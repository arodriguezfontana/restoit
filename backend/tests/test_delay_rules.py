"""US-65: configuración de la demora (inteligente y reglas fijas por método de entrega)."""

from datetime import datetime, timedelta, timezone

from app.models.order import Order, OrderStatusEvent
from app.services import order_service
from app.services.delivery_time_service import MIN_SAMPLES_FOR_SMART_ESTIMATE, estimate_delay
from app.services.order_service import OrderRequest

URL = "/api/v1/delay-settings"


def _regla(client, metodo, desde, hasta, minutos):
    return client.post(
        f"{URL}/rules",
        json={"delivery_method": metodo, "min_orders": desde, "max_orders": hasta, "minutes": minutos},
    )


def _nuevo_pedido(db_session, products, metodo="domicilio"):
    """Pedido que entra por el chat (queda tomado directamente, con la demora que corresponda)."""
    request = OrderRequest(
        customer_name="Ana",
        customer_phone="1155551234",
        delivery_method=metodo,
        shipping_address="Calle 1",
        notes=None,
        items=[(products["muzza"].id, 1)],
    )
    return order_service.create_bot_order(db_session, request, None, None, None, None)


def _pedido(db_session, status="Confirmado", metodo="domicilio"):
    order = Order(
        customer_name="Ana", shipping_address="Calle 1", total_amount=100.0, status=status, delivery_method=metodo
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def _historial(db_session, cantidad, minutos, metodo="domicilio"):
    for _ in range(cantidad):
        order = _pedido(db_session, status="Finalizado", metodo=metodo)
        order.actual_minutes = minutos
        db_session.add(
            OrderStatusEvent(order_id=order.id, status="Confirmado", occurred_at=datetime.now(timezone.utc), queue_size=0)
        )
    db_session.commit()


def test_la_configuracion_requiere_ser_admin(public_client):
    assert public_client.get(URL).status_code == 401
    assert public_client.put(f"{URL}/smart", json={"enabled": False}).status_code == 401
    assert public_client.post(f"{URL}/rules", json={}).status_code == 401


def test_por_defecto_la_demora_inteligente_esta_activa_y_sin_reglas(client):
    data = client.get(URL).json()
    assert data == {"smart_delay_enabled": True, "pickup_rules": [], "delivery_rules": []}


def test_activar_y_desactivar_la_demora_inteligente(client):
    assert client.put(f"{URL}/smart", json={"enabled": False}).json()["smart_delay_enabled"] is False
    assert client.get(URL).json()["smart_delay_enabled"] is False
    assert client.put(f"{URL}/smart", json={"enabled": True}).json()["smart_delay_enabled"] is True


def test_cada_metodo_tiene_sus_propias_reglas(client):
    assert _regla(client, "domicilio", 0, 10, 30).status_code == 201
    assert _regla(client, "domicilio", 11, 20, 40).status_code == 201
    assert _regla(client, "domicilio", 21, None, 50).status_code == 201
    # El mismo rango en retiro no choca con el de envío.
    assert _regla(client, "retiro", 0, 15, 20).status_code == 201

    data = client.get(URL).json()
    assert [(r["min_orders"], r["max_orders"], r["minutes"]) for r in data["delivery_rules"]] == [
        (0, 10, 30),
        (11, 20, 40),
        (21, None, 50),
    ]
    assert [(r["min_orders"], r["max_orders"], r["minutes"]) for r in data["pickup_rules"]] == [(0, 15, 20)]


def test_los_rangos_no_pueden_superponerse(client):
    _regla(client, "domicilio", 0, 10, 30)
    respuesta = _regla(client, "domicilio", 10, 20, 40)
    assert respuesta.status_code == 400
    assert "se superpone" in respuesta.json()["detail"]


def test_los_minutos_deben_ser_mayores_a_cero(client):
    assert _regla(client, "domicilio", 0, 10, 0).status_code == 400
    assert _regla(client, "domicilio", 0, 10, -5).status_code == 400


def test_o_mas_solo_puede_estar_en_la_ultima_regla(client):
    _regla(client, "domicilio", 21, None, 50)
    # Una regla posterior a "o más" (o que lo pise) se rechaza.
    assert _regla(client, "domicilio", 30, 40, 60).status_code == 400
    assert _regla(client, "domicilio", 5, None, 40).status_code == 400
    # Una anterior sin pisarlo está bien.
    assert _regla(client, "domicilio", 0, 20, 30).status_code == 201


def test_el_fin_del_rango_no_puede_ser_menor_al_inicio(client):
    assert _regla(client, "domicilio", 10, 5, 30).status_code == 400


def test_editar_y_eliminar_una_regla(client):
    primera = _regla(client, "retiro", 0, 15, 20).json()
    segunda = _regla(client, "retiro", 16, 20, 30).json()

    editada = client.put(f"{URL}/rules/{segunda['id']}", json={"min_orders": 16, "max_orders": 25, "minutes": 35})
    assert editada.status_code == 200
    assert (editada.json()["max_orders"], editada.json()["minutes"]) == (25, 35)

    # Al editar, la regla no choca consigo misma pero sí con las demás.
    assert client.put(f"{URL}/rules/{segunda['id']}", json={"min_orders": 10, "max_orders": 25, "minutes": 35}).status_code == 400

    assert client.delete(f"{URL}/rules/{primera['id']}").status_code == 204
    assert [r["id"] for r in client.get(URL).json()["pickup_rules"]] == [segunda["id"]]
    assert client.delete(f"{URL}/rules/{primera['id']}").status_code == 404


def test_se_aplica_la_regla_fija_cuando_entra_un_pedido(client, db_session, products):
    _regla(client, "domicilio", 0, 10, 30)

    order = _nuevo_pedido(db_session, products)

    assert (order.status, order.estimated_minutes, order.estimate_source) == ("Confirmado", 30, "fixed")


def test_la_regla_depende_de_los_pedidos_en_cola(client, db_session):
    _regla(client, "domicilio", 0, 0, 30)
    _regla(client, "domicilio", 1, None, 50)
    _pedido(db_session, status="Confirmado")

    assert estimate_delay(db_session, "domicilio", 0).minutes == 30
    assert estimate_delay(db_session, "domicilio", 1).minutes == 50
    # Un método sin reglas sigue pidiendo la demora a mano.
    assert estimate_delay(db_session, "retiro", 0).minutes is None


def test_sin_regla_aplicable_el_pedido_entra_sin_demora_y_el_personal_puede_cargarla(client, db_session, products):
    _regla(client, "domicilio", 5, 10, 30)

    order = _nuevo_pedido(db_session, products)

    assert (order.estimated_minutes, order.estimate_source) == (None, None)
    manual = client.patch(f"/api/v1/orders/{order.id}/delay", json={"estimated_minutes": 45})
    assert (manual.json()["estimated_minutes"], manual.json()["estimate_source"]) == (45, "manual")


def test_con_ambas_activas_gana_la_inteligente_si_hay_datos(client, db_session):
    _regla(client, "domicilio", 0, None, 30)
    _historial(db_session, MIN_SAMPLES_FOR_SMART_ESTIMATE, 40)

    estimate = estimate_delay(db_session, "domicilio", 0)
    assert (estimate.mode.value, estimate.minutes) == ("smart", 40)


def test_sin_datos_suficientes_cae_a_la_regla_fija(client, db_session):
    _regla(client, "domicilio", 0, None, 30)
    _historial(db_session, MIN_SAMPLES_FOR_SMART_ESTIMATE - 1, 40)

    estimate = estimate_delay(db_session, "domicilio", 0)
    assert (estimate.mode.value, estimate.minutes) == ("fixed", 30)


def test_con_la_inteligente_desactivada_solo_rigen_las_reglas(client, db_session):
    _regla(client, "domicilio", 0, None, 30)
    _historial(db_session, MIN_SAMPLES_FOR_SMART_ESTIMATE, 40)
    client.put(f"{URL}/smart", json={"enabled": False})

    estimate = estimate_delay(db_session, "domicilio", 0)
    assert (estimate.mode.value, estimate.minutes, estimate.samples) == ("fixed", 30, 0)

    # Sin reglas tampoco se sugiere nada por historial.
    other = estimate_delay(db_session, "retiro", 0)
    assert other.minutes is None


def test_cambiar_la_configuracion_no_altera_pedidos_ya_tomados(client, db_session, products):
    regla = _regla(client, "domicilio", 0, None, 30).json()
    order = _nuevo_pedido(db_session, products)

    client.put(f"{URL}/rules/{regla['id']}", json={"min_orders": 0, "max_orders": None, "minutes": 99})
    client.put(f"{URL}/smart", json={"enabled": False})

    db_session.refresh(order)
    assert (order.estimated_minutes, order.estimate_source) == (30, "fixed")


def test_un_pedido_programado_entra_sin_demora_y_no_cuenta_en_la_cola(client, db_session, products):
    _regla(client, "domicilio", 0, 0, 30)
    request = OrderRequest(
        customer_name="Ana",
        customer_phone="1155551234",
        delivery_method="domicilio",
        shipping_address="Calle 1",
        notes=None,
        items=[(products["muzza"].id, 1)],
    )
    programado = datetime.now(timezone.utc) + timedelta(hours=3)

    pedido = order_service.create_bot_order(db_session, request, None, None, programado, None)
    assert (pedido.status, pedido.estimated_minutes, pedido.estimate_source) == ("Confirmado", None, None)

    # El programado no ocupa la cocina: el siguiente pedido para ahora sigue entrando con la regla de cola vacía.
    siguiente = _nuevo_pedido(db_session, products)
    assert (siguiente.estimated_minutes, siguiente.estimate_source) == (30, "fixed")


def test_un_pedido_de_mostrador_toma_la_regla_fija_y_no_activa_la_alerta(client, db_session, products, open_shift):
    _regla(client, "domicilio", 0, None, 25)

    respuesta = client.post(
        "/api/v1/orders/counter",
        json={
            "customer_name": "Paula",
            "customer_phone": "11 4444-5555",
            "delivery_method": "domicilio",
            "shipping_address": "Belgrano 95",
            "items": [{"product_id": products["muzza"].id, "quantity": 1}],
            "payment_method": "efectivo",
            "is_paid": False,
        },
    )

    assert respuesta.status_code == 201
    order = db_session.get(Order, respuesta.json()["id"])
    assert (order.estimated_minutes, order.estimate_source) == (25, "fixed")
    assert order.needs_attention is False
