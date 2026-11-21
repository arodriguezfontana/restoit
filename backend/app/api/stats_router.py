from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, require_admin_pin
from app.db.session import get_db
from app.schemas.analytics_schemas import (
    BusinessGoalItem,
    BusinessGoalsResponse,
    DashboardKPIsResponse,
    StrategicInsightResponse,
    UpdateBusinessGoalsPayload,
)
from app.schemas.ingredient_schemas import IngredientConsumptionResponse
from app.schemas.predictive_schemas import (
    CopilotActionExecutionPayload,
    CopilotActionExecutionResponse,
    CopilotAnswerResponse,
    CopilotQuestionPayload,
    PredictionsResponse,
)
from app.schemas.stats_schemas import BestSellingDayResponse, StatusDistributionResponse, TopProductResponse
from app.services import analytics_service, copilot_service, predictive_service, stats_service
from app.services.ingredient_service import ingredient_consumption

router = APIRouter(dependencies=[Depends(require_admin_pin)])


def _goals_response(goals: list[analytics_service.BusinessGoalData]) -> BusinessGoalsResponse:
    return BusinessGoalsResponse(goals=[BusinessGoalItem.model_validate(goal) for goal in goals])


# --- Endpoints Clásicos (Retrocompatibilidad) ---------------------------------------------------------


@router.get(
    "/status-distribution",
    dependencies=[Depends(get_current_admin)],
)
def get_status_distribution(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: Session = Depends(get_db),
) -> StatusDistributionResponse:
    """Cantidad de pedidos del período en cada estado."""
    return StatusDistributionResponse(status_distribution=stats_service.status_distribution(db, date_from, date_to))


@router.get("/top-products", dependencies=[Depends(get_current_admin)])
def get_top_products(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[TopProductResponse]:
    """Productos más vendidos del período, sin contar los pedidos cancelados."""
    return [TopProductResponse.from_stat(stat) for stat in stats_service.top_products(db, date_from, date_to, limit)]


@router.get("/best-selling-day", dependencies=[Depends(get_current_admin)])
def get_best_selling_day(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: Session = Depends(get_db),
) -> BestSellingDayResponse:
    """Día de la semana con mayor facturación del período."""
    return BestSellingDayResponse.from_stat(stats_service.best_selling_day(db, date_from, date_to))


@router.get(
    "/ingredient-consumption",
    dependencies=[Depends(get_current_admin)],
)
def get_ingredient_consumption(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    ingredient_id: int | None = Query(None, description="Muestra solo el consumo de este ingrediente."),
    db: Session = Depends(get_db),
) -> IngredientConsumptionResponse:
    """Total de cada ingrediente usado en los pedidos finalizados del período, según las recetas."""
    return IngredientConsumptionResponse.from_report(ingredient_consumption(db, date_from, date_to, ingredient_id))


# --- US-49: Dashboard de Metas de Negocio y Rendimiento Comercial ------------------------------------


@router.get("/kpis", dependencies=[Depends(get_current_admin)])
def get_dashboard_kpis(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: Session = Depends(get_db),
) -> DashboardKPIsResponse:
    """Calcula métricas clave avanzadas (ticket promedio, tasa de cancelación, margen bruto y costos,

    crecimiento porcentual vs. período previo y seguimiento de metas).
    """
    return DashboardKPIsResponse.model_validate(analytics_service.calculate_dashboard_kpis(db, date_from, date_to))


@router.get("/goals", dependencies=[Depends(get_current_admin)])
def get_goals(
    db: Session = Depends(get_db),
) -> BusinessGoalsResponse:
    """Obtiene las metas comerciales configuradas para los diferentes períodos."""
    return _goals_response(analytics_service.get_business_goals(db))


@router.put("/goals", dependencies=[Depends(get_current_admin)])
def put_goals(
    payload: UpdateBusinessGoalsPayload,
    db: Session = Depends(get_db),
) -> BusinessGoalsResponse:
    """Establece o actualiza las metas cuantitativas del negocio."""
    goals = [
        analytics_service.BusinessGoalData(g.period_type, g.target_revenue, g.target_orders) for g in payload.goals
    ]
    return _goals_response(analytics_service.update_business_goals(db, goals))


@router.get("/strategic-insight", dependencies=[Depends(get_current_admin)])
def get_strategic_insight(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: Session = Depends(get_db),
) -> StrategicInsightResponse:
    """Genera un análisis e informe ejecutivo inteligente asistido por IA / BI sobre las métricas comerciales."""
    kpis = analytics_service.calculate_dashboard_kpis(db, date_from, date_to)
    insight = analytics_service.generate_strategic_insight(kpis, db=db, date_from=date_from, date_to=date_to)
    return StrategicInsightResponse.model_validate(insight)


# --- US-67: Analítica Predictiva y Copilot Q&A Comercial ---------------------------------------------


@router.get("/predictions", dependencies=[Depends(get_current_admin)])
def get_predictions(
    weeks: int = Query(26, ge=4, le=52, description="Semanas históricas analizadas para la proyección (6 meses por defecto)"),
    db: Session = Depends(get_db),
) -> PredictionsResponse:
    """Calcula proyecciones de pedidos y facturación a 7 días (diferenciando semana y fin de semana)

    y demanda proyectada de insumos según recetas, con recomendaciones estratégicas de IA / Gemini.
    """
    return predictive_service.calculate_predictions(db, historical_weeks=weeks)


@router.post("/copilot/ask", dependencies=[Depends(get_current_admin)])
def ask_copilot(
    payload: CopilotQuestionPayload,
    db: Session = Depends(get_db),
) -> CopilotAnswerResponse:
    """Asistente Q&A comercial que responde preguntas en lenguaje natural ejecutando funciones sobre

    la base de datos real con cero alucinaciones numéricas y citando el período consultado.
    """
    return copilot_service.ask_copilot(db, payload)


@router.post("/copilot/execute-action", dependencies=[Depends(get_current_admin)])
def execute_copilot_action(
    payload: CopilotActionExecutionPayload,
    db: Session = Depends(get_db),
) -> CopilotActionExecutionResponse:
    """Ejecuta una acción comercial aprobada por el administrador generada por el Copilot (Human-in-the-Loop)."""
    return copilot_service.execute_copilot_action(db, payload)

