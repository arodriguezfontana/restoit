from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DelayRuleInput(BaseModel):
    """Regla de demora fija. Las validaciones de negocio (rangos, minutos) las hace el servicio."""

    delivery_method: Literal["retiro", "domicilio"] = Field(..., description="Método de entrega al que aplica.")
    min_orders: int = Field(..., le=10_000, description="Desde cuántos pedidos en cola aplica (inclusive).")
    max_orders: int | None = Field(None, le=10_000, description="Hasta cuántos pedidos en cola (inclusive); vacío es 'o más'.")
    minutes: int = Field(..., le=10_000, description="Minutos de demora que se prometen.")


class DelayRuleUpdate(BaseModel):
    min_orders: int = Field(..., le=10_000)
    max_orders: int | None = Field(None, le=10_000)
    minutes: int = Field(..., le=10_000)


class DelayRuleResponse(BaseModel):
    id: int
    delivery_method: str
    min_orders: int
    max_orders: int | None
    minutes: int

    model_config = ConfigDict(from_attributes=True)


class DelaySettingsResponse(BaseModel):
    """Cómo se calcula la demora de los pedidos: demora inteligente y reglas fijas de cada método de entrega."""

    smart_delay_enabled: bool
    pickup_rules: list[DelayRuleResponse]
    delivery_rules: list[DelayRuleResponse]


class SmartDelayUpdate(BaseModel):
    enabled: bool
