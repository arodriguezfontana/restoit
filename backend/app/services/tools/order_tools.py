"""Tools de LangChain para analizar, calcular y persistir pedidos de forma exacta.

Son la "capa de entrada" del bot (como los routers para la API): interpretan lo que arma el modelo de
lenguaje y le devuelven textos para el cliente, pero las reglas del pedido y el acceso a la base quedan en
los servicios y el modelo, iguales para todos los canales.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Annotated, cast

from langchain_core.tools import InjectedToolArg, tool
from sqlalchemy.orm import Session

from app.core.channels import Channel
from app.core.money import to_money
from app.core.phone import normalize_phone
from app.core.text import sin_acentos
from app.core.time import ahora_local
from app.db.session import SessionLocal
from app.models.menu import Product
from app.models.order import (
    MAX_QUANTITY_PER_ITEM,
    PICKUP_ADDRESS,
    BusinessRuleError,
    DeliveryMethod,
    InvalidOrderError,
    PaymentMethod,
    clean_pizza_flavor,
    modifications_extra_cost,
)
from app.models.promotion import Promotion
from app.repositories import promotion_repository
from app.schemas.common import PHONE_PATTERN
from app.services import coupon_service, printer_service
from app.services.business_hours_service import (
    DIAS_SEMANA,
    Franja,
    describir_horarios,
    describir_momento,
    esta_abierto,
    obtener_franjas,
    proxima_apertura,
    proxima_fecha_abierta_a_la_hora,
)
from app.services.catalog_service import find_available_products_by_name
from app.services.mercadopago_service import start_chat_payment
from app.services.modifier_nlp import (
    extraer_modificadores_de_texto,
    filtrar_modificadores_para_producto,
    vincular_modificadores_con_db,
)
from app.services.order_service import OrderRequest, ScheduleTooEarlyError, create_bot_order, validate_schedule
from app.services.payment_methods_service import PAYMENT_LABELS, accepted_payment_methods, transfer_instructions
from app.services.store_config_service import get_or_create_store_config

logger = logging.getLogger(__name__)

# Margen para no rechazar al confirmar un horario que era válido cuando se le propuso al cliente
# y quedó apenas por debajo del mínimo por el tiempo que pasó en la conversación.
TOLERANCIA_CONFIRMACION_MINUTOS = 5

MAX_LARGO_OBSERVACIONES = 500
MAX_ITEMS_EN_PEDIDO = 50
MAX_LARGO_CLIENTE = 100
MAX_LARGO_DIRECCION = 255
MAX_LARGO_TELEFONO = 30

# Con cuántos días de anticipación se puede programar un pedido.
MAX_DIAS_PROGRAMACION = 7

# Frase del mensaje de éxito de confirmar_y_guardar_pedido: el chat la usa para saber que el pedido se registró.
MARCA_PEDIDO_REGISTRADO = "Recibimos tu pedido"

_PATRON_HORA = re.compile(r"(\d{1,2})(?:\s*[:.h]?\s*(\d{2}))?", re.IGNORECASE)
_PATRON_FECHA_DIA_MES = re.compile(r"(\d{1,2})/(\d{1,2})")
_PATRON_PREFIJO_PIZZA = re.compile(r"^(?:pizza(?:s)?\s+)?(?:de\s+)?", re.IGNORECASE)
_PATRON_MITAD_ENTRE_CORCHETES = re.compile(r"^(.*?)\s*\[\s*1/2\s+(.*?)\s*\|\s*1/2\s+(.*?)\s*\]$", re.IGNORECASE)
_PATRON_MITAD_EN_LENGUAJE_NATURAL = re.compile(
    r"^(.*?)\s*(?:mitad|1/2|media)\s+(?:de\s+)?(.*?)\s*(?:,|y|\/|\||-|\s+)\s*(?:mitad|1/2|media)\s+(?:de\s+)?(.*?)$",
    re.IGNORECASE,
)
_PATRON_COMA_ENTRE_MITADES = re.compile(r",\s*(?=(?:mitad|1/2|media)\b)", re.IGNORECASE)
_PATRON_CANTIDAD_NUMERICA = re.compile(r"^(\d+)\s*(?:x|-)?\s*(.+)$", re.IGNORECASE)
_PATRON_CANTIDAD_EN_PALABRAS = re.compile(r"^(una?|dos|tres|cuatro|cinco)\s+(.+)$", re.IGNORECASE)
_CANTIDADES_EN_PALABRAS = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}

_ACLARACION_MODIFICACIONES = (
    "ℹ️ Aclaración: Las modificaciones y adicionales se realizan según los ingredientes y adicionales "
    "permitidos de cada plato."
)


# --- Interpretación de textos sueltos ---------------------------------------------------------------------


_PATRONES_DE_PAGO = (
    (r"mercado|\bmp\b", PaymentMethod.MERCADOPAGO),
    (r"transf|\bcbu\b|\bcvu\b|alias|home ?banking", PaymentMethod.TRANSFER),
    (r"tarj|debit|credit|\bdeb\b|\bcred\b|\bcard\b|posnet|\bvisa\b|master", PaymentMethod.CARD),
    (r"link|digital|\bqr\b", PaymentMethod.MERCADOPAGO),
    (r"efectivo|cash|pesos|billete|contado", PaymentMethod.CASH),
)


def normalizar_metodo_pago(metodo: str | None) -> str | None:
    """Medio de pago ('efectivo', 'transferencia', 'tarjeta' o 'mercadopago') al que se refiere el texto, o None si no es reconocible."""
    if not metodo:
        return None
    texto = sin_acentos(str(metodo).strip().lower())
    # Se reconocen las variantes del habla ("transfe", "con tarjeta", "débito", "crédito"...).
    for patron, medio in _PATRONES_DE_PAGO:
        if re.search(patron, texto):
            return medio.value
    return None


def _parsear_hora(hora_str: str) -> time | None:
    """Interpreta horarios como '21', '21:30', '21.30hs', '21h30' o '2130'."""
    match = _PATRON_HORA.search(hora_str)
    if not match:
        return None
    horas, minutos = int(match.group(1)), int(match.group(2) or 0)
    if horas > 23 or minutos > 59:
        return None
    return time(horas, minutos)


def _parsear_dia(dia_str: str, hoy: date) -> date | None:
    """Interpreta 'hoy', 'mañana', 'pasado mañana', un día de la semana, '17/10' o '2026-10-17'."""
    texto = sin_acentos(dia_str.strip().lower())
    try:
        return date.fromisoformat(texto)
    except ValueError:
        pass
    return _dia_relativo(texto, hoy) or _dia_de_la_semana(texto, hoy) or _dia_y_mes(texto, hoy)


def _dia_relativo(texto: str, hoy: date) -> date | None:
    if "pasado manana" in texto:
        return hoy + timedelta(days=2)
    if "manana" in texto:
        return hoy + timedelta(days=1)
    if "hoy" in texto:
        return hoy
    return None


def _dia_de_la_semana(texto: str, hoy: date) -> date | None:
    """Próxima fecha (hoy incluido) del día de la semana nombrado en el texto."""
    numeros = [numero for numero, nombre in enumerate(DIAS_SEMANA) if sin_acentos(nombre) in texto]
    return hoy + timedelta(days=(numeros[0] - hoy.weekday()) % 7) if numeros else None


def _dia_y_mes(texto: str, hoy: date) -> date | None:
    """Fecha con formato 'día/mes': este año o, si ya pasó, el próximo."""
    match = _PATRON_FECHA_DIA_MES.search(texto)
    if not match:
        return None
    try:
        fecha = date(hoy.year, int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None
    return fecha if fecha >= hoy else fecha.replace(year=hoy.year + 1)


def _telefono_valido(telefono: str | None) -> bool:
    """Mismo criterio que los pedidos de la web y del mostrador."""
    return bool(telefono) and 6 <= len(telefono) <= MAX_LARGO_TELEFONO and re.match(PHONE_PATTERN, telefono) is not None


def _recortar(texto: str | None, largo_maximo: int) -> str | None:
    return (texto or "").strip()[:largo_maximo] or None


# --- Horario del pedido -----------------------------------------------------------------------------------


def _texto_horarios(franjas: list[Franja]) -> str:
    return "\n".join(f"- {linea}" for linea in describir_horarios(franjas))


def _aviso_local_cerrado(franjas: list[Franja], ahora: datetime) -> str:
    apertura = proxima_apertura(franjas, ahora)
    vuelve = f" Volvemos a abrir {describir_momento(apertura, ahora, con_fecha=False)}." if apertura else ""
    return (
        f"🔒 En este momento el local está cerrado, así que no podemos prepararlo para ahora.{vuelve}\n\n"
        f"🕒 Nuestros horarios de atención:\n{_texto_horarios(franjas)}\n\n"
        "Si querés, lo programamos para un horario en el que estemos abiertos: ¿para qué día y hora te lo preparamos?"
    )


def _aviso_local_cerrado_en(franjas: list[Franja], solicitado: datetime, ahora: datetime) -> str:
    return (
        f"El local está cerrado {describir_momento(solicitado, ahora)}, "
        "así que no podemos programarlo para ese horario.\n\n"
        f"🕒 Nuestros horarios de atención:\n{_texto_horarios(franjas)}\n\n"
        "¿Para qué otro horario querés programarlo?"
    )


def _aviso_demora_excedida(
    error: ScheduleTooEarlyError, franjas: list[Franja], solicitado: datetime, ahora: datetime
) -> str:
    if not esta_abierto(franjas, ahora) or not esta_abierto(franjas, error.earliest):
        # Lo más rápido posible cae fuera del horario: no se puede ofrecer ni esa hora ni "para ahora".
        return (
            f"Con la demora actual (unos {error.delay_minutes} minutos) no llegamos a tenerlo a las "
            f"{solicitado:%H:%M}. ¿Para qué otro horario querés programarlo?"
        )
    return (
        f"Con la demora actual (unos {error.delay_minutes} minutos), lo más rápido que podemos tener tu pedido "
        f"es a las {error.earliest:%H:%M}. ¿Querés programarlo para esa hora o preferís pedirlo para ahora?"
    )


def _momento_solicitado(franjas: list[Franja], ahora: datetime, hora: time, dia_str: str | None) -> datetime | None:
    """Fecha y hora pedidas por el cliente; None si el día indicado no se entiende."""
    if dia_str and dia_str.strip():
        fecha = _parsear_dia(dia_str, ahora.date())
        return None if fecha is None else datetime.combine(fecha, hora, tzinfo=ahora.tzinfo)
    solicitado = datetime.combine(ahora.date(), hora, tzinfo=ahora.tzinfo)
    # Sin día indicado, si hoy a esa hora el local no abre (o ya pasó y ahora está cerrado),
    # se toma el próximo día en que sí abre a esa hora (ej. a la noche, "para las 13" es mañana).
    if not esta_abierto(franjas, solicitado) or (solicitado < ahora and not esta_abierto(franjas, ahora)):
        return (
            proxima_fecha_abierta_a_la_hora(franjas, ahora.date(), hora, ahora.tzinfo, MAX_DIAS_PROGRAMACION)
            or solicitado
        )
    return solicitado


def _evaluar_hora_programada(
    db: Session, hora_str: str | None, dia_str: str | None = None, tolerancia_minutos: int = 0
) -> tuple[datetime | None, str | None]:
    """Interpreta el horario pedido en la zona horaria del local y verifica que se pueda cumplir:
    que el local esté abierto a esa hora y que se llegue a preparar con la demora actual.

    Devuelve el horario programado (None si el pedido es para ahora) o, si no se puede cumplir,
    el mensaje a transmitirle al cliente.
    """
    ahora = ahora_local()
    franjas = obtener_franjas(db)

    if not hora_str or not re.search(r"\d", hora_str):
        return None, None if esta_abierto(franjas, ahora) else _aviso_local_cerrado(franjas, ahora)

    hora = _parsear_hora(hora_str)
    if hora is None:
        return None, f"No entendí el horario '{hora_str}'. ¿Me lo indicás como HH:MM (por ejemplo, 21:30)?"

    solicitado = _momento_solicitado(franjas, ahora, hora, dia_str)
    if solicitado is None:
        return None, (
            f"No entendí para qué día es el pedido ('{dia_str}'). "
            "¿Me lo indicás (por ejemplo, hoy, mañana o el sábado)?"
        )
    if solicitado.date() > ahora.date() + timedelta(days=MAX_DIAS_PROGRAMACION):
        return None, f"Solo podemos programar pedidos con hasta {MAX_DIAS_PROGRAMACION} días de anticipación."
    if not esta_abierto(franjas, solicitado):
        return None, _aviso_local_cerrado_en(franjas, solicitado, ahora)

    try:
        validate_schedule(db, solicitado, now=ahora, tolerance_minutes=tolerancia_minutos)
    except ScheduleTooEarlyError as exc:
        return None, _aviso_demora_excedida(exc, franjas, solicitado, ahora)
    return solicitado, None


def describir_horario_programado(programado: datetime | None, ahora: datetime) -> str:
    if programado is None:
        return "para ahora"
    if programado.date() == ahora.date():
        return f"para las {programado:%H:%M}"
    return f"para {describir_momento(programado, ahora)}"


# --- Ítems que arma el modelo de lenguaje -----------------------------------------------------------------


def _id_opcional(item: dict, clave: str) -> int | None:
    return int(item[clave]) if item.get(clave) is not None else None


def _modificaciones_del_item(item: dict) -> list:
    return list(item.get("modifications") or item.get("modificaciones") or [])


def _cantidad_del_item(item: dict) -> int:
    cantidad = item.get("cantidad") if item.get("cantidad") is not None else item.get("quantity")
    try:
        return int(cantidad) if cantidad is not None else 1
    except (ValueError, TypeError):
        return 1


def _linea_del_modelo(item: dict) -> tuple | None:
    """(product_id, cantidad, secondary_product_id, custom_name, modifications, promotion_id) o None si no trae producto ni promo."""
    promo_id = _id_opcional(item, "promotion_id")
    product_id = _id_opcional(item, "product_id")
    if promo_id is None and product_id is None:
        return None
    secondary_id = _id_opcional(item, "secondary_product_id")
    lleva_nombre_propio = item.get("nombre") and (secondary_id is not None or promo_id is not None)
    custom_name = str(item["nombre"]) if lleva_nombre_propio else None
    return product_id, int(item.get("quantity") or 1), secondary_id, custom_name, _modificaciones_del_item(item), promo_id


def items_del_modelo(items: list) -> list[tuple] | None:
    """Una línea (ver _linea_del_modelo) por cada ítem que armó el modelo, o None si no se pueden interpretar.

    Solo se toman los ids y las cantidades: los precios y el total los calcula siempre el pedido con los
    de la base, nunca con lo que haya armado el modelo.
    """
    try:
        lineas = [_linea_del_modelo(item) for item in items]
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    validas = [linea for linea in lineas if linea is not None]
    return validas if len(validas) == len(lineas) else None


def _parsear_items_solicitados(items_solicitados: str) -> list[dict]:
    """Ítems de una lista JSON o, si no lo es, de un texto libre como "2 Pizza Muzzarella, 1 Coca-Cola"."""
    try:
        parsed = json.loads(items_solicitados)
    except ValueError:
        return _items_desde_texto_libre(items_solicitados)
    if isinstance(parsed, list):
        return parsed
    return [parsed] if isinstance(parsed, dict) else []


def _items_desde_texto_libre(texto: str) -> list[dict]:
    # La coma de "mitad X, mitad Y" no separa productos: es una sola pizza mitad y mitad.
    sin_comas_de_mitades = _PATRON_COMA_ENTRE_MITADES.sub(" y ", texto)
    partes = [parte.strip() for parte in sin_comas_de_mitades.split(",")]
    return [_item_de_texto(parte) for parte in partes if parte]


def _item_de_texto(parte: str) -> dict:
    con_numero = _PATRON_CANTIDAD_NUMERICA.search(parte)
    if con_numero:
        return {"nombre": con_numero.group(2).strip(), "cantidad": int(con_numero.group(1))}
    con_palabra = _PATRON_CANTIDAD_EN_PALABRAS.search(parte)
    if con_palabra:
        cantidad = _CANTIDADES_EN_PALABRAS.get(con_palabra.group(1).lower(), 1)
        return {"nombre": con_palabra.group(2).strip(), "cantidad": cantidad}
    return {"nombre": parte, "cantidad": 1}


# --- Pizzas mitad y mitad ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class PedidoMitadYMitad:
    sabor1: str
    sabor2: str
    tamanio: str
    cantidad: int


def _tamanio_en(texto: str) -> str:
    """'grande' o 'chica' si el texto lo menciona; si no, vacío."""
    texto = texto.lower()
    if "grande" in texto:
        return "grande"
    return "chica" if "chica" in texto else ""


def _nombre_pizza_mitad_y_mitad(p1_name: str, p2_name: str, size_hint: str = "") -> str:
    """Nombre unificado de la pizza mitad y mitad (ej: 'Pizza Grande [1/2 Muzzarella | 1/2 Napolitana]')."""
    tamanio = _tamanio_en(f"{size_hint or ''} {p1_name} {p2_name}")
    base = f"Pizza {tamanio.capitalize()}".strip()
    return f"{base} [1/2 {clean_pizza_flavor(p1_name)} | 1/2 {clean_pizza_flavor(p2_name)}]"


def _es_pizza(producto: Product) -> bool:
    categoria = producto.category
    return (
        categoria is not None and (categoria.name.lower() == "pizzas" or getattr(categoria, "sector", "") == "pizzeria")
    ) or "pizza" in producto.name.lower()


def _coincidencia_por_tamanio(pool: list[Product], size_hint: str, tamanio: str) -> Product | list[Product] | None:
    """Productos del tamaño pedido (uno solo, o la lista si hay varios) cuando el cliente lo indicó."""
    if tamanio not in (size_hint or "").lower():
        return None
    coinciden = [p for p in pool if tamanio in p.name.lower()]
    return coinciden[0] if len(coinciden) == 1 else coinciden or None


def _buscar_sabor_pizza(db: Session, sabor: str, size_hint: str = "") -> Product | list[Product] | None:
    sabor_limpio = _PATRON_PREFIJO_PIZZA.sub("", sabor.strip()).strip()
    if not sabor_limpio:
        return None
    candidatos = find_available_products_by_name(db, sabor_limpio) or find_available_products_by_name(
        db, f"pizza {sabor_limpio}"
    )
    if not candidatos:
        return None
    if len(candidatos) == 1:
        return candidatos[0]

    pizzas = [p for p in candidatos if _es_pizza(p)]
    pool = pizzas or candidatos
    if len(pool) == 1:
        return pool[0]

    por_tamanio = _coincidencia_por_tamanio(pool, size_hint, "grande") or _coincidencia_por_tamanio(
        pool, size_hint, "chica"
    )
    if por_tamanio:
        return por_tamanio
    sin_tamanio = [p for p in pool if not _tamanio_en(p.name)]
    return sin_tamanio[0] if len(sin_tamanio) == 1 else pool


def _mitad_y_mitad_desde_nombre(nombre: str, size_hint: str, cantidad: int) -> PedidoMitadYMitad | None:
    """Interpreta '[1/2 Sabor1 | 1/2 Sabor2]' o el lenguaje natural 'mitad X, mitad Y' / '1/2 X y 1/2 Y'."""
    entre_corchetes = _PATRON_MITAD_ENTRE_CORCHETES.search(nombre)
    if entre_corchetes:
        prefijo, sabor1, sabor2 = (grupo.strip() for grupo in entre_corchetes.groups())
        return PedidoMitadYMitad(sabor1, sabor2, _tamanio_en(prefijo) or size_hint, cantidad)
    natural = _PATRON_MITAD_EN_LENGUAJE_NATURAL.search(nombre)
    if natural:
        prefijo = natural.group(1).strip()
        sabor1, sabor2 = (natural.group(i).strip().rstrip(" ,;/|[]") for i in (2, 3))
        cantidad_del_prefijo = re.search(r"^(\d+)", prefijo)
        cantidad = int(cantidad_del_prefijo.group(1)) if cantidad_del_prefijo else cantidad
        return PedidoMitadYMitad(sabor1, sabor2, _tamanio_en(prefijo) or size_hint, cantidad)
    return None


def _detectar_mitad_y_mitad(item: dict) -> PedidoMitadYMitad | None:
    """La pizza mitad y mitad que describe el ítem, o None si es un producto común."""
    sabor1 = item.get("sabor1") or item.get("gusto1")
    sabor2 = item.get("sabor2") or item.get("gusto2")
    cantidad = _cantidad_del_item(item)
    size_hint = str(item.get("tamanio") or item.get("size") or "")
    if sabor1 and sabor2:
        return PedidoMitadYMitad(str(sabor1).strip(), str(sabor2).strip(), size_hint, cantidad)
    nombre = str(item.get("nombre", "")).strip()
    return _mitad_y_mitad_desde_nombre(nombre, size_hint, cantidad) if nombre else None


# --- Resolución de ítems contra el menú -------------------------------------------------------------------


@dataclass
class ItemsResueltos:
    """Productos que pidió el cliente, ya buscados en el menú con los precios de la base."""

    validados: list[dict] = field(default_factory=list)
    resumen: list[str] = field(default_factory=list)
    total: Decimal = Decimal(0)
    hay_ambiguos: bool = False
    hay_cantidades_invalidas: bool = False
    # Posición en `resumen` de la línea de cada ítem validado (para reemplazarla si el pedido arma una promo).
    linea_de_item: list[int] = field(default_factory=list)

    def agregar_item(self, item: dict, linea: str, subtotal: Decimal) -> None:
        self.validados.append(item)
        self.resumen.append(linea)
        self.linea_de_item.append(len(self.resumen) - 1)
        self.total += subtotal

    def agregar_aviso(self, *lineas: str) -> None:
        self.resumen.extend(lineas)

    def agregar_ambiguedad(self, *lineas: str) -> None:
        self.hay_ambiguos = True
        self.resumen.extend(lineas)

    def agregar_cantidad_invalida(self, linea: str) -> None:
        self.hay_cantidades_invalidas = True
        self.resumen.append(linea)

    def mensaje_sin_items(self) -> str:
        """Qué decirle al cliente cuando no se pudo reconocer ningún producto."""
        if self.hay_ambiguos:
            return "Necesito que me aclares algunos productos:\n" + "\n".join(self.resumen)
        if self.hay_cantidades_invalidas:
            return "Necesito que revises algunos productos del pedido:\n" + "\n".join(self.resumen)
        return "No se pudieron reconocer productos válidos en el menú para tu pedido."


def _motivo_cantidad_invalida(cantidad: int) -> str | None:
    if cantidad < 1:
        return "la cantidad debe ser de al menos 1 unidad."
    if cantidad > MAX_QUANTITY_PER_ITEM:
        return f"supera la cantidad máxima permitida ({MAX_QUANTITY_PER_ITEM} unidades)."
    return None


def _rechazar_si_cantidad_invalida(resueltos: ItemsResueltos, descripcion: str, cantidad: int) -> bool:
    """Si la cantidad no es válida deja el motivo en el resumen y devuelve True."""
    motivo = _motivo_cantidad_invalida(cantidad)
    if motivo is None:
        return False
    resueltos.agregar_cantidad_invalida(f"- {descripcion}: {motivo}")
    return True


def _linea_de_resumen(nombre: str, cantidad: int, subtotal: Decimal, modificaciones: list[dict]) -> str:
    linea = f"- {nombre} (x{cantidad}) ${subtotal:,.2f}"
    etiquetas = " ".join(m["tag"] for m in modificaciones if m.get("tag"))
    return f"{linea}\n  {etiquetas}" if etiquetas else linea


def _nombres(productos: list) -> str:
    return ", ".join(p.name for p in productos)


def _item_de_promocion(promo: Promotion, cantidad: int) -> dict:
    return {
        "product_id": None,
        "secondary_product_id": None,
        "promotion_id": promo.id,
        "nombre": promo.name,
        "quantity": cantidad,
        "unit_price": float(to_money(promo.price)),
        "modifications": [],
    }


def _linea_de_promocion(promo: Promotion, cantidad: int) -> str:
    return f"- Promo: {promo.name} (x{cantidad}) ${to_money(promo.price) * cantidad:,.2f}"


def _buscar_producto(db: Session, nombre: str) -> Product | list[Product] | None:
    """Producto que corresponde al nombre que escribió el cliente: uno solo, la lista de candidatos si el
    nombre es ambiguo (para preguntarle cuál quiso, en vez de elegir uno al azar) o None."""
    candidatos = find_available_products_by_name(db, nombre)
    if not candidatos:
        return None
    return candidatos[0] if len(candidatos) == 1 else candidatos


def _resolver_sabores(
    db: Session, mitad: PedidoMitadYMitad, bases: tuple[str, str], resueltos: ItemsResueltos
) -> tuple[Product, Product] | None:
    """Los dos productos de la pizza; si algún sabor no existe o es ambiguo deja el aviso en el resumen."""
    sabores = (mitad.sabor1, mitad.sabor2)
    productos = [_buscar_sabor_pizza(db, base, mitad.tamanio) for base in bases]
    no_encontrados = [f"- No pudimos encontrar el sabor: '{s}'" for s, p in zip(sabores, productos, strict=True) if not p]
    if no_encontrados:
        resueltos.agregar_aviso(*no_encontrados)
        return None
    ambiguos = [f"- '{s}' puede ser: {_nombres(p)}. ¿Cuál querés?" for s, p in zip(sabores, productos, strict=True) if isinstance(p, list)]
    if ambiguos:
        resueltos.agregar_ambiguedad(*ambiguos)
        return None
    return cast(tuple[Product, Product], tuple(productos))


def _resolver_mitad_y_mitad(db: Session, item: dict, mitad: PedidoMitadYMitad, resueltos: ItemsResueltos) -> None:
    descripcion = f"Pizza mitad {mitad.sabor1} y mitad {mitad.sabor2}"
    if _rechazar_si_cantidad_invalida(resueltos, descripcion, mitad.cantidad):
        return
    base1, modificaciones1 = extraer_modificadores_de_texto(mitad.sabor1, db=db)
    base2, modificaciones2 = extraer_modificadores_de_texto(mitad.sabor2, db=db)
    modificaciones = vincular_modificadores_con_db(
        db, _modificaciones_del_item(item) + modificaciones1 + modificaciones2
    )
    sabores = _resolver_sabores(db, mitad, (base1, base2), resueltos)
    if sabores is None:
        return
    p1, p2 = sabores
    modificaciones = filtrar_modificadores_para_producto(modificaciones, p1, p2)
    # Regla de cobro: la pizza mitad y mitad toma el valor del gusto más caro.
    precio_unitario = max(p1.price, p2.price) + modifications_extra_cost(modificaciones)
    subtotal = precio_unitario * mitad.cantidad
    nombre = _nombre_pizza_mitad_y_mitad(p1.name, p2.name, mitad.tamanio)
    resueltos.agregar_item(
        {
            "product_id": p1.id,
            "secondary_product_id": p2.id,
            "nombre": nombre,
            "quantity": mitad.cantidad,
            "unit_price": float(precio_unitario),
            "modifications": modificaciones,
        },
        _linea_de_resumen(nombre, mitad.cantidad, subtotal, modificaciones),
        subtotal,
    )


def _promociones_pedidas(db: Session, nombre: str, base_nombre: str) -> list[Promotion]:
    """Promociones a las que se refiere el nombre pedido.

    Una coincidencia parcial con el nombre de una promo ("Coca-Cola 500ml" dentro de "Muzzarella + Coca-Cola
    500ml") no pisa a un producto del menú con ese nombre: el producto gana y, si el pedido arma una promo,
    se aplica después (ver _aplicar_promociones). Solo el nombre exacto de la promo, o un nombre que no
    corresponde a ningún producto, se toma como pedido de la promo.
    """
    promociones = promotion_repository.find_available_by_name(db, nombre)
    if not promociones and base_nombre != nombre:
        promociones = promotion_repository.find_available_by_name(db, base_nombre)
    nombres_exactos = {nombre.lower(), base_nombre.lower()}
    es_promo_exacta = any(p.name.lower() in nombres_exactos for p in promociones)
    es_producto = _buscar_producto(db, base_nombre) or _buscar_producto(db, nombre)
    return [] if promociones and not es_promo_exacta and es_producto else promociones


def _resolver_promocion(resueltos: ItemsResueltos, nombre: str, promociones: list[Promotion], cantidad: int) -> None:
    if len(promociones) > 1:
        resueltos.agregar_ambiguedad(
            f"- '{nombre}' puede referirse a las promociones: {_nombres(promociones)}. ¿Cuál querés?"
        )
        return
    promo = promociones[0]
    subtotal = promo.price * cantidad
    resueltos.agregar_item(
        _item_de_promocion(promo, cantidad), f"- Promo: {promo.name} (x{cantidad}) ${subtotal:,.2f}", subtotal
    )


def _producto_pedido(
    db: Session, nombre: str, base_nombre: str, modificaciones: list[dict]
) -> tuple[Product | list[Product] | None, list[dict]]:
    """Producto del menú para el nombre pedido y las modificaciones que le corresponden.

    Si solo se lo encuentra con el nombre completo (y no sin las modificaciones que se le sacaron), el texto
    extra era parte del nombre y no hay modificaciones.
    """
    producto = _buscar_producto(db, base_nombre)
    if producto or nombre == base_nombre:
        return producto, modificaciones
    return _buscar_producto(db, nombre), []


def _resolver_producto(
    db: Session, resueltos: ItemsResueltos, nombre: str, base_nombre: str, modificaciones: list[dict], cantidad: int
) -> None:
    producto, modificaciones = _producto_pedido(db, nombre, base_nombre, modificaciones)
    if not producto:
        resueltos.agregar_aviso(f"- No pudimos encontrar el producto: '{nombre}'")
        return
    if isinstance(producto, list):
        resueltos.agregar_ambiguedad(f"- '{base_nombre}' puede ser: {_nombres(producto)}. ¿Cuál querés?")
        return
    modificaciones = filtrar_modificadores_para_producto(modificaciones, producto)
    precio_unitario = producto.price + modifications_extra_cost(modificaciones)
    subtotal = precio_unitario * cantidad
    resueltos.agregar_item(
        {
            "product_id": producto.id,
            "nombre": producto.name,
            "quantity": cantidad,
            "unit_price": float(precio_unitario),
            "modifications": modificaciones,
        },
        _linea_de_resumen(producto.name, cantidad, subtotal, modificaciones),
        subtotal,
    )


def _resolver_item_comun(db: Session, item: dict, resueltos: ItemsResueltos) -> None:
    nombre = str(item.get("nombre", "")).strip()
    if not nombre:
        return
    cantidad = _cantidad_del_item(item)
    base_nombre, modificaciones_del_texto = extraer_modificadores_de_texto(nombre, db=db)
    modificaciones = vincular_modificadores_con_db(db, _modificaciones_del_item(item) + modificaciones_del_texto)
    if _rechazar_si_cantidad_invalida(resueltos, f"'{nombre}'", cantidad):
        return
    promociones = _promociones_pedidas(db, nombre, base_nombre)
    if promociones:
        _resolver_promocion(resueltos, nombre, promociones, cantidad)
        return
    _resolver_producto(db, resueltos, nombre, base_nombre, modificaciones, cantidad)


def _resolver_item(db: Session, item: dict, resueltos: ItemsResueltos) -> None:
    mitad = _detectar_mitad_y_mitad(item)
    if mitad:
        _resolver_mitad_y_mitad(db, item, mitad, resueltos)
    else:
        _resolver_item_comun(db, item, resueltos)


def resolver_items(db: Session, items_solicitados: str) -> ItemsResueltos:
    """Interpreta lo que pidió el cliente ("2 Pizza Muzzarella, 1 Coca-Cola" o una lista JSON) y lo busca en el menú."""
    resueltos = ItemsResueltos()
    for item in _parsear_items_solicitados(items_solicitados)[:MAX_ITEMS_EN_PEDIDO]:
        _resolver_item(db, item, resueltos)
    _aplicar_promociones(db, resueltos)
    return resueltos


# --- Promociones que arma el sistema ----------------------------------------------------------------------


def _es_producto_suelto(item: dict) -> bool:
    """Producto común, sin gustos combinados ni modificaciones: el único que puede pasar a formar parte de una promo."""
    return (
        item.get("product_id") is not None
        and not item.get("promotion_id")
        and not item.get("secondary_product_id")
        and not item.get("modifications")
    )


def _veces_que_entra(requisitos: dict[int, int], disponible: dict[int, int]) -> int:
    return min(disponible.get(pid, 0) // cantidad for pid, cantidad in requisitos.items())


def _promo_candidata(promo: Promotion, disponible: dict[int, int]) -> tuple[Decimal, Promotion, dict[int, int]] | None:
    """(ahorro por vez, promo, productos que pide) si la promo sale más barata y los productos sueltos alcanzan."""
    requisitos = {it.product_id: it.quantity for it in promo.items}
    precio_normal = sum((to_money(it.product.price) * it.quantity for it in promo.items), Decimal(0))
    ahorro = precio_normal - to_money(promo.price)
    if ahorro > 0 and _veces_que_entra(requisitos, disponible) >= 1:
        return ahorro, promo, requisitos
    return None


def _usar_promo(
    candidata: tuple[Decimal, Promotion, dict[int, int]],
    disponible: dict[int, int],
    aplicadas: dict[int, tuple[Promotion, int, Decimal]],
) -> None:
    """Aplica la promo tantas veces como entre con lo que queda de productos sueltos."""
    ahorro, promo, requisitos = candidata
    veces = _veces_que_entra(requisitos, disponible)
    if veces < 1:
        return
    for pid, cantidad in requisitos.items():
        disponible[pid] -= cantidad * veces
    aplicadas[promo.id] = (promo, veces, ahorro * veces)


def _elegir_promociones(
    promociones: list[Promotion], disponible: dict[int, int]
) -> dict[int, tuple[Promotion, int, Decimal]]:
    """Promos a aplicar con {id: (promo, veces, ahorro total)}. Descuenta de `disponible` lo que usan."""
    candidatas = [c for c in (_promo_candidata(promo, disponible) for promo in promociones) if c]
    # Primero la promo que más ahorra por vez; cada producto se usa en una sola promo.
    candidatas.sort(key=lambda c: (-c[0], c[1].id))
    aplicadas: dict[int, tuple[Promotion, int, Decimal]] = {}
    for candidata in candidatas:
        _usar_promo(candidata, disponible, aplicadas)
    return aplicadas


class _ReemplazoPorPromociones:
    """Rearma los ítems y las líneas del resumen cambiando los productos sueltos por las promos que forman."""

    def __init__(
        self,
        resueltos: ItemsResueltos,
        sueltos: set[int],
        aplicadas: dict[int, tuple[Promotion, int, Decimal]],
        consumo: dict[int, int],
    ):
        self._resueltos = resueltos
        self._sueltos = sueltos
        self._aplicadas = aplicadas
        self._consumo = consumo
        self._items = resueltos.validados
        self._item_de_cada_linea = {linea: k for k, linea in enumerate(resueltos.linea_de_item)}
        self._ya_pedidas = {item["promotion_id"] for item in self._items if item.get("promotion_id")}
        self._nuevos_items: list[dict] = []
        self._nuevas_lineas: list[str] = []
        self._promos_agregadas: set[int] = set()

    def ejecutar(self) -> None:
        for posicion, linea in enumerate(self._resueltos.resumen):
            self._procesar_linea(posicion, linea)
        self._resueltos.validados[:] = self._nuevos_items
        self._resueltos.resumen[:] = self._nuevas_lineas

    def _procesar_linea(self, posicion: int, linea: str) -> None:
        indice = self._item_de_cada_linea.get(posicion)
        if indice is None:
            self._nuevas_lineas.append(linea)
            return
        item = self._items[indice]
        if item.get("promotion_id") in self._aplicadas:
            self._sumar_a_promo_pedida(item)
            return
        if indice in self._sueltos and self._consumo.get(item["product_id"], 0) > 0:
            linea_restante = self._descontar_lo_usado_en_promos(item)
        else:
            linea_restante = linea
        if linea_restante is not None:
            self._nuevos_items.append(item)
            self._nuevas_lineas.append(linea_restante)

    def _sumar_a_promo_pedida(self, item: dict) -> None:
        """El modelo ya había puesto esta promo: se le suman las que se armaron con productos sueltos."""
        promo, veces, _ahorro = self._aplicadas[item["promotion_id"]]
        item["quantity"] += veces
        self._nuevos_items.append(item)
        self._nuevas_lineas.append(_linea_de_promocion(promo, item["quantity"]))

    def _descontar_lo_usado_en_promos(self, item: dict) -> str | None:
        """Pone las promos donde estaba el primer producto suelto y devuelve la línea de lo que sobra (None si nada)."""
        self._agregar_promos_nuevas()
        tomado = min(item["quantity"], self._consumo[item["product_id"]])
        self._consumo[item["product_id"]] -= tomado
        item["quantity"] -= tomado
        if item["quantity"] == 0:
            return None
        return f"- {item['nombre']} (x{item['quantity']}) ${to_money(item['unit_price']) * item['quantity']:,.2f}"

    def _agregar_promos_nuevas(self) -> None:
        nuevas = [
            (promo_id, promo, veces)
            for promo_id, (promo, veces, _ahorro) in self._aplicadas.items()
            if promo_id not in self._promos_agregadas and promo_id not in self._ya_pedidas
        ]
        for promo_id, promo, veces in nuevas:
            self._promos_agregadas.add(promo_id)
            self._nuevos_items.append(_item_de_promocion(promo, veces))
            self._nuevas_lineas.append(_linea_de_promocion(promo, veces))


def _aplicar_promociones(db: Session, resueltos: ItemsResueltos) -> None:
    """Si los productos sueltos del pedido arman una promo vigente (y sale más barata), los reemplaza por ella.

    Lo decide el sistema y no el modelo de lenguaje: el modelo solo pasa lo que dijo el cliente y acá se detecta
    si eso ya es una promo, así nunca se agrega un producto de más ni se pierde un descuento.
    """
    items = resueltos.validados
    sueltos = {i for i, item in enumerate(items) if _es_producto_suelto(item)}
    if not sueltos:
        return
    disponible: dict[int, int] = {}
    for i in sueltos:
        _sumar_cantidad(disponible, items[i])
    inicial = dict(disponible)

    aplicadas = _elegir_promociones(promotion_repository.list_available(db), disponible)
    if not aplicadas:
        return
    # Cuánto de cada producto suelto pasó a las promos.
    consumo = {pid: inicial[pid] - disponible[pid] for pid in inicial}
    _ReemplazoPorPromociones(resueltos, sueltos, aplicadas, consumo).ejecutar()
    resueltos.total -= sum((ahorro for _, _, ahorro in aplicadas.values()), Decimal(0))


def _sumar_cantidad(cantidades: dict[int, int], item: dict) -> None:
    cantidades[item["product_id"]] = cantidades.get(item["product_id"], 0) + item["quantity"]


# --- Resumen para el cliente ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _DatosDeEntrega:
    cliente: str | None
    telefono: str
    es_retiro: bool
    direccion: str | None
    horario: datetime | None
    observaciones: str | None
    metodo_pago: str | None
    # Los medios que ofrece el local, en texto ("Efectivo y Tarjeta"), para preguntarle al cliente cómo paga.
    opciones_pago: str = ""

    def lineas(self) -> list[str]:
        entrega = PICKUP_ADDRESS if self.es_retiro else f"Envío a domicilio: {self.direccion}"
        lineas = [f"- Nombre: {self.cliente}", f"- Teléfono: {self.telefono}", f"- {entrega}"]
        # El horario y las observaciones solo aparecen si hay algo que mostrar (un pedido para ahora no lleva horario).
        if self.horario:
            lineas.append(f"- Horario: {describir_horario_programado(self.horario, ahora_local())}")
        if self.observaciones:
            lineas.append(f"- Observaciones: {self.observaciones}")
        if self.metodo_pago:
            lineas.append(f"- Método de pago: {self._etiqueta_pago()}")
        return lineas

    def cierre(self) -> str:
        if self.metodo_pago:
            # Con todos los datos, incluido el pago: es la única vez que se le pide confirmar.
            return "¿Está todo bien para confirmar el pedido?"
        return f"💳 ¿Cómo preferís pagar? Ofrecemos {self.opciones_pago}."

    def _etiqueta_pago(self) -> str:
        return PAYMENT_LABELS[PaymentMethod(self.metodo_pago)]


DELIVERY_VALUES = {metodo.value for metodo in DeliveryMethod}


def _texto_de_opciones(opciones: list[PaymentMethod]) -> str:
    """Los medios de pago entre comillas: '"Efectivo"', '"Efectivo" y "Tarjeta"'..."""
    nombres = [f'"{PAYMENT_LABELS[metodo]}"' for metodo in opciones]
    return " y ".join([", ".join(nombres[:-1]), nombres[-1]]) if len(nombres) > 1 else "".join(nombres)


def _bloque_de_productos(resueltos: ItemsResueltos) -> list[str]:
    lineas = [*resueltos.resumen]
    if any(item.get("modifications") for item in resueltos.validados):
        lineas.extend(["", _ACLARACION_MODIFICACIONES])
    return lineas


def _datos_faltantes(
    resueltos: ItemsResueltos, metodo_entrega: str | None, nombre: str | None, telefono: str, falta_direccion: bool
) -> list[str]:
    """Qué le falta decir al cliente para poder armar el pedido."""
    faltantes = []
    if metodo_entrega is None:
        faltantes.append("si retirás por el local o te lo enviamos a domicilio")
    if not nombre:
        faltantes.append("tu nombre")
    if not _telefono_valido(telefono):
        faltantes.append("un teléfono de contacto válido" if telefono else "un teléfono de contacto")
    if falta_direccion:
        faltantes.append("tu dirección de envío completa (calle, número y entre qué calles queda)")
    if resueltos.hay_ambiguos:
        faltantes.append("cuál de los productos que te consulté arriba querés")
    if resueltos.hay_cantidades_invalidas:
        faltantes.append("corregir las cantidades no válidas que te indiqué arriba")
    return faltantes


def _bloque_de_totales(
    total_base: Decimal,
    cupon_aplicado: str | None = None,
    cupon_pct: int | None = None,
    cupon_ahorro: Decimal | None = None,
    total_final: Decimal | None = None,
    con_icono: bool = True,
) -> list[str]:
    icono = "💰 " if con_icono else ""
    if cupon_aplicado and cupon_pct is not None and cupon_ahorro is not None and total_final is not None:
        return [
            f"Subtotal: ${total_base:,.2f}",
            f"Descuento cupón ({cupon_aplicado} - {cupon_pct}% OFF): -${cupon_ahorro:,.2f}",
            f"{icono}Total: ${total_final:,.2f}",
        ]
    return [f"{icono}Total: ${total_base:,.2f}"]


def _texto_con_datos_faltantes(
    resueltos: ItemsResueltos,
    faltantes: list[str],
    aviso_horario: str | None,
    cupon_aplicado: str | None = None,
    cupon_pct: int | None = None,
    cupon_ahorro: Decimal | None = None,
    total_final: Decimal | None = None,
) -> str:
    lineas_totales = _bloque_de_totales(
        resueltos.total, cupon_aplicado, cupon_pct, cupon_ahorro, total_final, con_icono=False
    )
    texto = (
        "Detalle de tu pedido:\n"
        + "\n".join(_bloque_de_productos(resueltos))
        + "\n\n"
        + "\n".join(lineas_totales)
        + f"\n\n(Me falta que me digas {', '.join(faltantes)} para continuar)."
    )
    return f"{texto}\n\n{aviso_horario}" if aviso_horario else texto


def _texto_para_confirmar(
    resueltos: ItemsResueltos,
    entrega: _DatosDeEntrega,
    cupon_aplicado: str | None = None,
    cupon_pct: int | None = None,
    cupon_ahorro: Decimal | None = None,
    total_final: Decimal | None = None,
) -> str:
    lineas_totales = _bloque_de_totales(
        resueltos.total, cupon_aplicado, cupon_pct, cupon_ahorro, total_final, con_icono=True
    )
    return "\n".join(
        [
            "📝 Resumen de tu pedido",
            "",
            "🛒 Productos:",
            *_bloque_de_productos(resueltos),
            *lineas_totales,
            "",
            "🚚 Entrega:",
            *entrega.lineas(),
            "",
            entrega.cierre(),
        ]
    )


def _mensaje_para_el_cliente(
    resueltos: ItemsResueltos,
    faltantes: list[str],
    aviso_horario: str | None,
    entrega: _DatosDeEntrega,
    cupon_aplicado: str | None = None,
    cupon_pct: int | None = None,
    cupon_ahorro: Decimal | None = None,
    total_final: Decimal | None = None,
) -> str:
    if faltantes:
        return _texto_con_datos_faltantes(
            resueltos, faltantes, aviso_horario, cupon_aplicado, cupon_pct, cupon_ahorro, total_final
        )
    return aviso_horario or _texto_para_confirmar(
        resueltos, entrega, cupon_aplicado, cupon_pct, cupon_ahorro, total_final
    )


def _datos_temporales(
    resueltos: ItemsResueltos,
    entrega: _DatosDeEntrega,
    metodo_entrega: str | None,
    faltantes: list[str],
    aviso_horario: str | None,
    total_final: Decimal | None = None,
    cupon_aplicado: str | None = None,
) -> dict:
    """Los datos del pedido que se le devuelven al modelo para que los use al confirmarlo."""
    horario = entrega.horario
    total = float(total_final if total_final is not None else resueltos.total)
    return {
        "items": resueltos.validados,
        "total": total,
        "cliente": entrega.cliente,
        "telefono": entrega.telefono or None,
        "direccion": PICKUP_ADDRESS if entrega.es_retiro else entrega.direccion,
        "metodo_entrega": metodo_entrega,
        "hora_programada": f"{horario:%H:%M}" if horario else None,
        "dia_programado": f"{horario:%Y-%m-%d}" if horario else None,
        "observaciones": entrega.observaciones,
        "metodo_pago": entrega.metodo_pago,
        "faltan_datos": bool(faltantes) or aviso_horario is not None,
        "cupon": cupon_aplicado,
    }


@tool
def calcular_y_preparar_pedido(
    items_solicitados: str,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    shipping_address: str | None = None,
    metodo_entrega: str | None = None,
    hora_programada: str | None = None,
    dia_programado: str | None = None,
    observaciones: str | None = None,
    metodo_pago: str | None = None,
    cupon: str | None = None,
) -> str:
    """Calcula de forma exacta el total de un pedido consultando los precios reales.

    Args:
        items_solicitados: Los productos y cantidades que pidió el cliente, tal cual, sin agregar nada
            (ej: "2 Pizza Muzzarella, 1 Coca-Cola"). Si lo pedido arma una promoción vigente, el sistema la aplica
            solo: no pases la promo ni sus productos por tu cuenta, salvo que el cliente haya nombrado la promo.
        customer_name: Nombre del cliente.
        customer_phone: Teléfono de contacto del cliente.
        shipping_address: Dirección de envío completa (solo para envíos a domicilio): calle, número y entre qué
            calles queda (ej: "Belgrano 95, entre Mitre y San Martín").
        metodo_entrega: "retiro" o "domicilio".
        hora_programada: Hora para la que se programa el pedido (ej: "21:00"); vacío si es para ahora.
        dia_programado: Día para el que se programa el pedido, solo si el cliente lo indicó (ej: "mañana",
            "sábado", "17/10"); vacío si no dijo el día.
        observaciones: Aclaraciones del cliente sobre la comida o la entrega (ej: "sin cebolla",
            "timbre 2B", "paga con $20000"). Incluí cualquier aclaración de este tipo que el cliente
            haya mencionado en cualquier momento de la conversación, aunque no se la hayas preguntado.
        metodo_pago: "efectivo", "transferencia", "tarjeta" o "mercadopago" (solo los que ofrece el local). Si el
            cliente indicó cómo desea abonar, pasalo acá.
        cupon: Código de cupón de descuento provisto por el cliente (ej: "PROMOVERANO").
    """
    db = SessionLocal()
    try:
        resueltos = resolver_items(db, items_solicitados)
        if not resueltos.validados:
            return resueltos.mensaje_sin_items()

        cupon_aplicado: str | None = None
        cupon_pct: int | None = None
        cupon_ahorro: Decimal | None = None
        total_con_descuento: Decimal = resueltos.total
        aviso_cupon: str | None = None

        if cupon and cupon.strip():
            codigo_cupon = cupon.strip().upper()
            c_res = coupon_service.validate_web_coupon(db, codigo_cupon)
            if c_res.valid:
                cupon_aplicado = c_res.code
                cupon_pct = c_res.discount_percentage
                cupon_ahorro = round(resueltos.total * Decimal(str(cupon_pct)) / Decimal("100"), 2)
                total_con_descuento = max(Decimal("0.00"), resueltos.total - cupon_ahorro)
            else:
                aviso_cupon = "⚠️ El cupón ingresado no es válido."

        nombre = _recortar(customer_name, MAX_LARGO_CLIENTE)
        direccion = _recortar(shipping_address, MAX_LARGO_DIRECCION)
        telefono = (customer_phone or "").strip()
        es_retiro = metodo_entrega == DeliveryMethod.PICKUP
        faltantes = _datos_faltantes(resueltos, metodo_entrega, nombre, telefono, not es_retiro and not direccion)
        horario, aviso_horario = _evaluar_hora_programada(db, hora_programada, dia_programado)
        metodo = normalizar_metodo_pago(metodo_pago)
        opciones = accepted_payment_methods(db, metodo_entrega if metodo_entrega in DELIVERY_VALUES else None)
        aviso_pago = None
        if metodo and PaymentMethod(metodo) not in opciones:
            aviso_pago = f"El local no acepta {PAYMENT_LABELS[PaymentMethod(metodo)]} para este pedido."
            metodo = None
        entrega = _DatosDeEntrega(
            cliente=nombre,
            telefono=telefono,
            es_retiro=es_retiro,
            direccion=direccion,
            horario=horario,
            observaciones=_limpiar_observaciones(observaciones),
            metodo_pago=metodo,
            opciones_pago=_texto_de_opciones(opciones),
        )
        datos_temporales = _datos_temporales(
            resueltos,
            entrega,
            metodo_entrega,
            faltantes,
            aviso_horario,
            total_final=total_con_descuento,
            cupon_aplicado=cupon_aplicado,
        )
        mensaje = _mensaje_para_el_cliente(
            resueltos,
            faltantes,
            aviso_horario,
            entrega,
            cupon_aplicado=cupon_aplicado,
            cupon_pct=cupon_pct,
            cupon_ahorro=cupon_ahorro,
            total_final=total_con_descuento,
        )
        partes_extra = [aviso_cupon, aviso_pago]
        partes_activas = [p for p in partes_extra if p]
        if partes_activas:
            mensaje = "\n\n".join([*partes_activas, mensaje])
        return json.dumps({"mensaje_para_usuario": mensaje, "datos_temporales": datos_temporales}, ensure_ascii=False)
    except Exception as e:
        logger.exception("Error procesando el cálculo del pedido. items_solicitados=%s", items_solicitados)
        return f"Error procesando el cálculo: {str(e)}"
    finally:
        db.close()


# --- Confirmación del pedido ------------------------------------------------------------------------------


def _limpiar_observaciones(observaciones: str | None) -> str | None:
    return _recortar(observaciones, MAX_LARGO_OBSERVACIONES)


def _metodo_entrega_confirmado(datos: dict) -> DeliveryMethod:
    entrega = str(datos.get("metodo_entrega", "domicilio")).lower()
    es_retiro = "retiro" in entrega or "local" in entrega
    return DeliveryMethod.PICKUP if es_retiro else DeliveryMethod.DELIVERY


def _telefono_confirmado(datos: dict, canal: Channel | None, chat_id: str | None) -> str:
    if canal == Channel.WHATSAPP and chat_id:
        # En WhatsApp el cliente se identifica por el número del chat: es el teléfono del pedido y de su perfil.
        return normalize_phone(chat_id)
    return str(datos.get("telefono") or datos.get("customer_phone") or "").strip()[:MAX_LARGO_TELEFONO]


def _detalle_de_pago(db: Session, metodo_pago: str, total: Decimal, link_enviado: bool = True) -> str:
    if metodo_pago == PaymentMethod.MERCADOPAGO.value:
        if link_enviado:
            return "MercadoPago (abajo te dejo el link de pago)"
        return "MercadoPago (el local te va a enviar el link de pago por este chat)"
    if metodo_pago == PaymentMethod.TRANSFER.value:
        return (
            f"Transferencia. Transferí ${total:,.2f} a {transfer_instructions(db)} y mandame por este chat una "
            "foto del comprobante"
        )
    if metodo_pago == PaymentMethod.CARD.value:
        return "Tarjeta (abonás al recibir o retirar tu pedido)"
    return "Efectivo (abonás al recibir o retirar tu pedido)"


def _mensaje_pedido_registrado(
    cliente: str,
    programado: datetime | None,
    detalle_pago: str,
    demora_minutos: int | None = None,
    instrucciones_pago: str | None = None,
) -> str:
    """Mensaje al cliente con el pedido ya tomado por el local: la demora se informa solo si hay una."""
    horario = f" {describir_horario_programado(programado, ahora_local())}" if programado else ""
    partes = [f"¡Listo, {cliente}! 🙌 {MARCA_PEDIDO_REGISTRADO}{horario}."]
    if demora_minutos is not None and programado is None:
        partes.append(f"Tiempo estimado de entrega: {demora_minutos} minutos aproximadamente.")
    partes.append(f"Método de pago: {detalle_pago}.")
    if instrucciones_pago:
        partes.append(instrucciones_pago)
    partes.append("Ya lo estamos preparando. ¡Muchas gracias por elegirnos!")
    return "\n\n".join(partes)


def _imprimir_comanda(db: Session, pedido) -> None:
    """La comanda sale a cocina apenas entra el pedido. Si la impresora falla el pedido queda registrado igual."""
    resultado = printer_service.print_order(db, pedido)
    if not resultado.success:
        logger.warning("No se pudo imprimir la comanda del pedido #%s: %s", pedido.id, resultado.message)


def _instrucciones_de_pago(db: Session, pedido) -> str | None:
    """Link de MercadoPago del pedido (solo si se paga por ahí). Si no se pudo generar, el local lo envía a mano."""
    try:
        return start_chat_payment(db, pedido, get_or_create_store_config(db))
    except Exception:
        logger.exception("No se pudo generar el link de pago del pedido #%s.", pedido.id)
        return None


def _registrar_pedido_confirmado(db: Session, datos: dict, canal: Channel | None, chat_id: str | None) -> str:
    """Valida lo que confirmó el cliente y registra el pedido; devuelve el mensaje para el cliente."""
    delivery_method = _metodo_entrega_confirmado(datos)
    es_retiro = delivery_method == DeliveryMethod.PICKUP
    cliente = (datos.get("cliente") or datos.get("customer_name") or "Cliente").strip()[:MAX_LARGO_CLIENTE]
    direccion = _recortar(datos.get("direccion") or datos.get("shipping_address"), MAX_LARGO_DIRECCION)
    telefono = _telefono_confirmado(datos, canal, chat_id)

    if not cliente or (not es_retiro and not direccion):
        return "Faltan datos obligatorios (nombre o dirección) para registrar la orden."
    if not _telefono_valido(telefono):
        return "El pedido NO se registró todavía: falta un teléfono de contacto válido del cliente."

    programado, aviso_horario = _evaluar_hora_programada(
        db,
        datos.get("hora_programada"),
        datos.get("dia_programado"),
        tolerancia_minutos=TOLERANCIA_CONFIRMACION_MINUTOS,
    )
    if aviso_horario:
        return f"El pedido NO se registró todavía. {aviso_horario}"
    items = items_del_modelo(datos.get("items") or [])
    if items is None:
        return "El pedido NO se registró todavía. No pude identificar los productos del pedido."

    metodo_pago = normalizar_metodo_pago(datos.get("metodo_pago") or datos.get("payment_method")) or PaymentMethod.CASH.value
    pedido = OrderRequest(
        customer_name=cliente,
        customer_phone=telefono,
        delivery_method=delivery_method,
        shipping_address=None if es_retiro else direccion,
        notes=_limpiar_observaciones(datos.get("observaciones") or datos.get("notes")),
        items=items,
    )
    cupon = datos.get("cupon") or datos.get("coupon_code")
    # Mismas reglas que los pedidos de la web y del mostrador (disponibilidad, máximo por producto, precios).
    try:
        guardado = create_bot_order(
            db,
            pedido,
            channel=canal,
            chat_id=chat_id if canal else None,
            scheduled_for=programado.astimezone(timezone.utc) if programado else None,
            payment_method=metodo_pago,
            coupon_code=cupon,
        )
    except (InvalidOrderError, BusinessRuleError) as exc:
        return f"El pedido NO se registró todavía. {exc}"
    _imprimir_comanda(db, guardado)
    instrucciones = _instrucciones_de_pago(db, guardado) if metodo_pago == PaymentMethod.MERCADOPAGO.value else None
    detalle = _detalle_de_pago(db, metodo_pago, guardado.total_amount, link_enviado=instrucciones is not None)
    return _mensaje_pedido_registrado(cliente, programado, detalle, guardado.estimated_minutes, instrucciones)


@tool
def confirmar_y_guardar_pedido(
    datos_pedido_json: str,
    canal: Annotated[Channel | None, InjectedToolArg] = None,
    chat_id: Annotated[str | None, InjectedToolArg] = None,
) -> str:
    """Persiste definitivamente la orden en la base de datos: el local la toma directamente (sin aceptarla ni rechazarla).
    Se ejecuta únicamente cuando el usuario confirma explícitamente con un 'Sí'.

    Args:
        datos_pedido_json: El objeto JSON con los items, total, nombre y dirección validados previamente.
    """
    db = SessionLocal()
    try:
        return _registrar_pedido_confirmado(db, json.loads(datos_pedido_json), canal, chat_id)
    except Exception:
        # Si el error ocurrió al guardar, el servicio ya deshizo la transacción.
        logger.exception("Error al guardar la orden. datos_pedido_json=%s", datos_pedido_json)
        return "Error al procesar el registro del pedido. Por favor, intentá nuevamente."
    finally:
        db.close()
