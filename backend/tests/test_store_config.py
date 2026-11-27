from unittest.mock import patch

CONFIG_URL = "/api/v1/store-config"


def test_public_get_store_config_returns_default(public_client):
    response = public_client.get(CONFIG_URL)
    assert response.status_code == 200
    data = response.json()
    assert data["store_name"] == "RestoIT"
    assert data["theme_color"] == "black"
    assert data["login_bg"] == "bistro"
    assert "address" in data
    assert "opening_hours" not in data
    assert data["login_bg_image"] is None
    assert "contact_phone" in data


def test_modify_store_config_requires_admin(public_client):
    payload = {
        "store_name": "Pizzería Nápoles",
        "address": "Av. Corrientes 500",
        "contact_phone": "11 5555-4321",
        "logo_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "theme_color": "red",
        "login_bg": "kitchen",
    }
    response = public_client.put(CONFIG_URL, json=payload)
    assert response.status_code == 401


def test_admin_can_update_store_config(client, public_client):
    payload = {
        "store_name": "Pizzería Bella Vista",
        "address": "Calle Falsa 123",
        "contact_phone": "11 9999-8888",
        "logo_url": "data:image/png;base64,test-logo-base64",
        "theme_color": "emerald",
        "login_bg": "trattoria",
        "mp_alias": "bellavista.mp",
    }
    response = client.put(CONFIG_URL, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["store_name"] == "Pizzería Bella Vista"
    assert data["address"] == "Calle Falsa 123"
    assert data["contact_phone"] == "11 9999-8888"
    assert data["logo_url"] == "data:image/png;base64,test-logo-base64"
    assert data["theme_color"] == "emerald"
    assert data["login_bg"] == "trattoria"
    assert data["mp_alias"] == "bellavista.mp"

    # Inmediatamente visible para clientes sin autenticación
    pub_res = public_client.get(CONFIG_URL)
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["store_name"] == "Pizzería Bella Vista"
    assert pub_data["theme_color"] == "emerald"
    assert pub_data["login_bg"] == "trattoria"
    assert pub_data["logo_url"] == "data:image/png;base64,test-logo-base64"
    assert pub_data["mp_alias"] == "bellavista.mp"


def test_update_store_config_validates_theme_color(client):
    payload = {
        "store_name": "Pizzería Central",
        "address": "Av. Siempre Viva 742",
        "contact_phone": "11 1111-2222",
        "logo_url": None,
        "theme_color": "color_invalido",
    }
    response = client.put(CONFIG_URL, json=payload)
    assert response.status_code == 422


def test_update_store_config_validates_store_name(client):
    payload = {
        "store_name": "   ",
        "theme_color": "blue",
    }
    response = client.put(CONFIG_URL, json=payload)
    assert response.status_code == 422


def test_update_store_config_validates_login_bg(client):
    payload = {
        "store_name": "Pizzería Central",
        "theme_color": "blue",
        "login_bg": "pizza",
    }
    response = client.put(CONFIG_URL, json=payload)
    assert response.status_code == 422


def test_admin_can_upload_custom_login_background(client, public_client):
    image = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ=="
    response = client.put(
        CONFIG_URL,
        json={"store_name": "RestoIT", "theme_color": "black", "login_bg": "custom", "login_bg_image": image},
    )
    assert response.status_code == 200

    pub_data = public_client.get(CONFIG_URL).json()
    assert pub_data["login_bg"] == "custom"
    assert pub_data["login_bg_image"] == image


def test_custom_login_background_requires_an_image(client):
    response = client.put(CONFIG_URL, json={"store_name": "RestoIT", "theme_color": "black", "login_bg": "custom"})
    assert response.status_code == 422


def test_login_background_image_must_be_an_image_data_url(client):
    response = client.put(
        CONFIG_URL,
        json={"store_name": "RestoIT", "theme_color": "black", "login_bg": "custom", "login_bg_image": "https://x.com/a.js"},
    )
    assert response.status_code == 422


def test_admin_can_update_custom_hex_theme_color(client, public_client):
    payload = {
        "store_name": "Pizzería Colorida",
        "theme_color": "#a855f7",
    }
    response = client.put(CONFIG_URL, json=payload)
    assert response.status_code == 200
    assert response.json()["theme_color"] == "#a855f7"

    pub_res = public_client.get(CONFIG_URL)
    assert pub_res.status_code == 200
    assert pub_res.json()["theme_color"] == "#a855f7"


# --- Fondo del panel de administración ---

BASE = {"store_name": "RestoIT", "theme_color": "black"}


def test_el_panel_arranca_sin_fondo(public_client):
    data = public_client.get(CONFIG_URL).json()

    assert data["panel_bg"] == "none"
    assert data["panel_bg_image"] is None


def test_el_dueno_elige_una_imagen_de_fondo_para_el_panel(client, public_client):
    response = client.put(CONFIG_URL, json={**BASE, "panel_bg": "kitchen"})

    assert response.status_code == 200
    assert public_client.get(CONFIG_URL).json()["panel_bg"] == "kitchen"


def test_el_dueno_elige_un_color_liso_para_el_panel(client, public_client):
    response = client.put(CONFIG_URL, json={**BASE, "panel_bg": "color", "panel_bg_color": "#334155"})

    assert response.status_code == 200
    data = public_client.get(CONFIG_URL).json()
    assert (data["panel_bg"], data["panel_bg_color"]) == ("color", "#334155")


def test_el_color_del_panel_exige_elegir_el_color_y_ser_un_hex_valido(client):
    assert client.put(CONFIG_URL, json={**BASE, "panel_bg": "color"}).status_code == 422
    for invalido in ("rojo", "#fff", "#12345g", "334155"):
        respuesta = client.put(CONFIG_URL, json={**BASE, "panel_bg": "color", "panel_bg_color": invalido})
        assert respuesta.status_code == 422


def test_el_fondo_del_panel_es_independiente_del_del_login(client, public_client):
    client.put(CONFIG_URL, json={**BASE, "login_bg": "trattoria", "panel_bg": "bistro"})

    data = public_client.get(CONFIG_URL).json()
    assert (data["login_bg"], data["panel_bg"]) == ("trattoria", "bistro")


def test_el_dueno_sube_una_imagen_propia_para_el_panel(client, public_client):
    image = "data:image/png;base64,iVBORw0KGgo="
    response = client.put(CONFIG_URL, json={**BASE, "panel_bg": "custom", "panel_bg_image": image})

    assert response.status_code == 200
    data = public_client.get(CONFIG_URL).json()
    assert (data["panel_bg"], data["panel_bg_image"]) == ("custom", image)


def test_volver_al_fondo_liso(client, public_client):
    client.put(CONFIG_URL, json={**BASE, "panel_bg": "bistro"})

    client.put(CONFIG_URL, json={**BASE, "panel_bg": "none"})

    assert public_client.get(CONFIG_URL).json()["panel_bg"] == "none"


def test_el_fondo_propio_del_panel_exige_una_imagen(client):
    assert client.put(CONFIG_URL, json={**BASE, "panel_bg": "custom"}).status_code == 422


def test_el_fondo_del_panel_tiene_que_ser_una_opcion_valida_con_imagen_data_url(client):
    assert client.put(CONFIG_URL, json={**BASE, "panel_bg": "pizza"}).status_code == 422
    invalida = {**BASE, "panel_bg": "custom", "panel_bg_image": "https://x.com/a.js"}
    assert client.put(CONFIG_URL, json=invalida).status_code == 422


# --- Fondo del menú público ---


def test_el_menu_arranca_sin_fondo(public_client):
    data = public_client.get(CONFIG_URL).json()

    assert (data["menu_bg"], data["menu_bg_image"], data["menu_bg_color"]) == ("none", None, None)


def test_el_dueno_elige_el_fondo_del_menu_sin_tocar_el_del_panel(client, public_client):
    client.put(CONFIG_URL, json={**BASE, "panel_bg": "bistro", "menu_bg": "color", "menu_bg_color": "#334155"})

    data = public_client.get(CONFIG_URL).json()
    assert (data["panel_bg"], data["menu_bg"], data["menu_bg_color"]) == ("bistro", "color", "#334155")


def test_el_dueno_sube_una_imagen_propia_para_el_menu(client, public_client):
    image = "data:image/png;base64,iVBORw0KGgo="
    response = client.put(CONFIG_URL, json={**BASE, "menu_bg": "custom", "menu_bg_image": image})

    assert response.status_code == 200
    assert public_client.get(CONFIG_URL).json()["menu_bg_image"] == image


def test_el_fondo_del_menu_exige_su_imagen_o_color_y_valores_validos(client):
    assert client.put(CONFIG_URL, json={**BASE, "menu_bg": "custom"}).status_code == 422
    assert client.put(CONFIG_URL, json={**BASE, "menu_bg": "color"}).status_code == 422
    assert client.put(CONFIG_URL, json={**BASE, "menu_bg": "pizza"}).status_code == 422
    invalida = {**BASE, "menu_bg": "custom", "menu_bg_image": "https://x.com/a.js"}
    assert client.put(CONFIG_URL, json=invalida).status_code == 422


# --- Medios de pago (US-59) ---


def _config(**overrides) -> dict:
    return {"store_name": "Local", **overrides}


def test_por_defecto_solo_se_acepta_efectivo_en_la_config_guardada_sin_medios(client):
    response = client.put(CONFIG_URL, json=_config())

    data = response.json()
    assert response.status_code == 200
    assert (data["accepts_cash"], data["accepts_transfer"], data["accepts_card"], data["accepts_mercadopago"]) == (
        True,
        False,
        False,
        False,
    )


def test_transferencia_requiere_alias_o_cbu_y_titular(client):
    sin_datos = client.put(CONFIG_URL, json=_config(accepts_transfer=True))
    sin_titular = client.put(CONFIG_URL, json=_config(accepts_transfer=True, transfer_alias="mi.alias"))
    con_alias = client.put(
        CONFIG_URL, json=_config(accepts_transfer=True, transfer_alias="mi.alias", transfer_holder="Ana Pérez")
    )
    con_cbu = client.put(
        CONFIG_URL, json=_config(accepts_transfer=True, transfer_cbu="0000003100012345678901", transfer_holder="Ana")
    )

    assert sin_datos.status_code == 422
    assert sin_titular.status_code == 422
    assert con_alias.status_code == 200
    assert con_alias.json()["transfer_holder"] == "Ana Pérez"
    assert con_cbu.status_code == 200


def test_tarjeta_guarda_a_que_pedidos_aplica(client):
    response = client.put(CONFIG_URL, json=_config(accepts_card=True, card_applies_to="delivery"))
    invalida = client.put(CONFIG_URL, json=_config(accepts_card=True, card_applies_to="siempre"))

    assert response.json()["card_applies_to"] == "delivery"
    assert invalida.status_code == 422


def test_mercadopago_solo_se_activa_con_credenciales(client):
    with patch("app.schemas.store_config_schemas.mercadopago_configured", return_value=False):
        sin_credenciales = client.put(CONFIG_URL, json=_config(accepts_mercadopago=True))
    with patch("app.schemas.store_config_schemas.mercadopago_configured", return_value=True):
        con_credenciales = client.put(CONFIG_URL, json=_config(accepts_mercadopago=True))

    assert sin_credenciales.status_code == 422
    assert con_credenciales.status_code == 200
    assert con_credenciales.json()["accepts_mercadopago"] is True


def test_siempre_queda_al_menos_un_medio_activo(client):
    response = client.put(CONFIG_URL, json=_config(accepts_cash=False))

    assert response.status_code == 422
    assert "al menos un medio" in response.text


def test_la_config_publica_informa_si_hay_credenciales_de_mercadopago(public_client):
    with patch("app.api.store_config_router.mercadopago_configured", return_value=True):
        assert public_client.get(CONFIG_URL).json()["mercadopago_available"] is True
    with patch("app.api.store_config_router.mercadopago_configured", return_value=False):
        assert public_client.get(CONFIG_URL).json()["mercadopago_available"] is False
