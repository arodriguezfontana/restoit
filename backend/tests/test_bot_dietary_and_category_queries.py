"""Pruebas de US-64: Consultas de carta por restricciones alimenticias y categorías específicas en el chatbot."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.models.menu import Category, Product
from app.services.chat_memory import SesionChat
from app.services.chat_service import ChatService
from app.services.tools.menu_tools import obtener_menu_actual
from tests.conftest import TestingSessionLocal


class LLM:
    def __init__(self, *respuestas: AIMessage):
        self.respuestas = list(respuestas)
        self.llamadas = 0
        self.mensajes_recibidos = []

    def bind_tools(self, _herramientas):
        return self

    async def ainvoke(self, mensajes):
        self.llamadas += 1
        self.mensajes_recibidos.append(mensajes)
        return self.respuestas.pop(0)


@pytest.fixture()
def menu_con_categorias_y_restricciones(db_session):
    cat_pizzas = Category(name="Pizzas")
    cat_pastas = Category(name="Pastas")
    cat_bebidas = Category(name="Bebidas")
    cat_postres = Category(name="Postres")
    db_session.add_all([cat_pizzas, cat_pastas, cat_bebidas, cat_postres])
    db_session.flush()

    p1 = Product(
        name="Pizza Muzzarella",
        description="Salsa de tomate y muzzarella",
        price=8500.0,
        category_id=cat_pizzas.id,
        dietary_restrictions=["vegetariano"],
    )
    p2 = Product(
        name="Pizza Vegana Especial",
        description="Queso de almendras y vegetales asados",
        price=9500.0,
        category_id=cat_pizzas.id,
        dietary_restrictions=["vegano", "vegetariano"],
    )
    p3 = Product(
        name="Ñoquis de Papa Sin TACC",
        description="Con salsa fileto artesanal",
        price=9000.0,
        category_id=cat_pastas.id,
        dietary_restrictions=["sin TACC", "celíaco", "vegetariano"],
    )
    p4 = Product(
        name="Limonada con Menta",
        description="500ml natural",
        price=2200.0,
        category_id=cat_bebidas.id,
        dietary_restrictions=["vegano", "sin TACC"],
    )
    p5 = Product(
        name="Tiramisú Clásico",
        description="Café y mascarpone",
        price=3500.0,
        category_id=cat_postres.id,
        dietary_restrictions=["vegetariano"],
    )
    p6 = Product(
        name="Calabresa Tradicional",
        description="Con longaniza",
        price=9200.0,
        category_id=cat_pizzas.id,
        dietary_restrictions=[],
    )
    db_session.add_all([p1, p2, p3, p4, p5, p6])
    db_session.commit()
    return {
        "pizzas": cat_pizzas,
        "pastas": cat_pastas,
        "bebidas": cat_bebidas,
        "postres": cat_postres,
    }


def test_obtener_menu_actual_incluye_restricciones_y_categoria(menu_con_categorias_y_restricciones):
    with patch("app.services.tools.menu_tools.SessionLocal", TestingSessionLocal):
        menu = obtener_menu_actual()

    # Formato con categoría y restricciones si las tiene
    assert "- Pizza Muzzarella ($8,500.00) [Pizzas] [Apto: vegetariano]: Salsa de tomate y muzzarella" in menu
    assert "- Pizza Vegana Especial ($9,500.00) [Pizzas] [Apto: vegano, vegetariano]: Queso de almendras y vegetales asados" in menu
    assert "- Ñoquis de Papa Sin TACC ($9,000.00) [Pastas] [Apto: sin TACC, celíaco, vegetariano]: Con salsa fileto artesanal" in menu
    assert "- Limonada con Menta ($2,200.00) [Bebidas] [Apto: vegano, sin TACC]: 500ml natural" in menu
    assert "- Tiramisú Clásico ($3,500.00) [Postres] [Apto: vegetariano]: Café y mascarpone" in menu
    # Producto sin restricciones no muestra corchete de Apto
    assert "- Calabresa Tradicional ($9,200.00) [Pizzas]: Con longaniza" in menu
    assert "[Apto:" not in [line for line in menu.splitlines() if "Calabresa Tradicional" in line][0]


def test_system_prompt_contiene_instrucciones_de_categorias_y_restricciones():
    servicio = ChatService(llm=MagicMock())
    prompt = servicio.system_prompt

    # Criterio 1: Restricciones alimenticias
    assert "Consultas por restricciones alimenticias" in prompt
    assert "celíaco / sin TACC, vegetariano, vegano" in prompt
    assert "[Apto: ...]" in prompt
    assert "no disponen de opciones para dicha restricción" in prompt

    # Criterio 2: Categorías de la carta sin enviar imagen general
    assert "Consultas de categorías específicas" in prompt
    assert "bebidas, postres, pizzas, pastas, empanadas" in prompt
    assert 'NO uses la herramienta "enviar_menu_en_imagen"' in prompt

    # Criterio 3: Preservación del pedido
    assert "Preservación del pedido" in prompt
    assert "no debe alterar ni reiniciar los ítems o datos que el cliente ya haya seleccionado" in prompt

    # Criterio 4: Integridad del rol contra temas fuera de contexto
    assert "INTEGRIDAD DEL ROL" in prompt
    assert "deportes, noticias, cultura general, programación" in prompt


def test_consulta_por_restriccion_alimenticia_recibe_menu_con_apto_y_responde_en_texto(menu_con_categorias_y_restricciones):
    respuesta_esperada = "🌿 Opciones aptas para celíacos / sin TACC: Ñoquis de Papa Sin TACC ($9,000.00) y Limonada con Menta ($2,200.00)."
    llm = LLM(AIMessage(content=respuesta_esperada))
    servicio = ChatService(llm=llm)

    with patch("app.services.tools.menu_tools.SessionLocal", TestingSessionLocal):
        respuesta = asyncio.run(
            servicio.obtener_respuesta("¿Tienen opciones sin TACC o para celíacos?", session_id="whatsapp:5491100001111")
        )

    assert respuesta == respuesta_esperada
    assert llm.llamadas == 1
    # Verifica que el SystemMessage pasado a Gemini contenga las etiquetas [Apto: ...] para que pueda responder
    mensajes = llm.mensajes_recibidos[0]
    prompt_sistema = mensajes[0].content
    assert "[Apto: sin TACC, celíaco, vegetariano]" in prompt_sistema
    assert "[Apto: vegano, sin TACC]" in prompt_sistema


def test_consulta_por_categoria_especifica_responde_en_texto_sin_usar_herramientas(menu_con_categorias_y_restricciones):
    respuesta_esperada = "🍹 De bebidas tenemos Limonada con Menta ($2,200.00). ¿Te gustaría sumar alguna?"
    llm = LLM(AIMessage(content=respuesta_esperada))
    servicio = ChatService(llm=llm)

    with patch("app.services.tools.menu_tools.SessionLocal", TestingSessionLocal):
        respuesta = asyncio.run(
            servicio.obtener_respuesta("¿Qué tienen para tomar?", session_id="whatsapp:5491100001111")
        )

    assert respuesta == respuesta_esperada
    assert llm.llamadas == 1
    # No llamó a ninguna herramienta (ni enviar_menu_en_imagen ni calcular_y_preparar_pedido)
    sesion = servicio.sesiones["whatsapp:5491100001111"]
    assert not any(hasattr(m, "tool_calls") and m.tool_calls for m in sesion.historial)


def test_consulta_de_restriccion_o_categoria_preserva_pedido_en_curso(menu_con_categorias_y_restricciones):
    servicio = ChatService(llm=MagicMock())
    session_id = "whatsapp:5491100002222"
    sesion = SesionChat()
    sesion.cliente = {"nombre": "Laura", "telefono": "1199998888", "direccion": "San Martín 123"}
    sesion.pedido_en_curso = {
        "items": [{"nombre": "Pizza Muzzarella", "quantity": 1, "unit_price": 8500.0}],
        "total": 8500.0,
        "metodo_entrega": "delivery",
    }
    servicio.sesiones[session_id] = sesion

    # El cliente consulta por postres en el medio de la conversación
    respuesta_postres = "🍰 De postres te ofrecemos Tiramisú Clásico ($3,500.00). ¿Querés agregar uno a tu pedido?"
    llm = LLM(AIMessage(content=respuesta_postres))
    servicio._llms = servicio._crear_modelos(llm)
    servicio._orden_de_modelos = lambda: ["inyectado"]

    with patch("app.services.tools.menu_tools.SessionLocal", TestingSessionLocal):
        respuesta = asyncio.run(
            servicio.obtener_respuesta("¿Y qué postres tienen?", session_id=session_id)
        )

    assert respuesta == respuesta_postres
    # El pedido en curso y los datos del cliente se mantuvieron intactos
    assert sesion.pedido_en_curso is not None
    assert sesion.pedido_en_curso["items"][0]["nombre"] == "Pizza Muzzarella"
    assert sesion.cliente["nombre"] == "Laura"
    assert "PEDIDO EN CURSO (1x Pizza Muzzarella)" in sesion.texto_memoria()


def test_consulta_fuera_de_contexto_se_rechaza_cordialmente():
    respuesta_esperada = "Disculpá, solo puedo ayudarte con información del menú, precios, horarios y pedidos del restaurante. ¿Te gustaría consultar nuestra carta?"
    llm = LLM(AIMessage(content=respuesta_esperada))
    servicio = ChatService(llm=llm)

    respuesta = asyncio.run(
        servicio.obtener_respuesta("¿Quién salió campeón del mundial 2022?", session_id="whatsapp:5491100003333")
    )

    assert respuesta == respuesta_esperada
    assert llm.llamadas == 1
    # Ninguna herramienta del sistema fue invocada
    sesion = servicio.sesiones["whatsapp:5491100003333"]
    assert sesion.pedido_en_curso is None
