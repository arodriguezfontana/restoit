"""Tests para el soporte de cupones de descuento en el bot (US-68)."""

import json
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.models.coupon import Coupon
from app.models.order import Order
from app.services.tools.order_tools import (
    calcular_y_preparar_pedido,
    confirmar_y_guardar_pedido,
)
from tests.conftest import TestingSessionLocal


@pytest.fixture(autouse=True)
def tools_session(db_session):
    with patch("app.services.tools.order_tools.SessionLocal", TestingSessionLocal):
        yield


def _calcular(**args) -> dict:
    return json.loads(calcular_y_preparar_pedido.invoke(args))


def _confirmar(datos: dict) -> str:
    return confirmar_y_guardar_pedido.invoke({"datos_pedido_json": json.dumps(datos)})


def test_calcular_pedido_con_cupon_valido(db_session, products):
    cupon = Coupon(code="PROMO20", discount_percentage=20, is_active=True)
    db_session.add(cupon)
    db_session.commit()

    respuesta = _calcular(
        items_solicitados="2 Pizza Muzzarella",
        customer_name="María",
        customer_phone="11 2233-4455",
        shipping_address="Av. Corrientes 1000",
        metodo_entrega="domicilio",
        metodo_pago="efectivo",
        cupon="promo20",
    )

    datos = respuesta["datos_temporales"]
    assert datos["cupon"] == "PROMO20"
    # 2 x 8500 = 17000. Con 20% OFF = 13600
    assert datos["total"] == 13600.0

    mensaje = respuesta["mensaje_para_usuario"]
    assert "Subtotal: $17,000.00" in mensaje
    assert "Descuento cupón (PROMO20 - 20% OFF): -$3,400.00" in mensaje
    assert "💰 Total: $13,600.00" in mensaje
    assert "⚠️ El cupón ingresado no es válido." not in mensaje


def test_calcular_pedido_con_cupon_invalido_o_inexistente(products):
    respuesta = _calcular(
        items_solicitados="2 Pizza Muzzarella",
        customer_name="María",
        customer_phone="11 2233-4455",
        shipping_address="Av. Corrientes 1000",
        metodo_entrega="domicilio",
        metodo_pago="efectivo",
        cupon="INVALIDO99",
    )

    datos = respuesta["datos_temporales"]
    assert datos["cupon"] is None
    assert datos["total"] == 17000.0

    mensaje = respuesta["mensaje_para_usuario"]
    assert "⚠️ El cupón ingresado no es válido." in mensaje
    assert "Subtotal:" not in mensaje
    assert "Descuento cupón" not in mensaje
    assert "💰 Total: $17,000.00" in mensaje


def test_calcular_pedido_con_cupon_pausado(db_session, products):
    cupon = Coupon(code="PAUSADO15", discount_percentage=15, is_active=False)
    db_session.add(cupon)
    db_session.commit()

    respuesta = _calcular(
        items_solicitados="2 Pizza Muzzarella",
        customer_name="María",
        customer_phone="11 2233-4455",
        shipping_address="Av. Corrientes 1000",
        metodo_entrega="domicilio",
        metodo_pago="efectivo",
        cupon="PAUSADO15",
    )

    datos = respuesta["datos_temporales"]
    assert datos["cupon"] is None
    assert datos["total"] == 17000.0

    mensaje = respuesta["mensaje_para_usuario"]
    assert "⚠️ El cupón ingresado no es válido." in mensaje
    assert "💰 Total: $17,000.00" in mensaje


def test_confirmar_pedido_con_cupon_valido_persiste_descuento_y_nota(db_session, products):
    cupon = Coupon(code="DESCUENTO10", discount_percentage=10, is_active=True)
    db_session.add(cupon)
    db_session.commit()

    calculo = _calcular(
        items_solicitados="2 Pizza Muzzarella",
        customer_name="Carlos",
        customer_phone="11 9988-7766",
        shipping_address="Mitre 500",
        metodo_entrega="domicilio",
        metodo_pago="efectivo",
        observaciones="timbre 1A",
        cupon="DESCUENTO10",
    )
    datos = calculo["datos_temporales"]
    assert datos["cupon"] == "DESCUENTO10"
    assert datos["total"] == 15300.0

    resultado = _confirmar(datos)
    assert "Recibimos tu pedido" in resultado

    order = db_session.query(Order).one()
    # Base: 17000, 10% OFF: 15300
    assert order.total_amount == Decimal("15300.00")
    assert "[Cupón aplicado: DESCUENTO10 (10% OFF - Ahorro: $1,700.00)]" in order.notes
    assert "timbre 1A" in order.notes


def test_recalcular_pedido_al_modificar_items_mantiene_cupon(db_session, products):
    cupon = Coupon(code="FIDELIDAD25", discount_percentage=25, is_active=True)
    db_session.add(cupon)
    db_session.commit()

    # Paso 1: 1 Pizza Muzzarella ($8,500)
    calculo1 = _calcular(
        items_solicitados="1 Pizza Muzzarella",
        customer_name="Lucas",
        customer_phone="11 3344-5566",
        shipping_address="San Martín 200",
        metodo_entrega="domicilio",
        metodo_pago="efectivo",
        cupon="FIDELIDAD25",
    )
    # 8500 * 0.75 = 6375
    assert calculo1["datos_temporales"]["total"] == 6375.0
    assert "Subtotal: $8,500.00" in calculo1["mensaje_para_usuario"]
    assert "Descuento cupón (FIDELIDAD25 - 25% OFF): -$2,125.00" in calculo1["mensaje_para_usuario"]
    assert "💰 Total: $6,375.00" in calculo1["mensaje_para_usuario"]

    # Paso 2: El cliente pide cambiar a 2 Pizzas Muzzarella ($17,000)
    calculo2 = _calcular(
        items_solicitados="2 Pizza Muzzarella",
        customer_name="Lucas",
        customer_phone="11 3344-5566",
        shipping_address="San Martín 200",
        metodo_entrega="domicilio",
        metodo_pago="efectivo",
        cupon="FIDELIDAD25",
    )
    # 17000 * 0.75 = 12750
    assert calculo2["datos_temporales"]["total"] == 12750.0
    assert "Subtotal: $17,000.00" in calculo2["mensaje_para_usuario"]
    assert "Descuento cupón (FIDELIDAD25 - 25% OFF): -$4,250.00" in calculo2["mensaje_para_usuario"]
    assert "💰 Total: $12,750.00" in calculo2["mensaje_para_usuario"]


def test_calcular_con_datos_faltantes_y_cupon_valido(db_session, products):
    cupon = Coupon(code="WEB10", discount_percentage=10, is_active=True)
    db_session.add(cupon)
    db_session.commit()

    # Faltan datos (sin dirección ni teléfono)
    respuesta = _calcular(
        items_solicitados="1 Pizza Muzzarella",
        cupon="WEB10",
    )
    datos = respuesta["datos_temporales"]
    assert datos["faltan_datos"] is True
    assert datos["cupon"] == "WEB10"
    assert datos["total"] == 7650.0

    mensaje = respuesta["mensaje_para_usuario"]
    assert "Subtotal: $8,500.00" in mensaje
    assert "Descuento cupón (WEB10 - 10% OFF): -$850.00" in mensaje
    assert "Total: $7,650.00" in mensaje


def test_calcular_con_datos_faltantes_y_cupon_invalido(products):
    respuesta = _calcular(
        items_solicitados="1 Pizza Muzzarella",
        cupon="EXPIRADO",
    )
    datos = respuesta["datos_temporales"]
    assert datos["faltan_datos"] is True
    assert datos["cupon"] is None
    assert datos["total"] == 8500.0

    mensaje = respuesta["mensaje_para_usuario"]
    assert "⚠️ El cupón ingresado no es válido." in mensaje
    assert "Total: $8,500.00" in mensaje
