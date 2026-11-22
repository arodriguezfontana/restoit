from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.db.base_class import Base

# Comprobante de una transferencia: JPG, PNG, WEBP o PDF de hasta 5 MB.
MAX_PROOF_BYTES = 5 * 1024 * 1024
MAX_PROOF_MB = MAX_PROOF_BYTES // (1024 * 1024)
# Cuánto se guarda un comprobante si el local no indica otra cosa.
DEFAULT_PROOF_RETENTION_HOURS = 48


class PaymentProof(Base):
    """Comprobante de la transferencia de un pedido. Hay uno por pedido: subir otro lo reemplaza.

    Se guarda en la base (los bytes van aparte para no traerlos al consultar el pedido) y se elimina solo cuando
    vence (ver payment_proof_service.delete_expired).
    """

    __tablename__ = "payment_proofs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
