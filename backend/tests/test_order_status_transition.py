from datetime import datetime, timezone

import pytest

from app.api.deps import get_current_user
from app.main import app
from app.models.order import Order


def _create_order(db_session, status="Confirmado", delivery_method="domicilio"):
    order = Order(
        customer_name="Juan Perez",
        shipping_address="Av. Siempreviva 742",
        total_amount=1000.0,
        status=status,
        delivery_method=delivery_method,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def test_confirmado_to_en_camino_succeeds_for_domicilio(client, db_session):
    order = _create_order(db_session, status="Confirmado", delivery_method="domicilio")

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "En Camino"})

    assert response.status_code == 200
    assert response.json()["status"] == "En Camino"


def test_confirmado_to_listo_para_retirar_succeeds_for_retiro(client, db_session):
    order = _create_order(db_session, status="Confirmado", delivery_method="retiro")

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "Listo para Retirar"})

    assert response.status_code == 200
    assert response.json()["status"] == "Listo para Retirar"


@pytest.mark.parametrize("terminal_status", ["En Camino", "Listo para Retirar"])
def test_en_camino_or_listo_to_finalizado_succeeds(client, db_session, terminal_status):
    order = _create_order(db_session, status=terminal_status)

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "Finalizado"})

    assert response.status_code == 200
    assert response.json()["status"] == "Finalizado"


def test_skipping_a_step_is_rejected(client, db_session):
    order = _create_order(db_session, status="Confirmado")

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "Finalizado"})

    assert response.status_code == 409


@pytest.mark.parametrize("terminal_status", ["Finalizado", "Cancelado"])
def test_transition_from_terminal_status_is_rejected(client, db_session, terminal_status):
    order = _create_order(db_session, status=terminal_status)

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "En Camino"})

    assert response.status_code == 409


@pytest.mark.parametrize("removed_status", ["Pendiente", "Rechazado"])
def test_los_estados_de_aceptacion_ya_no_existen(client, db_session, removed_status):
    order = _create_order(db_session)

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": removed_status})

    assert response.status_code == 422


def test_invalid_status_value_is_rejected(client, db_session):
    order = _create_order(db_session)

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "Bogus"})

    assert response.status_code == 422


def test_order_not_found_returns_404(client, db_session):
    response = client.patch("/api/v1/orders/9999/status", json={"status": "En Camino"})

    assert response.status_code == 404


def test_requires_authentication(client, db_session):
    order = _create_order(db_session)
    del app.dependency_overrides[get_current_user]

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "En Camino"})

    assert response.status_code == 401


@pytest.mark.parametrize("status", ["Confirmado", "En Camino", "Listo para Retirar"])
def test_cualquier_pedido_activo_se_puede_cancelar(client, db_session, status):
    order = _create_order(db_session, status=status)

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "Cancelado"})

    assert response.status_code == 200
    assert response.json()["status"] == "Cancelado"


@pytest.mark.parametrize("status", ["Finalizado", "Cancelado"])
def test_no_se_puede_cancelar_un_pedido_terminado(client, db_session, status):
    order = _create_order(db_session, status=status)

    response = client.patch(f"/api/v1/orders/{order.id}/status", json={"status": "Cancelado"})

    assert response.status_code == 409


# --- Demora a mano ---


def test_el_personal_modifica_la_demora_de_un_pedido(client, db_session):
    order = _create_order(db_session)

    response = client.patch(f"/api/v1/orders/{order.id}/delay", json={"estimated_minutes": 45})

    assert response.status_code == 200
    assert (response.json()["estimated_minutes"], response.json()["estimate_source"]) == (45, "manual")


@pytest.mark.parametrize("minutes", [0, -5])
def test_la_demora_a_mano_debe_ser_mayor_a_cero(client, db_session, minutes):
    order = _create_order(db_session)

    assert client.patch(f"/api/v1/orders/{order.id}/delay", json={"estimated_minutes": minutes}).status_code == 422


def test_un_programado_no_acepta_demora(client, db_session):
    order = _create_order(db_session)
    order.scheduled_for = datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc)
    db_session.commit()

    response = client.patch(f"/api/v1/orders/{order.id}/delay", json={"estimated_minutes": 30})

    assert response.status_code == 400
    db_session.refresh(order)
    assert order.estimated_minutes is None


def test_no_se_modifica_la_demora_de_un_pedido_terminado(client, db_session):
    order = _create_order(db_session, status="Finalizado")

    assert client.patch(f"/api/v1/orders/{order.id}/delay", json={"estimated_minutes": 30}).status_code == 400


# --- Pedido nuevo visto ---


def test_marcar_visto_apaga_la_alerta_del_pedido(client, db_session):
    order = _create_order(db_session)
    order.needs_attention = True
    db_session.commit()

    response = client.post(f"/api/v1/orders/{order.id}/seen")

    assert response.status_code == 200
    assert response.json()["needs_attention"] is False
    db_session.refresh(order)
    assert order.needs_attention is False
