"""Casos de uso de los pedidos: registrarlos desde cada canal (web, mostrador y bot), consultarlos y
avanzarlos en su ciclo de vida. Las reglas del pedido en sí viven en el modelo Order."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.channels import Channel
from app.core.errors import BusinessRuleError, NotFoundError
from app.db.session import transaction
from app.models.delivery_driver import DeliveryDriver
from app.models.order import (
    DeliveryMethod,
    EstimateSource,
    InvalidOrderError,
    Order,
    OrderSource,
    OrderStatus,
    PaymentMethod,
    complete_line,
)
from app.models.user import User
from app.repositories import delivery_driver_repository, order_repository, product_repository, promotion_repository
from app.services import cash_shift_service, coupon_service
from app.services.business_hours_service import verificar_local_abierto
from app.services.client_service import upsert_client
from app.services.delivery_time_service import estimate_delay
from app.services.modifier_nlp import (
    extraer_modificadores_de_texto,
    filtrar_modificadores_para_producto,
    vincular_modificadores_con_db,
)
from app.services.payment_methods_service import ensure_payment_method_accepted

logger = logging.getLogger(__name__)

# Demora estimada de un pedido nuevo: una base más un tanto por cada pedido que se está preparando.
BASE_DELAY_MINUTES = 15
MINUTES_PER_ORDER_IN_PROGRESS = 3


@dataclass(frozen=True)
class OrderRequest:
    """Datos de un pedido nuevo, sea cual sea el canal por el que llegó."""

    customer_name: str
    customer_phone: str
    delivery_method: DeliveryMethod | str
    shipping_address: str | None
    notes: str | None
    # (product_id, cantidad) o (product_id, cantidad, secondary_product_id, custom_name, mods, promotion_id,
    # variante).
    items: list[tuple]


@dataclass(frozen=True)
class CounterPayment:
    method: str | None
    is_paid: bool


class ScheduleTooEarlyError(BusinessRuleError):
    """El horario pedido es anterior al primero en el que el local puede tener listo el pedido."""

    def __init__(self, earliest: datetime, delay_minutes: int):
        self.earliest = earliest
        self.delay_minutes = delay_minutes
        super().__init__(f"Lo más temprano que podemos tener el pedido es a las {earliest:%H:%M}.")


# --- Demora y horarios --------------------------------------------------------------------------------


def estimate_delay_minutes(db: Session) -> int:
    """Demora mínima con la que se puede tener listo un pedido nuevo (para validar los horarios de los programados):
    una base más un tanto por cada pedido en preparación."""
    return BASE_DELAY_MINUTES + current_queue_size(db) * MINUTES_PER_ORDER_IN_PROGRESS


def current_queue_size(db: Session) -> int:
    """Pedidos en cola: para ahora y todavía sin despachar ni listos para retirar."""
    return order_repository.count_in_queue(db)


def _assign_delay(db: Session, order: Order) -> None:
    """Le asigna al pedido que entra la demora con la que se promete: la del historial si alcanza (y está activada),
    si no la regla fija que corresponda. Sin ninguna de las dos no se informa demora. Los programados no llevan."""
    if order.scheduled_for is not None:
        return
    estimate = estimate_delay(db, order.delivery_method, current_queue_size(db))
    if estimate.minutes is not None:
        order.set_estimated_minutes(
            estimate.minutes, EstimateSource.SMART if estimate.is_smart else EstimateSource.FIXED
        )


def _round_up_to_minute(moment: datetime) -> datetime:
    rounded = moment.replace(second=0, microsecond=0)
    return rounded if rounded == moment else rounded + timedelta(minutes=1)


def validate_schedule(db: Session, requested: datetime, now: datetime, tolerance_minutes: int = 0) -> None:
    """Verifica que el pedido programado se llegue a preparar con la demora actual.

    La tolerancia evita rechazar al confirmar un horario que era válido cuando se le propuso al cliente y
    quedó apenas por debajo del mínimo por el tiempo que pasó en la conversación.
    """
    delay = estimate_delay_minutes(db)
    earliest = _round_up_to_minute(now + timedelta(minutes=delay))
    if requested + timedelta(minutes=tolerance_minutes) < earliest:
        raise ScheduleTooEarlyError(earliest, delay)


# --- Alta de pedidos ----------------------------------------------------------------------------------


def _ids_referenced_by(item: tuple) -> tuple[set[int], set[int]]:
    """(ids de productos, ids de promociones) a los que se refiere el ítem."""
    product_id, _, secondary_id, _, _, promotion_id, _ = complete_line(item)
    if promotion_id is not None:
        return set(), {promotion_id}
    if product_id is None:
        raise InvalidOrderError("Cada ítem debe tener un producto o una promoción.")
    return {i for i in (product_id, secondary_id) if i is not None}, set()


def _collect_referenced_ids(items: list[tuple]) -> tuple[set[int], set[int]]:
    """(ids de productos, ids de promociones) a los que se refieren los ítems del pedido."""
    referenced = [_ids_referenced_by(item) for item in items]
    return (
        {product_id for product_ids, _ in referenced for product_id in product_ids},
        {promotion_id for _, promotion_ids in referenced for promotion_id in promotion_ids},
    )


def _line_with_objects(item: tuple, products: dict, promotions: dict) -> tuple:
    """El ítem con los productos y la promoción en lugar de sus ids."""
    product_id, quantity, secondary_id, custom_name, mods, promotion_id, variant = complete_line(item)
    if promotion_id is not None:
        promotion = promotions[promotion_id]
        return None, quantity, None, custom_name or promotion.name, mods, promotion, None
    secondary_product = products[secondary_id] if secondary_id is not None else None
    return products[product_id], quantity, secondary_product, custom_name, mods, None, variant


def _products_for(
    db: Session, items: list[tuple]
) -> list[tuple[Any, int, Any, str | None, list[dict], Any, str | None]]:
    product_ids, promotion_ids = _collect_referenced_ids(items)

    products = product_repository.get_many(db, product_ids) if product_ids else {}
    if len(products) != len(product_ids):
        raise InvalidOrderError("Algunos productos del pedido ya no existen en el menú.")

    promotions = promotion_repository.get_many(db, promotion_ids) if promotion_ids else {}
    if len(promotions) != len(promotion_ids):
        raise InvalidOrderError("Algunas promociones del pedido ya no están disponibles.")

    return [_line_with_objects(item, products, promotions) for item in items]


def _promotion_products(promotion: Any) -> list[Any]:
    if promotion is None or not hasattr(promotion, "items"):
        return []
    return [item.product for item in promotion.items if getattr(item, "product", None)]


def _ingredient_ids_of_line(line: tuple) -> set[int]:
    """Ingredientes de las recetas de lo que lleva la línea (sus productos o los de su promoción)."""
    product, _, secondary_product, _, _, promotion, _ = complete_line(line)
    direct_products = [p for p in (product, secondary_product) if p is not None]
    return {
        recipe_item.ingredient_id
        for p in [*_promotion_products(promotion), *direct_products]
        for recipe_item in (getattr(p, "recipe_items", None) or [])
        if recipe_item.ingredient_id is not None
    }


def _is_food(product: Any) -> bool:
    category = getattr(product, "category", None)
    return product is not None and bool(category) and getattr(category, "sector", "") != "barra"


def _line_index_for_modifier(modifier: dict, lines: list[tuple], ingredient_ids_by_line: list[set[int]]) -> int:
    """Posición del ítem al que corresponde el modificador: el que tiene ese ingrediente en su receta o, si no
    hay, el único ítem o el primero que no sea una bebida."""
    ingredient_id = modifier.get("ingredient_id")
    owners = [i for i, ids in enumerate(ingredient_ids_by_line) if ingredient_id is not None and ingredient_id in ids]
    if owners:
        return owners[0]
    if len(lines) == 1:
        return 0
    food_indices = [i for i, line in enumerate(lines) if _is_food(line[0])]
    return food_indices[0] if food_indices else 0


def _modifiers_from_notes(db: Session, notes: str) -> list[dict]:
    """Exclusiones y extras de las observaciones que corresponden a ingredientes del sistema o a extras con costo."""
    _, raw_modifiers = extraer_modificadores_de_texto(notes, db=db)
    if not raw_modifiers:
        return []
    return [
        m
        for m in vincular_modificadores_con_db(db, raw_modifiers)
        if m.get("ingredient_id") is not None or float(m.get("price") or 0) > 0
    ]


def _line_with_valid_modifiers(line: tuple, extra_modifiers: list[dict]) -> tuple:
    """La línea con sus modificaciones más las indicadas, quedándose con las que valen para su producto."""
    product, quantity, secondary_product, custom_name, modifiers, promotion, variant = complete_line(line)
    modifiers = modifiers + extra_modifiers
    if product is not None:
        modifiers = filtrar_modificadores_para_producto(modifiers, product, secondary_product)
    return product, quantity, secondary_product, custom_name, modifiers, promotion, variant


def _attach_notes_modifiers(db: Session, notes: str | None, parsed_items: list[tuple]) -> list[tuple]:
    """Interpreta exclusiones y extras en lenguaje natural de las observaciones y los asocia a los ítems del pedido."""
    if not notes or not str(notes).strip():
        return parsed_items
    # Si los ítems ya traen modificaciones explícitas (ej. bot con desglose previo), no las sobreescribimos
    if any(complete_line(line)[4] for line in parsed_items):
        return parsed_items
    modifiers = _modifiers_from_notes(db, str(notes))
    if not modifiers:
        return parsed_items

    ingredient_ids_by_line = [_ingredient_ids_of_line(line) for line in parsed_items]
    modifiers_by_line: defaultdict[int, list[dict]] = defaultdict(list)
    for modifier in modifiers:
        modifiers_by_line[_line_index_for_modifier(modifier, parsed_items, ingredient_ids_by_line)].append(modifier)
    return [_line_with_valid_modifiers(line, modifiers_by_line[i]) for i, line in enumerate(parsed_items)]


def _new_order(db: Session, request: OrderRequest, source: OrderSource) -> Order:
    """Arma el pedido (sin guardarlo) validándolo contra el menú actual, con los precios de la base."""
    order = Order(
        customer_name=request.customer_name,
        customer_phone=request.customer_phone,
        notes=request.notes or None,
        source=source.value,
        status=OrderStatus.CONFIRMED.value,
    )
    order.set_delivery(request.delivery_method, request.shipping_address)
    parsed_items = _attach_notes_modifiers(db, request.notes, _products_for(db, request.items))
    order.set_items([_line_with_valid_modifiers(line, []) for line in parsed_items])
    return order


def _save(db: Session, order: Order) -> Order:
    with transaction(db):
        order_repository.add(db, order)
    db.refresh(order)
    return order


def _attach_open_shift(db: Session, order: Order) -> None:
    """El pedido entra al turno de caja abierto, si lo hay."""
    shift = cash_shift_service.get_current_open_shift(db)
    if shift:
        order.cash_shift_id = shift.id


def _apply_coupon_discount(db: Session, order: Order, coupon_code: str | None) -> None:
    if not coupon_code:
        return
    coupon_res = coupon_service.validate_web_coupon(db, coupon_code)
    if coupon_res.valid:
        discount_amount = round(order.total_amount * Decimal(str(coupon_res.discount_percentage)) / Decimal("100"), 2)
        order.total_amount = max(Decimal("0"), order.total_amount - discount_amount)
        coupon_note = f"[Cupón aplicado: {coupon_res.code} ({coupon_res.discount_percentage}% OFF - Ahorro: ${discount_amount:,.2f})]"
        order.notes = f"{order.notes}\n{coupon_note}".strip() if order.notes else coupon_note
    else:
        raise BusinessRuleError(coupon_res.message or f"El cupón '{coupon_code}' no es válido.")


def create_web_order(
    db: Session,
    request: OrderRequest,
    user: User | None = None,
    payment_method: PaymentMethod | str = PaymentMethod.CASH,
    coupon_code: str | None = None,
) -> Order:
    """Pedido hecho desde la web: entra directamente 'Confirmado' (con la demora estimada del local, si la hay) y
    queda sin abonar. El local puede cancelarlo después.

    Se puede pedir como invitado. Si quien pide tiene sesión de cliente, el pedido queda asociado a su
    cuenta (los datos de contacto son siempre los enviados en el pedido). Solo se aceptan dentro del
    horario de atención del local (si no, lanza LocalCerradoError).
    """
    verificar_local_abierto(db)
    ensure_payment_method_accepted(db, payment_method, request.delivery_method)
    order = _new_order(db, request, OrderSource.WEB)
    order.customer_id = user.id if user is not None and user.is_customer else None
    order.needs_attention = True
    _assign_delay(db, order)
    order.payment_method = PaymentMethod(payment_method).value
    order.is_paid = False
    _attach_open_shift(db, order)

    _apply_coupon_discount(db, order, coupon_code)

    return _save(db, order)


def create_counter_order(db: Session, request: OrderRequest, payment: CounterPayment) -> Order:
    """Pedido presencial cargado por el personal en el mostrador.

    Como lo registra el propio local, entra directamente 'Confirmado' con la demora estimada
    automática, sin pasar por la aceptación (ni disparar la alerta de pedidos pendientes).
    Además registra (o actualiza) al cliente en la agenda del local para autocompletar sus
    próximos pedidos.
    """
    shift = cash_shift_service.get_current_open_shift(db)
    if not shift:
        raise BusinessRuleError("No se pueden tomar ni facturar pedidos porque la caja no está abierta. Abrí la caja antes de continuar.")

    ensure_payment_method_accepted(db, payment.method, request.delivery_method)
    order = _new_order(db, request, OrderSource.COUNTER)
    order.cash_shift_id = shift.id
    _assign_delay(db, order)
    order.payment_method = payment.method
    order.is_paid = payment.is_paid
    order = _save(db, order)
    _register_client(db, request)
    return order


def create_bot_order(
    db: Session,
    request: OrderRequest,
    channel: Channel | str | None,
    chat_id: str | None,
    scheduled_for: datetime | None,
    payment_method: str | None = None,
    coupon_code: str | None = None,
) -> Order:
    """Pedido confirmado por el cliente en el chat del bot (de cualquier canal): como los de la web, entra directamente
    'Confirmado' (en preparación) con la demora que corresponda, sin pasar por una aceptación del local."""
    ensure_payment_method_accepted(db, payment_method, request.delivery_method)
    order = _new_order(db, request, OrderSource.BOT)
    order.channel = Channel(channel).value if channel else None
    order.chat_id = chat_id
    order.scheduled_for = scheduled_for
    order.needs_attention = True
    _assign_delay(db, order)
    order.payment_method = payment_method
    order.is_paid = False
    _attach_open_shift(db, order)
    _apply_coupon_discount(db, order, coupon_code)
    order = _save(db, order)
    # Queda en la agenda (nombre, teléfono y dirección de envío) para reconocerlo en su próximo pedido.
    _register_client(db, request)
    return order


def _register_client(db: Session, request: OrderRequest) -> None:
    """Guarda los datos del cliente del pedido en la agenda.

    Se hace después de guardar el pedido y sin propagar errores: si la agenda falla, el pedido
    ya quedó registrado y el flujo de carga no se interrumpe.
    """
    address = request.shipping_address if DeliveryMethod(request.delivery_method) == DeliveryMethod.DELIVERY else None
    try:
        with transaction(db):
            upsert_client(db, request.customer_phone, request.customer_name, address)
    except SQLAlchemyError:
        logger.exception("No se pudo registrar al cliente del pedido en la agenda.")


# --- Consulta y ciclo de vida -------------------------------------------------------------------------


def list_orders(
    db: Session,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    statuses: list[str] | None = None,
    sector: str | None = None,
) -> list[Order]:
    """Pedidos registrados, del más reciente al más antiguo, filtrados por fecha de creación, estado y sector."""
    return order_repository.list_orders(db, date_from, date_to, statuses, sector)


def get_order(db: Session, order_id: int) -> Order:
    """Pedido con sus ítems y productos."""
    order = order_repository.get_with_items(db, order_id)
    if order is None:
        raise NotFoundError("Pedido no encontrado")
    return order


def _require_driver_change_allowed(order: Order) -> None:
    """Solo los envíos a domicilio llevan repartidor, y no se lo puede cambiar cuando su viaje ya salió: la ruta y
    los avisos ya están en curso."""
    if order.delivery_method != DeliveryMethod.DELIVERY.value:
        raise BusinessRuleError("Solo se pueden asignar repartidores a pedidos con envío a domicilio.")
    if order.is_dispatched:
        raise BusinessRuleError("El viaje de este pedido ya salió: no se puede cambiar el repartidor.")


def _find_active_driver(db: Session, delivery_driver_id: int) -> DeliveryDriver:
    driver = delivery_driver_repository.get(db, delivery_driver_id)
    if driver is None:
        raise NotFoundError("Repartidor no encontrado.")
    if not driver.is_active:
        raise BusinessRuleError("Solo se pueden asignar repartidores activos.")
    return driver


def change_order_status(
    db: Session,
    order_id: int,
    new_status: OrderStatus | str,
    delivery_driver_id: int | None = None,
) -> Order:
    """Avanza el pedido al nuevo estado según las reglas de su ciclo de vida (ver Order.transition_to)."""
    order = get_order(db, order_id)
    driver = None
    if delivery_driver_id is not None:
        _require_driver_change_allowed(order)
        driver = _find_active_driver(db, delivery_driver_id)

    with transaction(db):
        if driver is not None:
            order.delivery_driver_id = driver.id
        order.transition_to(new_status)
        if order.status == OrderStatus.COMPLETED.value and order.awaits_cash_payment:
            _collect_cash_payment(db, order)
    db.refresh(order)
    return order


def _collect_cash_payment(db: Session, order: Order) -> None:
    """Un pedido en efectivo se cobra al entregarlo: al finalizar entra a la caja, sin marcarlo a mano."""
    order.is_paid = True
    if not order.cash_shift_id:
        _attach_open_shift(db, order)


def assign_delivery_driver(
    db: Session, order_id: int, delivery_driver_id: int | None
) -> Order:
    """Asigna (o desasigna) un repartidor de la lista de personal activo a un pedido con envío a domicilio."""
    order = get_order(db, order_id)
    _require_driver_change_allowed(order)
    driver = _find_active_driver(db, delivery_driver_id) if delivery_driver_id is not None else None
    with transaction(db):
        order.delivery_driver_id = driver.id if driver else None
    db.refresh(order)
    return order


def _release_from_closed_shift(order: Order, is_paid: bool) -> None:
    """Lo que ya se cobró en un turno cerrado no se toca. Pero un pedido que quedó abierto sin cobrar al cerrar la
    caja se cobra recién ahora: ese dinero entra en el turno que está abierto."""
    if not is_paid or order.is_paid or order.amount_paid > 0:
        raise BusinessRuleError("No se puede modificar el pago de un pedido con turno de caja cerrado.")
    order.cash_shift_id = None


def _require_open_shift_to_collect(db: Session, order: Order) -> None:
    shift = cash_shift_service.get_current_open_shift(db)
    if not shift:
        raise BusinessRuleError("No se pueden cobrar pedidos porque no hay una caja abierta.")
    order.cash_shift_id = shift.id


def update_order_payment(
    db: Session,
    order_id: int,
    is_paid: bool | None = None,
    payment_method: PaymentMethod | str | None = None,
) -> Order:
    """Actualiza manualmente el estado de cobro de un pedido o su medio de pago."""
    order = get_order(db, order_id)
    if payment_method is not None:
        change_order_payment_method(db, order, payment_method)
    if is_paid is not None:
        with transaction(db):
            if order.is_shift_closed:
                _release_from_closed_shift(order, is_paid)
            if is_paid and not order.cash_shift_id:
                _require_open_shift_to_collect(db, order)
            order.is_paid = is_paid
    db.refresh(order)
    return order


def update_order_item_prepared(db: Session, order_id: int, item_id: int, is_prepared: bool) -> Order:
    """Marca o desmarca un ítem individual de una comanda como preparado."""
    order = get_order(db, order_id)
    item = next((i for i in order.items if i.id == item_id), None)
    if item is None:
        raise NotFoundError("Ítem no encontrado en el pedido.")
    with transaction(db):
        item.is_prepared = is_prepared
    db.refresh(order)
    return order


def update_order_sector_prepared(db: Session, order_id: int, sector: str, is_prepared: bool) -> Order:
    """Marca o desmarca todos los ítems de un sector en una comanda como preparados."""
    order = get_order(db, order_id)
    sector_clean = sector.strip().lower()
    sector_items = [item for item in order.items if item.sector.lower() == sector_clean]
    if not sector_items:
        raise NotFoundError(f"No hay ítems para el sector '{sector}' en este pedido.")
    with transaction(db):
        for item in sector_items:
            item.is_prepared = is_prepared
    db.refresh(order)
    return order


# --- Cambios que pide el cliente sobre un pedido ya registrado ----------------------------------------


def find_latest_chat_order(db: Session, channel: Channel | str, chat_id: str) -> Order | None:
    """Último pedido del cliente de ese chat, para modificarlo (ver Order.add_items y Order.change_payment_method)."""
    return order_repository.latest_for_chat(db, Channel(channel).value, chat_id)


def add_items_to_order(db: Session, order: Order, items: list[tuple]) -> Decimal:
    """Suma productos a un pedido ya registrado y devuelve lo que costaron. Cocina ve el aviso en su tablero."""
    products = _products_for(db, items)
    with transaction(db):
        added = order.add_items(products)
    db.refresh(order)
    return added


def change_order_payment_method(db: Session, order: Order, method: PaymentMethod | str) -> None:
    """Cambia el medio de pago del pedido (o el de la diferencia, si tiene un pago parcial). No toca a cocina."""
    ensure_payment_method_accepted(db, method, order.delivery_method)
    with transaction(db):
        order.change_payment_method(method)
    db.refresh(order)


def acknowledge_kitchen_update(db: Session, order_id: int) -> Order:
    """Cocina vio los productos agregados: se apaga la alerta del tablero."""
    order = get_order(db, order_id)
    with transaction(db):
        order.kitchen_update_pending = False
    db.refresh(order)
    return order


def acknowledge_new_order(db: Session, order_id: int) -> Order:
    """El personal vio el pedido nuevo: se apaga su alerta sonora en el tablero."""
    order = get_order(db, order_id)
    with transaction(db):
        order.needs_attention = False
    db.refresh(order)
    return order


def update_estimated_minutes(db: Session, order_id: int, minutes: int) -> Order:
    """El personal modifica a mano la demora de un pedido (queda como 'manual'). No afecta a los demás pedidos."""
    order = get_order(db, order_id)
    with transaction(db):
        order.set_estimated_minutes(minutes)
    db.refresh(order)
    return order
