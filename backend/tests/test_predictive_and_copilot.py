"""Tests para US-67: Analítica Predictiva de Demanda, Insumos y Copilot Q&A Comercial."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.core.time import ahora_local
from app.models.menu import Category, Ingredient, Product, ProductIngredient
from app.models.order import Order, OrderItem

STATS_URL = "/api/v1/stats"


@pytest.fixture(autouse=True)
def _auth_stats_pin(client):
    client.headers["X-Admin-PIN"] = settings.ADMIN_PIN


NOW = ahora_local()
AYER = NOW - timedelta(days=1)
HACE_DOS_DIAS = NOW - timedelta(days=2)
HACE_TRES_DIAS = NOW - timedelta(days=3)

# Días pasados recientes dentro de las últimas semanas
days_since_sat = (NOW.weekday() - 5) % 7
if days_since_sat == 0:
    days_since_sat = 7
RECENT_SABADO = (NOW - timedelta(days=days_since_sat)).replace(hour=21, minute=0, second=0)
RECENT_DOMINGO = (RECENT_SABADO + timedelta(days=1)).replace(hour=21, minute=0, second=0)
RECENT_LUNES = (RECENT_SABADO - timedelta(days=5)).replace(hour=13, minute=0, second=0)


def _order(db_session, status="Finalizado", created_at=None, items=(), total=None):
    if created_at is None:
        created_at = AYER
    order = Order(
        customer_name="Cliente Predictivo",
        shipping_address="Retiro en el local",
        delivery_method="retiro",
        status=status,
        created_at=created_at,
        total_amount=Decimal(str(total)) if total is not None else sum(Decimal(str(p.price)) * q for p, q in items),
    )
    order.items = [OrderItem(product_id=p.id, quantity=q, unit_price=p.price) for p, q in items]
    db_session.add(order)
    db_session.commit()
    return order


@pytest.fixture()
def setup_menu_and_recipes(db_session):
    cat = Category(name="Pizzas Predictivas")
    db_session.add(cat)
    db_session.flush()

    harina = Ingredient(name="Harina 000", unit="kg", cost=Decimal("600"), extra_price=Decimal("0"))
    queso = Ingredient(name="Muzzarella Barra", unit="kg", cost=Decimal("4000"), extra_price=Decimal("500"))
    salsa = Ingredient(name="Tomate Triturado", unit="kg", cost=Decimal("1200"), extra_price=Decimal("0"))
    db_session.add_all([harina, queso, salsa])
    db_session.flush()

    pizza_muzza = Product(
        name="Pizza Muzzarella Gourmet",
        price=Decimal("8000"),
        category_id=cat.id,
        is_active=True,
    )
    pizza_fugazza = Product(
        name="Pizza Fugazzeta",
        price=Decimal("9500"),
        category_id=cat.id,
        is_active=True,
    )
    db_session.add_all([pizza_muzza, pizza_fugazza])
    db_session.flush()

    # Recetas
    db_session.add_all(
        [
            ProductIngredient(product_id=pizza_muzza.id, ingredient_id=harina.id, quantity=0.3),
            ProductIngredient(product_id=pizza_muzza.id, ingredient_id=queso.id, quantity=0.25),
            ProductIngredient(product_id=pizza_muzza.id, ingredient_id=salsa.id, quantity=0.15),
            ProductIngredient(product_id=pizza_fugazza.id, ingredient_id=harina.id, quantity=0.35),
            ProductIngredient(product_id=pizza_fugazza.id, ingredient_id=queso.id, quantity=0.35),
        ]
    )
    db_session.commit()

    return {
        "harina": harina,
        "queso": queso,
        "salsa": salsa,
        "muzza": pizza_muzza,
        "fugazza": pizza_fugazza,
    }


# --- Tests de Autenticación ---------------------------------------------------------------------------


def test_endpoints_predictivos_requieren_admin_pin(client):
    # Sin PIN
    del client.headers["X-Admin-PIN"]

    resp_pred = client.get(f"{STATS_URL}/predictions")
    assert resp_pred.status_code in (401, 403)

    resp_qa = client.post(f"{STATS_URL}/copilot/ask", json={"question": "¿Cuáles son los insumos con más gasto?"})
    assert resp_qa.status_code in (401, 403)


# --- Tests de Analítica Predictiva (/predictions) -----------------------------------------------------


def test_predictions_calcula_proyeccion_7_dias_y_diferencia_fin_de_semana(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]

    # Simular ventas en días de semana y fin de semana
    _order(db_session, status="Finalizado", created_at=RECENT_LUNES, items=[(muzza, 2)], total=16000)
    _order(db_session, status="Finalizado", created_at=RECENT_SABADO, items=[(muzza, 5)], total=40000)
    _order(db_session, status="Finalizado", created_at=RECENT_DOMINGO, items=[(muzza, 4)], total=32000)
    _order(db_session, status="Cancelado", created_at=RECENT_SABADO, total=8000)

    resp = client.get(f"{STATS_URL}/predictions")
    assert resp.status_code == 200
    data = resp.json()

    # Valida estructura de 7 días
    assert len(data["days"]) == 7
    for day in data["days"]:
        assert "date" in day
        assert "day_name" in day
        assert "is_weekend" in day
        assert "projected_orders" in day
        assert "projected_revenue" in day

    # Debe diferenciar fin de semana y días de semana
    assert "weekday_projected_orders" in data
    assert "weekend_projected_orders" in data
    assert "weekday_projected_revenue" in data
    assert "weekend_projected_revenue" in data
    assert data["total_projected_orders"] == data["weekday_projected_orders"] + data["weekend_projected_orders"]
    assert round(data["total_projected_revenue"], 2) == round(
        data["weekday_projected_revenue"] + data["weekend_projected_revenue"], 2
    )

    # Demanda proyectada de insumos principales
    assert len(data["ingredient_demands"]) > 0
    names = [i["ingredient_name"] for i in data["ingredient_demands"]]
    assert "Muzzarella Barra" in names or "Harina 000" in names

    # Prescripciones estratégicas
    assert len(data["strategic_prescriptions"]) >= 3


def test_predictions_degradacion_controlada_sin_gemini(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    _order(db_session, status="Finalizado", created_at=AYER, items=[(muzza, 3)], total=24000)

    # Simular falla de Gemini
    with patch("app.services.predictive_service.genai.Client", side_effect=Exception("Error de cuota 429")):
        resp = client.get(f"{STATS_URL}/predictions")
        assert resp.status_code == 200
        data = resp.json()

        # No arroja 500 y degrada a estimaciones determinísticas
        assert data["is_ai_generated"] is False
        assert data["disclaimer"] is not None
        assert len(data["strategic_prescriptions"]) >= 3


# --- Tests de Copilot Q&A Comercial (/copilot/ask) ----------------------------------------------------


def test_copilot_responde_insumos_con_mayor_gasto(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    fugazza = setup_menu_and_recipes["fugazza"]

    # 4 muzza: 4*0.25kg = 1kg queso ($4.000), 4*0.3kg = 1.2kg harina ($720), 4*0.15kg = 0.6kg salsa ($720)
    # 2 fugazza: 2*0.35kg = 0.7kg queso ($2.800), 2*0.35kg = 0.7kg harina ($420)
    # Total queso: 1.7kg -> $6.800 (mayor gasto)
    _order(db_session, status="Finalizado", created_at=AYER, items=[(muzza, 4), (fugazza, 2)])

    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "¿Cuáles son los 3 insumos con más gasto este mes?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "answer" in data
    assert "cited_period" in data
    assert "Muzzarella Barra" in data["answer"]
    assert "data_summary" in data
    # Verifica cero alucinación numérica: el total de gasto viene en data_summary
    items = data["data_summary"]["items"]
    assert items[0]["ingredient_name"] == "Muzzarella Barra"
    assert items[0]["total_spent"] == 6800.0


def test_copilot_responde_dia_con_mas_cancelaciones(client, db_session):
    # 3 cancelaciones en sábado, 1 en lunes
    _order(db_session, status="Cancelado", created_at=RECENT_SABADO, total=15000)
    _order(db_session, status="Cancelado", created_at=RECENT_SABADO, total=12000)
    _order(db_session, status="Cancelado", created_at=RECENT_SABADO, total=8000)
    _order(db_session, status="Cancelado", created_at=RECENT_LUNES, total=6000)
    _order(db_session, status="Finalizado", created_at=RECENT_LUNES, total=20000)

    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "¿Qué día tuvimos más cancelaciones?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "Sábado" in data["answer"]
    assert data["data_summary"]["worst_day"] == "Sábado"
    assert data["data_summary"]["worst_day_cancellations"] == 3


def test_copilot_responde_insumos_a_comprar_antes_del_fin_de_semana(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    _order(db_session, status="Finalizado", created_at=RECENT_SABADO, items=[(muzza, 6)], total=48000)

    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "¿Qué insumos debería comprar antes del fin de semana?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "answer" in data
    assert len(data["suggested_followups"]) > 0


def test_copilot_responde_facturacion_pasada(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    _order(db_session, status="Finalizado", created_at=AYER, items=[(muzza, 2)], total=16000)

    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "¿Cuánto facturamos la última semana?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "data_summary" in data
    assert "revenue" in data["data_summary"]
    assert "cited_period" in data


def test_copilot_responde_platos_mas_rentables(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    fugazza = setup_menu_and_recipes["fugazza"]

    _order(db_session, status="Finalizado", created_at=AYER, items=[(muzza, 5), (fugazza, 2)])

    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "¿Cuáles son los platos más rentables?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "Pizza Muzzarella Gourmet" in data["answer"] or "Pizza Fugazzeta" in data["answer"]
    assert "margin_pct" in str(data["data_summary"])


def test_copilot_degradacion_controlada_ante_falla_de_gemini(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    _order(db_session, status="Finalizado", created_at=AYER, items=[(muzza, 2)], total=16000)

    # Simular timeout / error de Gemini
    with patch("app.services.copilot_service.genai.Client", side_effect=Exception("Timeout en API de Gemini")):
        resp = client.post(
            f"{STATS_URL}/copilot/ask",
            json={"question": "¿Cuáles son los 3 insumos con más gasto este mes?"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # No arroja 500 y degrada de forma controlada
        assert data["is_fallback"] is True
        assert "Muzzarella Barra" in data["answer"]
        assert data["cited_period"] is not None
        assert data["data_summary"] is not None


def test_copilot_responde_cuantas_muzzarelas_vendi(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    _order(db_session, status="Finalizado", created_at=AYER, items=[(muzza, 4)], total=32000)

    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "cuantas muzzarelas vendi?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "Vendiste" in data["answer"]
    assert "Pizza Muzzarella" in data["answer"]
    assert data["data_summary"]["total_units_sold"] == 4


def test_copilot_responde_me_conviene_comprar_insumo(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    _order(db_session, status="Finalizado", created_at=AYER, items=[(muzza, 3)], total=24000)

    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "me conviene comprar muzzarella?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "conviene comprar" in data["answer"].lower()
    assert "Muzzarella Barra" in data["answer"]
    assert data["data_summary"]["ingredient_name"] == "Muzzarella Barra"
    # Consultas puramente informativas no deben forzar acciones sugeridas
    assert data["suggested_action"] is None


def test_copilot_sugiere_y_ejecuta_pausar_producto(client, db_session, setup_menu_and_recipes):
    muzza = setup_menu_and_recipes["muzza"]
    fugazza = setup_menu_and_recipes["fugazza"]
    # Muzza tiene ventas, Fugazza tiene cero ventas
    _order(db_session, status="Finalizado", created_at=AYER, items=[(muzza, 5)], total=40000)

    # Preguntar qué producto eliminar/reemplazar
    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "qué producto podría eliminar y por qué cambiarlo?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    action = data.get("suggested_action")
    assert action is not None
    assert action["action_type"] == "deactivate_product"
    assert action["payload"]["product_id"] == fugazza.id
    assert "Pausar" in action["button_label"]

    # Ejecutar la acción aprobada por el admin
    exec_resp = client.post(
        f"{STATS_URL}/copilot/execute-action",
        json={"action_type": action["action_type"], "payload": action["payload"]},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["success"] is True
    assert exec_data["executed_action"] == "deactivate_product"

    # Verificar que el producto quedó inactivo en base de datos
    db_session.refresh(fugazza)
    assert fugazza.is_active is False


def test_copilot_sugiere_y_ejecuta_crear_promocion(client, db_session, setup_menu_and_recipes):
    resp = client.post(
        f"{STATS_URL}/copilot/ask",
        json={"question": "¿qué promoción me recomendás crear para aumentar las ventas?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    action = data.get("suggested_action")
    assert action is not None
    assert action["action_type"] == "create_promotion"
    assert "items" in action["payload"]
    assert len(action["payload"]["items"]) >= 2

    # Ejecutar creación de promo
    exec_resp = client.post(
        f"{STATS_URL}/copilot/execute-action",
        json={"action_type": action["action_type"], "payload": action["payload"]},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["success"] is True
    assert exec_data["executed_action"] == "create_promotion"
    assert exec_data["affected_entity_id"] is not None

