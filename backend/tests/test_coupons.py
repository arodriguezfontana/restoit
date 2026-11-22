"""Tests para el módulo de Cupones Web y las nuevas acciones del Copilot."""

import pytest

from app.core.config import settings
from app.models.coupon import Coupon
from app.models.menu import Category
from app.models.promotion import Promotion
from app.schemas.predictive_schemas import CopilotActionExecutionPayload
from app.services.copilot_service import execute_copilot_action

COUPONS_URL = "/api/v1/coupons"
VALIDATE_URL = "/api/v1/coupons/validate"
WEB_ORDERS_URL = "/api/v1/orders/web"


@pytest.fixture(autouse=True)
def _auth_admin_pin(client):
    client.headers["X-Admin-PIN"] = settings.ADMIN_PIN


def test_create_and_list_coupons(client):
    res = client.post(COUPONS_URL, json={
        "code": "promo15",
        "discount_percentage": 15,
        "is_active": True
    })
    assert res.status_code == 201
    data = res.json()
    assert data["code"] == "PROMO15"
    assert data["discount_percentage"] == 15
    assert data["is_active"] is True

    # List
    list_res = client.get(COUPONS_URL)
    assert list_res.status_code == 200
    coupons = list_res.json()
    assert any(c["code"] == "PROMO15" for c in coupons)


def test_create_duplicate_coupon(client):
    client.post(COUPONS_URL, json={"code": "DUP20", "discount_percentage": 20})
    dup_res = client.post(COUPONS_URL, json={"code": "dup20", "discount_percentage": 10})
    assert dup_res.status_code in (400, 409)
    assert "ya existe" in dup_res.json()["detail"].lower()


def test_update_and_delete_coupon(client):
    res = client.post(COUPONS_URL, json={"code": "TEMP", "discount_percentage": 10})
    c_id = res.json()["id"]

    # Pause
    upd_res = client.put(f"{COUPONS_URL}/{c_id}", json={"is_active": False, "discount_percentage": 25})
    assert upd_res.status_code == 200
    assert upd_res.json()["is_active"] is False
    assert upd_res.json()["discount_percentage"] == 25

    # Delete
    del_res = client.delete(f"{COUPONS_URL}/{c_id}")
    assert del_res.status_code == 204


def test_validate_coupon_endpoint(public_client, client):
    client.post(COUPONS_URL, json={"code": "VALID10", "discount_percentage": 10, "is_active": True})
    client.post(COUPONS_URL, json={"code": "PAUSED10", "discount_percentage": 10, "is_active": False})

    # Valid
    val = public_client.get(f"{VALIDATE_URL}/valid10")
    assert val.status_code == 200
    assert val.json()["valid"] is True
    assert val.json()["discount_percentage"] == 10

    # Inactive
    inv = public_client.get(f"{VALIDATE_URL}/PAUSED10")
    assert inv.status_code == 200
    assert inv.json()["valid"] is False

    # Not found
    nf = public_client.get(f"{VALIDATE_URL}/NONEXIST")
    assert nf.status_code == 200
    assert nf.json()["valid"] is False


def test_web_order_with_valid_coupon(public_client, client, products):
    client.post(COUPONS_URL, json={"code": "DESCUENTO20", "discount_percentage": 20, "is_active": True})

    items = [{"product_id": products["muzza"].id, "quantity": 1}]
    base_price = 8500.0  # muzza price

    order_payload = {
        "customer_name": "Juan Pérez",
        "customer_phone": "+54 11 5555-1234",
        "delivery_method": "retiro",
        "notes": "Bien cocida",
        "items": items,
        "coupon_code": "descuento20",
    }

    res = public_client.post(WEB_ORDERS_URL, json=order_payload)
    assert res.status_code == 201
    body = res.json()

    # 20% discount on 8500 = 6800
    expected_total = base_price * 0.8
    assert body["total_amount"] == expected_total
    assert "DESCUENTO20" in (body.get("notes") or "")


def test_web_order_with_invalid_coupon(public_client, products):
    items = [{"product_id": products["muzza"].id, "quantity": 1}]
    order_payload = {
        "customer_name": "Juan Pérez",
        "customer_phone": "+54 11 5555-1234",
        "delivery_method": "retiro",
        "items": items,
        "coupon_code": "INVALID_CODE",
    }
    res = public_client.post(WEB_ORDERS_URL, json=order_payload)
    assert res.status_code == 400
    assert "cupón" in res.json()["detail"].lower()


def test_copilot_extended_actions(db_session, products):
    # Test update_product_price
    p_muzza = products["muzza"]
    plan = CopilotActionExecutionPayload(
        action_type="update_product_price",
        payload={"product_id": p_muzza.id, "new_price": 9999.0},
    )
    res = execute_copilot_action(db_session, plan)
    assert res.success is True
    db_session.refresh(p_muzza)
    assert float(p_muzza.price) == 9999.0

    # Test update_category_prices
    cat = db_session.query(Category).first()
    plan_cat = CopilotActionExecutionPayload(
        action_type="update_category_prices",
        payload={"category_id": cat.id, "percentage_increase": 10},
    )
    res_cat = execute_copilot_action(db_session, plan_cat)
    assert res_cat.success is True

    # Test toggle_promotion_status
    promo = Promotion(name="Promo Test", price=1500.0, is_active=True)
    db_session.add(promo)
    db_session.commit()
    plan_promo = CopilotActionExecutionPayload(
        action_type="toggle_promotion_status",
        payload={"promotion_id": promo.id, "activate": False},
    )
    res_promo = execute_copilot_action(db_session, plan_promo)
    assert res_promo.success is True
    db_session.refresh(promo)
    assert promo.is_active is False

    # Test generate_shopping_list
    plan_shop = CopilotActionExecutionPayload(
        action_type="generate_shopping_list",
        payload={"forecast_days": 3},
    )
    res_shop = execute_copilot_action(db_session, plan_shop)
    assert res_shop.success is True

    # Test compensate_customers_coupon
    plan_comp = CopilotActionExecutionPayload(
        action_type="compensate_customers_coupon",
        payload={"coupon_code": "DISCULPA15", "discount_percentage": 15},
    )
    res_comp = execute_copilot_action(db_session, plan_comp)
    assert res_comp.success is True
    c = db_session.query(Coupon).filter(Coupon.code == "DISCULPA15").first()
    assert c is not None
    assert c.discount_percentage == 15

    # Test create_targeted_promotion
    plan_target = CopilotActionExecutionPayload(
        action_type="create_targeted_promotion",
        payload={"name": "Promo Clientes Fieles", "discount_percent": 20},
    )
    res_target = execute_copilot_action(db_session, plan_target)
    assert res_target.success is True
