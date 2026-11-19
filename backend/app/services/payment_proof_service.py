"""Comprobantes de las transferencias: se suben por el panel, la web o el chat del bot, se guardan optimizados y se
eliminan solos cuando vencen (por defecto a las 48 horas)."""

import hashlib
import hmac
import io
import logging
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.channels import Channel
from app.core.config import settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError, UnsupportedFileError
from app.db.session import transaction
from app.models.order import Order, PaymentMethod
from app.models.payment_proof import MAX_PROOF_BYTES, MAX_PROOF_MB, PaymentProof
from app.repositories import order_repository, payment_proof_repository
from app.services.store_config_service import get_or_create_store_config

logger = logging.getLogger(__name__)

# El lado más largo de la imagen guardada: alcanza para leer el monto, la fecha y el destinatario sin ocupar de más.
MAX_IMAGE_SIDE = 1600
JPEG_QUALITY = 80
# Una imagen con más píxeles que esto no es una captura ni una foto de un comprobante (protege la memoria).
MAX_IMAGE_PIXELS = 60_000_000

PROOF_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "application/pdf")
FORMAT_ERROR = "El comprobante tiene que ser un archivo JPG, PNG, WEBP o PDF."


class InvalidProofError(UnsupportedFileError):
    """El comprobante no es un archivo aceptado o pesa demasiado."""


def detect_content_type(data: bytes) -> str:
    """Tipo del archivo según su contenido (no su nombre ni lo que declara quien lo sube)."""
    if len(data) > MAX_PROOF_BYTES:
        raise InvalidProofError(f"El comprobante no puede pesar más de {MAX_PROOF_MB} MB.")
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    raise InvalidProofError(FORMAT_ERROR)


def _optimized_image(data: bytes) -> bytes | None:
    """La imagen achicada y comprimida (JPEG), o None si no se puede leer."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                return None
            image = ImageOps.exif_transpose(image)
            image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
            if image.mode in ("RGBA", "LA", "P"):
                # Los PNG con transparencia se apoyan sobre blanco: en JPEG el fondo transparente quedaría negro.
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def prepare_proof(data: bytes) -> tuple[bytes, str]:
    """Valida el archivo y devuelve (bytes a guardar, tipo). Las imágenes se redimensionan y comprimen; el PDF se
    guarda tal cual."""
    content_type = detect_content_type(data)
    if content_type == "application/pdf":
        return data, content_type
    optimized = _optimized_image(data)
    if optimized is None:
        raise InvalidProofError(FORMAT_ERROR)
    # Una imagen que ya es chica puede pesar menos como estaba: se queda con la más liviana.
    if len(optimized) >= len(data) and max(_size_of(data)) <= MAX_IMAGE_SIDE:
        return data, content_type
    return optimized, "image/jpeg"


def _size_of(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def is_expired(proof: PaymentProof, now: datetime | None = None) -> bool:
    return _aware(proof.expires_at) <= (now or datetime.now(timezone.utc))


def pays_by_transfer(order: Order) -> bool:
    """El pedido se paga por transferencia (o su diferencia, si tiene un pago parcial)."""
    return PaymentMethod.TRANSFER.value in (order.payment_method, order.balance_payment_method)


def current_proof(order: Order, now: datetime | None = None) -> PaymentProof | None:
    """El comprobante vigente del pedido (los vencidos cuentan como inexistentes aunque falte borrarlos)."""
    if not pays_by_transfer(order):
        return None
    proof = order.payment_proof
    return None if proof is None or is_expired(proof, now) else proof


def save_proof(db: Session, order: Order, data: bytes, now: datetime | None = None) -> PaymentProof:
    """Guarda el comprobante del pedido, o reemplaza el que ya tenía mientras el pago no esté confirmado (un pedido que
    se cobró en el momento igual puede recibir su primer comprobante)."""
    if not pays_by_transfer(order):
        raise BusinessRuleError("El pedido no se paga por transferencia: no lleva comprobante.")
    if order.is_paid and payment_proof_repository.get_for_order(db, order.id) is not None:
        raise ConflictError("El pago del pedido ya está confirmado: el comprobante no se puede reemplazar.")
    stored, content_type = prepare_proof(data)
    now = now or datetime.now(timezone.utc)
    hours = get_or_create_store_config(db).proof_retention_hours
    with transaction(db):
        proof = payment_proof_repository.get_for_order(db, order.id)
        created = proof is None
        if proof is None:
            proof = PaymentProof(order_id=order.id)
        proof.content_type = content_type
        proof.data = stored
        proof.size_bytes = len(stored)
        proof.uploaded_at = now
        proof.expires_at = now + timedelta(hours=hours)
        if created:
            payment_proof_repository.add(db, proof)
    db.refresh(order)
    return proof


def get_proof_file(db: Session, order_id: int) -> PaymentProof:
    proof = payment_proof_repository.get_for_order(db, order_id)
    if proof is None or is_expired(proof):
        raise NotFoundError("El pedido no tiene comprobante (o ya venció).")
    return proof


def delete_proof(db: Session, order_id: int) -> None:
    with transaction(db):
        proof = payment_proof_repository.get_for_order(db, order_id)
        if proof is None:
            raise NotFoundError("El pedido no tiene comprobante.")
        db.delete(proof)


def delete_expired(db: Session, now: datetime | None = None) -> int:
    """Elimina los comprobantes vencidos y devuelve cuántos eran."""
    with transaction(db):
        return payment_proof_repository.delete_expired(db, now or datetime.now(timezone.utc))


# --- Quién puede subirlo -----------------------------------------------------------------------------------------


def upload_token(order_id: int) -> str:
    """Clave con la que el cliente de la web puede subir el comprobante de su pedido (sin tener cuenta)."""
    return hmac.new(settings.JWT_SECRET_KEY.encode(), f"proof:{order_id}".encode(), hashlib.sha256).hexdigest()[:32]


def require_valid_token(order_id: int, token: str | None) -> None:
    if not hmac.compare_digest(token or "", upload_token(order_id)):
        raise PermissionDeniedError("No tenés permiso para adjuntar un comprobante a este pedido.")


# --- Bot ------------------------------------------------------------------------------------------------------------


def attach_from_chat(db: Session, channel: Channel | str, chat_id: str, data: bytes) -> Order | None:
    """Guarda la foto que mandó el cliente por el chat en su último pedido por transferencia sin abonar.

    Devuelve el pedido, o None si el cliente no tiene ninguno. Si el archivo no sirve, lanza InvalidProofError.
    """
    order = order_repository.latest_transfer_for_chat(db, Channel(channel).value, chat_id)
    if order is None:
        return None
    save_proof(db, order, data)
    return order


# --- Limpieza periódica -------------------------------------------------------------------------------------------

CLEANUP_INTERVAL_SECONDS = 15 * 60


def _delete_expired_in_new_session() -> int:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        return delete_expired(db)


async def run_cleanup_loop(interval_seconds: float = CLEANUP_INTERVAL_SECONDS) -> None:
    """Elimina cada tanto los comprobantes vencidos. Corre mientras viva la aplicación."""
    import asyncio

    while True:
        try:
            deleted = await asyncio.to_thread(_delete_expired_in_new_session)
            if deleted:
                logger.info("Se eliminaron %s comprobantes de transferencia vencidos.", deleted)
        except Exception:
            logger.exception("No se pudieron eliminar los comprobantes vencidos.")
        await asyncio.sleep(interval_seconds)
