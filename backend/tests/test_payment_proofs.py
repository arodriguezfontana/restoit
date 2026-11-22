"""Comprobantes de transferencia (US-60): carga, optimización, reemplazo, vigencia y el chat del bot."""

import asyncio
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.models.order import Order
from app.models.payment_proof import PaymentProof
from app.services import payment_proof_service
from app.services.bot_service import BotService
from app.services.store_config_service import get_or_create_store_config
from tests.conftest import TestingSessionLocal

WEB_URL = "/api/v1/orders/web"


def _image(fmt="PNG", size=(3000, 2000), color=(200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=fmt)
    return out.getvalue()


PDF = b"%PDF-1.4\n" + b"0" * 500


def _web_order(public_client, products, payment_method="transferencia") -> dict:
    response = public_client.post(
        WEB_URL,
        json={
            "customer_name": "Ana",
            "customer_phone": "+54 11 5555-1234",
            "delivery_method": "retiro",
            "shipping_address": None,
            "items": [{"product_id": products["muzza"].id, "quantity": 1}],
            "payment_method": payment_method,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload_web(public_client, order, data, token=None):
    return public_client.put(
        f"{WEB_URL}/{order['id']}/payment-proof",
        params={"token": token or order["proof_upload_token"]},
        content=data,
    )


def test_el_pedido_web_por_transferencia_devuelve_la_clave_para_adjuntar(public_client, products):
    transfer = _web_order(public_client, products)
    cash = _web_order(public_client, products, payment_method="efectivo")

    assert transfer["proof_upload_token"]
    assert cash["proof_upload_token"] is None


def test_el_cliente_adjunta_un_comprobante_y_el_panel_lo_ve(public_client, client, db_session, products):
    order = _web_order(public_client, products)

    response = _upload_web(public_client, order, _image())

    assert response.status_code == 201
    assert response.json()["payment_proof"]["content_type"] == "image/jpeg"
    detail = client.get(f"/api/v1/orders/{order['id']}").json()
    assert detail["payment_proof"] is not None
    file = client.get(f"/api/v1/orders/{order['id']}/payment-proof")
    assert file.status_code == 200 and file.headers["content-type"] == "image/jpeg"


def test_sin_la_clave_correcta_no_se_puede_adjuntar(public_client, products):
    order = _web_order(public_client, products)

    response = _upload_web(public_client, order, _image(), token="falsa")

    assert response.status_code == 403


def test_la_imagen_se_redimensiona_y_comprime(public_client, db_session, products):
    order = _web_order(public_client, products)
    original = _image("PNG", size=(4000, 3000))

    _upload_web(public_client, order, original)

    proof = db_session.query(PaymentProof).one()
    with Image.open(io.BytesIO(proof.data)) as saved:
        assert max(saved.size) == payment_proof_service.MAX_IMAGE_SIDE
    assert proof.size_bytes == len(proof.data) < len(original)


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_acepta_jpg_png_y_webp(public_client, products, fmt):
    order = _web_order(public_client, products)

    assert _upload_web(public_client, order, _image(fmt, size=(400, 300))).status_code == 201


def test_acepta_pdf_tal_cual(public_client, db_session, products):
    order = _web_order(public_client, products)

    response = _upload_web(public_client, order, PDF)

    assert response.status_code == 201
    proof = db_session.query(PaymentProof).one()
    assert (proof.content_type, proof.data) == ("application/pdf", PDF)


def test_rechaza_otros_formatos_y_archivos_de_mas_de_5_mb(public_client, products):
    order = _web_order(public_client, products)

    gif = _upload_web(public_client, order, b"GIF89a" + b"0" * 100)
    pesado = _upload_web(public_client, order, b"%PDF-" + b"0" * (5 * 1024 * 1024 + 1))

    assert gif.status_code == 415
    assert pesado.status_code == 413


def test_se_puede_reemplazar_mientras_no_este_abonado(public_client, client, db_session, products, open_shift):
    order = _web_order(public_client, products)
    _upload_web(public_client, order, _image(size=(300, 200)))

    _upload_web(public_client, order, PDF)
    assert db_session.query(PaymentProof).one().content_type == "application/pdf"

    client.patch(f"/api/v1/orders/{order['id']}/payment", json={"is_paid": True})
    bloqueado = _upload_web(public_client, order, _image(size=(300, 200)))
    assert bloqueado.status_code == 409


def test_un_pedido_que_no_es_por_transferencia_no_lleva_comprobante(client, public_client, products):
    order = _web_order(public_client, products, payment_method="efectivo")

    response = client.put(f"/api/v1/orders/{order['id']}/payment-proof", content=PDF)

    assert response.status_code == 400


def test_el_personal_adjunta_y_elimina_el_comprobante(client, public_client, db_session, products):
    order = _web_order(public_client, products)
    url = f"/api/v1/orders/{order['id']}/payment-proof"

    assert client.put(url, content=PDF).status_code == 201
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


def test_vigencia_por_defecto_48_horas_y_se_puede_configurar(public_client, db_session, products):
    order = _web_order(public_client, products)
    _upload_web(public_client, order, PDF)
    proof = db_session.query(PaymentProof).one()
    assert proof.expires_at - proof.uploaded_at == timedelta(hours=48)

    get_or_create_store_config(db_session).proof_retention_hours = 6
    db_session.commit()
    _upload_web(public_client, order, PDF)
    proof = db_session.query(PaymentProof).one()
    assert proof.expires_at - proof.uploaded_at == timedelta(hours=6)


def test_los_comprobantes_vencidos_se_eliminan(public_client, db_session, products):
    order = _web_order(public_client, products)
    _upload_web(public_client, order, PDF)
    proof_expires = db_session.query(PaymentProof).one().expires_at
    if proof_expires.tzinfo is None:
        proof_expires = proof_expires.replace(tzinfo=timezone.utc)

    assert payment_proof_service.delete_expired(db_session, proof_expires - timedelta(minutes=1)) == 0
    assert payment_proof_service.delete_expired(db_session, proof_expires + timedelta(minutes=1)) == 1
    assert db_session.query(PaymentProof).count() == 0


def test_un_comprobante_vencido_ya_no_se_ve_aunque_falte_borrarlo(public_client, client, db_session, products):
    order = _web_order(public_client, products)
    _upload_web(public_client, order, PDF)
    proof = db_session.query(PaymentProof).one()
    proof.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    assert client.get(f"/api/v1/orders/{order['id']}").json()["payment_proof"] is None
    assert client.get(f"/api/v1/orders/{order['id']}/payment-proof").status_code == 404


def test_el_ticket_indica_el_medio_y_si_hay_comprobante(public_client, db_session, products):
    from app.services.printer_service import build_ticket_lines

    order = _web_order(public_client, products)
    pedido = db_session.get(Order, order["id"])
    sin = [texto for _, texto in build_ticket_lines(pedido)]
    _upload_web(public_client, order, PDF)
    db_session.refresh(pedido)
    con = [texto for _, texto in build_ticket_lines(pedido)]

    assert "Pago: Transferencia (a cobrar)" in sin and "Comprobante: pendiente" in sin
    assert "Comprobante: adjunto" in con


# --- Bot ------------------------------------------------------------------------------------------------------------


def _bot_order(db_session, products, chat_id="777", method="transferencia"):
    from app.services.order_service import OrderRequest, create_bot_order

    request = OrderRequest(
        customer_name="Paula",
        customer_phone="11 4444-5555",
        delivery_method="retiro",
        shipping_address=None,
        notes=None,
        items=[(products["muzza"].id, 1, None, None, None, None)],
    )
    return create_bot_order(
        db_session, request, channel="telegram", chat_id=chat_id, scheduled_for=None, payment_method=method
    )


@pytest.fixture()
def bot_session(db_session):
    with patch("app.db.session.SessionLocal", TestingSessionLocal):
        yield


def _enviar_foto(data, chat_id="777"):
    from app.core.channels import Channel
    from app.services.channels.base import ArchivoRecibido

    canal = AsyncMock()
    canal.descargar_archivo.return_value = ArchivoRecibido(datos=data, mime_type="image/jpeg") if data else None
    with patch("app.services.bot_service.obtener_canal", return_value=canal):
        asyncio.run(BotService().guardar_comprobante(Channel.TELEGRAM, chat_id, "file-1"))
    return canal.enviar_mensaje.await_args.args[1]


def test_la_foto_del_chat_queda_en_el_ultimo_pedido_por_transferencia(db_session, products, bot_session):
    _bot_order(db_session, products, method="efectivo")
    pedido = _bot_order(db_session, products)

    respuesta = _enviar_foto(_image(size=(500, 400)))

    assert f"#{pedido.shift_number}" in respuesta and "Recibimos tu comprobante" in respuesta
    assert db_session.query(PaymentProof).one().order_id == pedido.id


def test_sin_pedido_por_transferencia_el_bot_avisa(db_session, products, bot_session):
    _bot_order(db_session, products, method="efectivo")

    respuesta = _enviar_foto(_image(size=(500, 400)))

    assert "No encontré un pedido" in respuesta
    assert db_session.query(PaymentProof).count() == 0


def test_si_el_archivo_no_sirve_el_bot_lo_explica(db_session, products, bot_session):
    _bot_order(db_session, products)

    assert "JPG, PNG, WEBP o PDF" in _enviar_foto(b"GIF89a" + b"0" * 50)
    assert "No pude recibir el archivo" in _enviar_foto(None)


def test_whatsapp_reconoce_fotos_y_documentos():
    from app.services.channels.whatsapp_webhook import mensajes_recibidos

    def datos(mensaje):
        return {"entry": [{"changes": [{"value": {"messages": [{"from": "549111", "id": "m1", **mensaje}]}}]}]}

    foto = mensajes_recibidos(datos({"type": "image", "image": {"id": "img-1"}}))
    pdf = mensajes_recibidos(datos({"type": "document", "document": {"id": "doc-1"}}))

    assert [m.archivo_id for m in foto + pdf] == ["img-1", "doc-1"]
