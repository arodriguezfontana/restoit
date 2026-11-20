from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.schemas.delay_rule_schemas import (
    DelayRuleInput,
    DelayRuleResponse,
    DelayRuleUpdate,
    DelaySettingsResponse,
    SmartDelayUpdate,
)
from app.services import delay_rule_service
from app.services.delay_rule_service import DelayRuleData

router = APIRouter(dependencies=[Depends(get_current_admin)])


def _settings(db: Session) -> DelaySettingsResponse:
    rules = delay_rule_service.list_rules(db)
    return DelaySettingsResponse(
        smart_delay_enabled=delay_rule_service.is_smart_delay_enabled(db),
        pickup_rules=[DelayRuleResponse.model_validate(r) for r in rules["retiro"]],
        delivery_rules=[DelayRuleResponse.model_validate(r) for r in rules["domicilio"]],
    )


@router.get("")
def get_delay_settings(db: Session = Depends(get_db)) -> DelaySettingsResponse:
    """Demora inteligente (activada o no) y reglas de demora fija de retiro y envío."""
    return _settings(db)


@router.put("/smart")
def set_smart_delay(payload: SmartDelayUpdate, db: Session = Depends(get_db)) -> DelaySettingsResponse:
    """Activa o desactiva la demora inteligente (con historial). Desactivada, el sistema no la calcula ni la sugiere."""
    delay_rule_service.set_smart_delay_enabled(db, payload.enabled)
    return _settings(db)


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_delay_rule(payload: DelayRuleInput, db: Session = Depends(get_db)) -> DelayRuleResponse:
    """Agrega una regla de demora fija a un método de entrega."""
    rule = delay_rule_service.create_rule(
        db, DelayRuleData(payload.delivery_method, payload.min_orders, payload.max_orders, payload.minutes)
    )
    return DelayRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}")
def update_delay_rule(rule_id: int, payload: DelayRuleUpdate, db: Session = Depends(get_db)) -> DelayRuleResponse:
    """Modifica una regla de demora fija. No cambia las demoras de los pedidos ya tomados."""
    existing = delay_rule_service.get_rule(db, rule_id)
    rule = delay_rule_service.update_rule(
        db,
        rule_id,
        DelayRuleData(existing.delivery_method, payload.min_orders, payload.max_orders, payload.minutes),
    )
    return DelayRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_delay_rule(rule_id: int, db: Session = Depends(get_db)) -> Response:
    delay_rule_service.delete_rule(db, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
