"""Reglas de demora fija por método de entrega (US-65): "con hasta N pedidos en cola, X minutos"."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.db.session import transaction
from app.models.delay_rule import DelayRule
from app.models.order import DeliveryMethod
from app.repositories import delay_rule_repository
from app.services.store_config_service import get_or_create_store_config

_OPEN_ENDED_ONLY_LAST = 'El valor "o más" solo puede estar en la última regla.'


@dataclass(frozen=True)
class DelayRuleData:
    delivery_method: str
    min_orders: int
    # None: "o más".
    max_orders: int | None
    minutes: int


def _label(min_orders: int, max_orders: int | None) -> str:
    if max_orders is None:
        return f"{min_orders} o más"
    return f"{min_orders} a {max_orders}"


def _overlap(min_a: int, max_a: int | None, min_b: int, max_b: int | None) -> bool:
    return (max_b is None or min_a <= max_b) and (max_a is None or min_b <= max_a)


def _validate(data: DelayRuleData, others: list[DelayRule]) -> None:
    if data.minutes <= 0:
        raise BusinessRuleError("Los minutos de demora deben ser mayores a 0.")
    if data.min_orders < 0:
        raise BusinessRuleError("La cantidad de pedidos en cola no puede ser negativa.")
    if data.max_orders is not None and data.max_orders < data.min_orders:
        raise BusinessRuleError("El fin del rango no puede ser menor que el inicio.")

    for other in others:
        if not _overlap(data.min_orders, data.max_orders, other.min_orders, other.max_orders):
            continue
        if data.max_orders is None or other.max_orders is None:
            raise BusinessRuleError(
                f'{_OPEN_ENDED_ONLY_LAST[:-1]}: "{_label(data.min_orders, data.max_orders)}" se superpone con '
                f'"{_label(other.min_orders, other.max_orders)}".'
            )
        raise BusinessRuleError(
            f'El rango "{_label(data.min_orders, data.max_orders)}" se superpone con '
            f'"{_label(other.min_orders, other.max_orders)}".'
        )
    # Sin superposición, "o más" solo puede quedar último.
    if data.max_orders is None and any(other.min_orders > data.min_orders for other in others):
        raise BusinessRuleError(_OPEN_ENDED_ONLY_LAST)
    if data.max_orders is not None and any(
        other.max_orders is None and other.min_orders < data.min_orders for other in others
    ):
        raise BusinessRuleError(_OPEN_ENDED_ONLY_LAST)


def list_rules(db: Session) -> dict[str, list[DelayRule]]:
    return {method.value: delay_rule_repository.list_for_method(db, method.value) for method in DeliveryMethod}


def _others(db: Session, method: str, exclude_id: int | None = None) -> list[DelayRule]:
    return [r for r in delay_rule_repository.list_for_method(db, method) if r.id != exclude_id]


def create_rule(db: Session, data: DelayRuleData) -> DelayRule:
    method = DeliveryMethod(data.delivery_method).value
    _validate(data, _others(db, method))
    with transaction(db):
        rule = delay_rule_repository.add(
            db,
            DelayRule(delivery_method=method, min_orders=data.min_orders, max_orders=data.max_orders, minutes=data.minutes),
        )
    db.refresh(rule)
    return rule


def get_rule(db: Session, rule_id: int) -> DelayRule:
    rule = delay_rule_repository.get(db, rule_id)
    if rule is None:
        raise NotFoundError("Regla de demora no encontrada.")
    return rule


def update_rule(db: Session, rule_id: int, data: DelayRuleData) -> DelayRule:
    rule = get_rule(db, rule_id)
    # El método de entrega de una regla no se cambia: se elimina y se crea en el otro.
    _validate(data, _others(db, rule.delivery_method, rule.id))
    with transaction(db):
        rule.min_orders = data.min_orders
        rule.max_orders = data.max_orders
        rule.minutes = data.minutes
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int) -> None:
    rule = get_rule(db, rule_id)
    with transaction(db):
        delay_rule_repository.delete(db, rule)


def rule_for(db: Session, delivery_method: str, queue_size: int) -> DelayRule | None:
    """La regla del método que cubre esa cantidad de pedidos en cola (None si ninguna la cubre)."""
    return next((r for r in delay_rule_repository.list_for_method(db, delivery_method) if r.covers(queue_size)), None)


def is_smart_delay_enabled(db: Session) -> bool:
    return bool(get_or_create_store_config(db).smart_delay_enabled)


def set_smart_delay_enabled(db: Session, enabled: bool) -> bool:
    with transaction(db):
        get_or_create_store_config(db).smart_delay_enabled = enabled
    return enabled
