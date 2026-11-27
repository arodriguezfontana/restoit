"""Productos con variantes (ej. pizza Grande / Chica, milanesa de Carne / Pollo): cada una con su precio."""

import json
from unittest.mock import patch

import pytest

from app.models.menu import Category, InvalidVariantError, Product
from app.models.order import Order, OrderItem
from app.models.promotion import Promotion
from app.services.tools.order_tools import calcular_y_preparar_pedido, confirmar_y_guardar_pedido
from tests.conftest import TestingSessionLocal

PRODUCTS_URL = "/api/v1/products"
MENU_URL = "/api/v1/menu/products"
WEB_ORDERS_URL = "/api/v1/orders/web"


@pytest.fixture()
def menu(db_session):
    """Pizzas Grande / Chica, una milanesa de Carne / Pollo y una bebida sin variantes."""
    pizzas = Category(name="Pizzas", sector="pizzeria")
    sandwiches = Category(name="Sándwiches")
    bebidas = Category(name="Bebidas", sector="barra")
    db_session.add_all([pizzas, sandwiches, bebidas])
    db_session.flush()

    def producto(name, category, variants=(), price=None):
        product = Product(name=name, price=price or 1, category_id=category.id, dietary_restrictions=[])
        product.replace_variants(list(variants))
        db_session.add(product)
        return product

    productos = {
        "muzza": producto("Muzzarella", pizzas, [("Grande", 16000), ("Chica", 14000)]),
        "napo": producto("Napolitana", pizzas, [("Grande", 19000), ("Chica", 17000)]),
        "milanesa": producto("Milanesa Simple", sandwiches, [("Carne", 16000), ("Pollo", 14000)]),
        "pizzaneza": producto("Pizzaneza Napolitana", pizzas, [("Carne", 38000), ("Pollo", 36000)]),
        "coca": producto("Coca-Cola", bebidas, price=2500),
    }
    db_session.commit()
    return productos


@pytest.fixture()
def bot_session(db_session):
    with patch("app.services.tools.order_tools.SessionLocal", TestingSessionLocal):
        yield


def _pedido(items, **overrides):
    return {
        "customer_name": "Ana",
        "customer_phone": "1155551234",
        "delivery_method": "retiro",
        "items": items,
        **overrides,
    }


def _calcular(items: str) -> dict:
    return json.loads(_respuesta(items))


def _respuesta(items: str) -> str:
    """Lo que devuelve el bot: el pedido en JSON o, si no pudo armar ninguno, el texto para el cliente."""
    return calcular_y_preparar_pedido.invoke({"items_solicitados": items})


# --- Modelo ---------------------------------------------------------------------------------------------


def test_el_precio_del_producto_es_el_de_la_variante_mas_barata(menu):
    assert menu["muzza"].price == 14000
    assert [(v.name, v.price) for v in menu["muzza"].variants] == [("Grande", 16000), ("Chica", 14000)]


def test_cada_variante_tiene_su_precio(menu):
    assert menu["muzza"].price_for("grande") == 16000
    assert menu["muzza"].price_for(" Chica ") == 14000
    assert menu["coca"].price_for(None) == 2500


@pytest.mark.parametrize("variante", [None, "", "Mediana"])
def test_un_producto_con_variantes_exige_una_de_las_suyas(menu, variante):
    with pytest.raises(InvalidVariantError, match="Grande"):
        menu["muzza"].price_for(variante)


@pytest.mark.parametrize(
    "variantes",
    [[("Grande", 100), ("grande", 90)], [("", 100)], [("Grande", 0)], [("x" * 51, 100)]],
)
def test_rechaza_variantes_invalidas(menu, variantes):
    with pytest.raises(InvalidVariantError):
        menu["coca"].replace_variants(variantes)


def test_reemplazar_las_variantes_conserva_las_que_siguen(db_session, menu):
    grande = menu["muzza"].variants[0]

    menu["muzza"].replace_variants([("Chica", 15000), ("Grande", 17000), ("Individual", 9000)])
    db_session.commit()

    assert [(v.name, v.price) for v in menu["muzza"].variants] == [("Chica", 15000), ("Grande", 17000), ("Individual", 9000)]
    assert menu["muzza"].variant_named("grande") is grande
    assert menu["muzza"].price == 9000


def test_subir_los_precios_tambien_sube_las_variantes(menu):
    menu["muzza"].scale_prices(1.1)

    assert [v.price for v in menu["muzza"].variants] == [17600, 15400]
    assert menu["muzza"].price == 15400


# --- Catálogo (panel) y menú público ----------------------------------------------------------------------


def test_crea_un_producto_con_variantes(client, menu):
    payload = {
        "name": "Fugazzeta",
        "description": "Cebolla y muzzarella.",
        "category_id": menu["muzza"].category_id,
        "variants": [{"name": " Grande ", "price": 24000}, {"name": "Chica", "price": 20000}],
    }

    response = client.post(PRODUCTS_URL, json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["price"] == 20000
    assert body["variants"] == [{"name": "Grande", "price": 24000}, {"name": "Chica", "price": 20000}]


def test_editar_un_producto_sin_variantes_se_las_quita(client, menu):
    payload = {
        "name": "Muzzarella",
        "description": "Salsa y muzzarella.",
        "category_id": menu["muzza"].category_id,
        "price": 15000,
    }

    response = client.put(f"{PRODUCTS_URL}/{menu['muzza'].id}", json=payload)

    assert response.status_code == 200
    assert response.json()["variants"] == []
    assert response.json()["price"] == 15000


@pytest.mark.parametrize(
    "extra",
    [{}, {"variants": [{"name": "Grande", "price": 1}, {"name": "GRANDE", "price": 2}]}],
)
def test_un_producto_necesita_precio_o_variantes_validas(client, menu, extra):
    payload = {"name": "Nueva", "description": "Algo.", "category_id": menu["muzza"].category_id, **extra}

    assert client.post(PRODUCTS_URL, json=payload).status_code == 422


def test_el_menu_publico_muestra_las_variantes(public_client, menu):
    productos = {p["name"]: p for p in public_client.get(MENU_URL).json()}

    assert productos["Muzzarella"]["variants"] == [{"name": "Grande", "price": 16000}, {"name": "Chica", "price": 14000}]
    assert productos["Coca-Cola"]["variants"] == []


# --- Pedidos web y de mostrador ---------------------------------------------------------------------------


def test_el_pedido_cobra_la_variante_elegida(public_client, db_session, menu):
    items = [
        {"product_id": menu["muzza"].id, "quantity": 2, "variant": "Grande"},
        {"product_id": menu["muzza"].id, "quantity": 1, "variant": "chica"},
        {"product_id": menu["coca"].id, "quantity": 1},
    ]

    response = public_client.post(WEB_ORDERS_URL, json=_pedido(items))

    assert response.status_code == 201
    body = response.json()
    assert body["total_amount"] == 2 * 16000 + 14000 + 2500
    assert {(i["product_name"], i["quantity"], i["unit_price"], i["variant_name"]) for i in body["items"]} == {
        ("Muzzarella (Grande)", 2, 16000, "Grande"),
        ("Muzzarella (Chica)", 1, 14000, "Chica"),
        ("Coca-Cola", 1, 2500, None),
    }


def test_las_lineas_de_la_misma_variante_se_suman(public_client, db_session, menu):
    items = [
        {"product_id": menu["muzza"].id, "quantity": 1, "variant": "Grande"},
        {"product_id": menu["muzza"].id, "quantity": 2, "variant": "GRANDE"},
    ]

    assert public_client.post(WEB_ORDERS_URL, json=_pedido(items)).status_code == 201

    [item] = db_session.query(OrderItem).all()
    assert (item.quantity, item.variant_name) == (3, "Grande")


@pytest.mark.parametrize("variante", [None, "Mediana"])
def test_rechaza_el_pedido_sin_una_variante_valida(public_client, db_session, menu, variante):
    items = [{"product_id": menu["muzza"].id, "quantity": 1, "variant": variante}]

    response = public_client.post(WEB_ORDERS_URL, json=_pedido(items))

    assert response.status_code == 400
    assert "Grande" in response.json()["detail"]
    assert db_session.query(Order).count() == 0


def test_la_variante_se_ignora_en_un_producto_que_no_tiene(public_client, menu):
    items = [{"product_id": menu["coca"].id, "quantity": 1, "variant": "Grande"}]

    response = public_client.post(WEB_ORDERS_URL, json=_pedido(items))

    assert response.status_code == 201
    assert response.json()["items"][0]["variant_name"] is None


def test_mitad_y_mitad_cobra_el_gusto_mas_caro_en_la_variante(public_client, menu):
    items = [
        {"product_id": menu["muzza"].id, "secondary_product_id": menu["napo"].id, "quantity": 1, "variant": "Chica"}
    ]

    response = public_client.post(WEB_ORDERS_URL, json=_pedido(items))

    assert response.status_code == 201
    [item] = response.json()["items"]
    assert item["unit_price"] == 17000
    assert item["product_name"] == "Pizza Chica [1/2 Muzzarella | 1/2 Napolitana]"


def test_la_comanda_muestra_la_variante(db_session, public_client, menu):
    items = [{"product_id": menu["milanesa"].id, "quantity": 1, "variant": "Pollo"}]
    public_client.post(WEB_ORDERS_URL, json=_pedido(items))

    [item] = db_session.query(OrderItem).all()
    assert item.comanda_display == "Milanesa Simple (Pollo)"


# --- Promociones -------------------------------------------------------------------------------------------


def test_una_promo_indica_la_variante_que_incluye(db_session, menu):
    promo = Promotion(name="3 Muzzarellas", price=42000)
    promo.set_products([(menu["muzza"], 3, "grande")])

    assert promo.items[0].variant_name == "Grande"
    assert promo.items[0].display_name == "Muzzarella (Grande)"
    assert promo.items[0].regular_price == 16000


def test_una_promo_con_un_producto_con_variantes_exige_la_variante(menu):
    with pytest.raises(Exception, match="variante"):
        Promotion(name="Muzza", price=1).set_products([(menu["muzza"], 1)])


def test_crea_una_promo_con_variantes_desde_el_panel(client, menu):
    payload = {
        "name": "3 Muzzarellas",
        "price": 42000,
        "items": [{"product_id": menu["muzza"].id, "quantity": 3, "variant_name": "Grande"}],
    }

    response = client.post("/api/v1/promotions", json=payload)

    assert response.status_code == 201
    assert response.json()["items"] == [
        {"product_id": menu["muzza"].id, "product_name": "Muzzarella", "quantity": 3, "variant_name": "Grande"}
    ]


# --- Bot ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [
        ("1 Muzzarella Grande", ("Muzzarella (Grande)", 16000.0, "Grande")),
        ("1 muzzarella chica", ("Muzzarella (Chica)", 14000.0, "Chica")),
        ("1 Milanesa Simple de Pollo", ("Milanesa Simple (Pollo)", 14000.0, "Pollo")),
        ("1 Napolitana de carne", ("Pizzaneza Napolitana (Carne)", 38000.0, "Carne")),
        ("1 Napolitana grande", ("Napolitana (Grande)", 19000.0, "Grande")),
    ],
)
def test_el_bot_entiende_la_variante_en_el_nombre(bot_session, menu, pedido, esperado):
    [item] = _calcular(pedido)["datos_temporales"]["items"]

    assert (item["nombre"], item["unit_price"], item["variant"]) == esperado


def test_el_bot_pregunta_la_variante_si_no_la_dijeron(bot_session, menu):
    respuesta = _respuesta("1 Muzzarella")

    assert "'Muzzarella' viene en Grande ($16,000.00) o Chica ($14,000.00). ¿Cuál querés?" in respuesta


def test_el_bot_pregunta_el_tamanio_de_la_mitad_y_mitad(bot_session, menu):
    respuesta = _respuesta("1 Pizza mitad muzzarella, mitad napolitana")

    assert "viene en Grande ($16,000.00) o Chica ($14,000.00). ¿Cuál querés?" in respuesta


def test_el_bot_cobra_la_mitad_y_mitad_en_el_tamanio_pedido(bot_session, menu):
    [item] = _calcular("1 Pizza Grande mitad muzzarella, mitad napolitana")["datos_temporales"]["items"]

    assert (item["unit_price"], item["variant"]) == (19000.0, "Grande")


def test_el_bot_registra_el_pedido_con_la_variante(bot_session, db_session, menu):
    datos = _calcular("2 Muzzarella Grande")["datos_temporales"]
    # El modelo de lenguaje a veces devuelve el pedido sin la variante: se recupera del nombre mostrado.
    for item in datos["items"]:
        item.pop("variant")
    datos.update(cliente="Ana", telefono="1155551234", metodo_entrega="retiro", metodo_pago="efectivo")

    confirmar_y_guardar_pedido.invoke({"datos_pedido_json": json.dumps(datos), "canal": "telegram", "chat_id": "1"})

    [item] = db_session.query(OrderItem).all()
    assert (item.variant_name, item.unit_price, item.quantity) == ("Grande", 16000, 2)


def test_el_bot_arma_la_promo_solo_con_la_variante_que_incluye(bot_session, db_session, menu):
    promo = Promotion(name="3 Muzzarellas", price=42000)
    promo.set_products([(menu["muzza"], 3, "Grande")])
    db_session.add(promo)
    db_session.commit()

    con_chicas = _calcular("3 Muzzarella Chica")["datos_temporales"]
    con_grandes = _calcular("3 Muzzarella Grande")["datos_temporales"]

    assert [i["nombre"] for i in con_chicas["items"]] == ["Muzzarella (Chica)"]
    assert [i["nombre"] for i in con_grandes["items"]] == ["3 Muzzarellas"]
    assert con_grandes["total"] == 42000


def test_el_menu_del_bot_muestra_el_precio_de_cada_variante(bot_session, menu):
    from app.services.tools import menu_tools

    with patch.object(menu_tools, "SessionLocal", TestingSessionLocal):
        texto = menu_tools.obtener_menu_actual()

    assert "- Muzzarella (Grande $16,000.00 / Chica $14,000.00) [Pizzas]" in texto
    assert "- Coca-Cola ($2,500.00) [Bebidas]" in texto
