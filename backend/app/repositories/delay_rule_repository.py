from sqlalchemy.orm import Session

from app.models.delay_rule import DelayRule


def list_for_method(db: Session, delivery_method: str) -> list[DelayRule]:
    """Reglas del método de entrega, de menor a mayor cantidad de pedidos en cola."""
    return (
        db.query(DelayRule)
        .filter(DelayRule.delivery_method == delivery_method)
        .order_by(DelayRule.min_orders.asc(), DelayRule.id.asc())
        .all()
    )


def get(db: Session, rule_id: int) -> DelayRule | None:
    return db.get(DelayRule, rule_id)


def add(db: Session, rule: DelayRule) -> DelayRule:
    """Registra la regla (sin confirmar la transacción)."""
    db.add(rule)
    db.flush()
    return rule


def delete(db: Session, rule: DelayRule) -> None:
    db.delete(rule)
    db.flush()
