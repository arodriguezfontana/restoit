"""Esquemas de datos para analítica predictiva de demanda, proyección de insumos y Copilot Q&A comercial."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DayProjectionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: str = Field(..., description="Fecha en formato YYYY-MM-DD")
    day_name: str = Field(..., description="Nombre del día en español (ej. 'Lunes')")
    is_weekend: bool = Field(..., description="Verdadero si es sábado o domingo")
    projected_orders: int = Field(..., ge=0, description="Volumen estimado de pedidos")
    projected_revenue: float = Field(..., ge=0, description="Facturación proyectada estimada")


class IngredientDemandItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredient_id: int
    ingredient_name: str
    unit: str
    projected_quantity: float = Field(..., ge=0, description="Cantidad proyectada requerida para los próximos 7 días")
    unit_cost: float = Field(default=0.0, ge=0, description="Costo unitario actual del insumo")
    estimated_cost: float = Field(default=0.0, ge=0, description="Gasto monetario estimado de reposición")
    contributing_products: list[str] = Field(
        default_factory=list, description="Platos principales que demandan este insumo"
    )


class PredictionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    days: list[DayProjectionItem]
    total_projected_orders: int = Field(..., ge=0)
    total_projected_revenue: float = Field(..., ge=0)
    weekday_projected_orders: int = Field(..., ge=0)
    weekday_projected_revenue: float = Field(..., ge=0)
    weekend_projected_orders: int = Field(..., ge=0)
    weekend_projected_revenue: float = Field(..., ge=0)
    avg_daily_orders: float = Field(..., ge=0)
    avg_daily_revenue: float = Field(..., ge=0)
    ingredient_demands: list[IngredientDemandItem]
    strategic_prescriptions: list[str] = Field(default_factory=list)
    is_ai_generated: bool = Field(default=False, description="Si las recomendaciones fueron redactadas por Gemini")
    historical_weeks_analyzed: int = Field(default=8)
    disclaimer: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationMessage(BaseModel):
    role: str = Field(..., description="'user' o 'assistant'")
    content: str


class CopilotQuestionPayload(BaseModel):
    question: str = Field(..., min_length=1, description="Pregunta ad-hoc en lenguaje natural del administrador")
    conversation_history: list[ConversationMessage] | None = None


class CopilotSuggestedAction(BaseModel):
    action_type: str = Field(..., description="Tipo de acción: 'deactivate_product', 'activate_product', 'create_promotion'")
    title: str = Field(..., description="Título de la tarjeta de acción")
    description: str = Field(..., description="Descripción breve de lo que hará la acción")
    button_label: str = Field(..., description="Texto del botón de confirmación")
    payload: dict[str, Any] = Field(default_factory=dict, description="Parámetros requeridos para ejecutar la acción")


class CopilotActionExecutionPayload(BaseModel):
    action_type: str = Field(..., description="Tipo de acción a ejecutar")
    payload: dict[str, Any] = Field(default_factory=dict, description="Parámetros de la acción")


class CopilotActionExecutionResponse(BaseModel):
    success: bool
    message: str
    executed_action: str
    affected_entity_id: int | None = None


class CopilotAnswerResponse(BaseModel):
    answer: str = Field(..., description="Respuesta concisa y fundamentada en datos reales")
    cited_period: str = Field(..., description="Período de tiempo consultado citado explícitamente")
    data_summary: dict[str, Any] | None = Field(default=None, description="Datos cuantitativos reales consultados")
    suggested_followups: list[str] = Field(default_factory=list)
    suggested_action: CopilotSuggestedAction | None = Field(default=None, description="Acción sugerida opcional que el usuario puede elegir ejecutar")
    is_fallback: bool = Field(default=False, description="Indica si se usó motor determinístico por degradación de IA")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
