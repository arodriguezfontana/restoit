"""Servicio de Copilot Comercial Q&A asistido por consultas directas a la base de datos real e IA."""

import collections
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google import genai
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import RESTAURANT_TZ, ahora_local
from app.models.order import Order, OrderStatus
from app.repositories import analytics_repository, ingredient_repository, order_repository
from app.schemas.predictive_schemas import (
    ConversationMessage,
    CopilotAnswerResponse,
    CopilotQuestionPayload,
)
from app.services import analytics_service, predictive_service
from app.services.gemini_models import modelos
from app.services.ingredient_service import consumption_totals
from app.services.stats_service import WEEKDAYS

logger = logging.getLogger(__name__)

COPILOT_TIMEOUT_SECONDS = 9


def _format_date(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")


def _get_date_range_from_question(question: str) -> tuple[datetime, datetime, str]:
    """Interpreta el período de tiempo mencionado en la pregunta o usa los últimos 30 días."""
    q = question.lower()
    now = ahora_local()

    if "este mes" in q or "del mes" in q or "en el mes" in q:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now, f"Mes actual ({_format_date(start)} al {_format_date(now)})"

    if "mes pasado" in q or "mes anterior" in q:
        first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_prev_month = first_this_month - timedelta(days=1)
        start_prev_month = last_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return (
            start_prev_month,
            last_prev_month.replace(hour=23, minute=59, second=59),
            f"Mes pasado ({_format_date(start_prev_month)} al {_format_date(last_prev_month)})",
        )

    if "esta semana" in q:
        start_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start_week, now, f"Esta semana ({_format_date(start_week)} al {_format_date(now)})"

    if (
        "semana pasada" in q
        or "última semana" in q
        or "ultima semana" in q
        or "ultimos 7 dias" in q
        or "últimos 7 días" in q
    ):
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, f"Últimos 7 días ({_format_date(start)} al {_format_date(now)})"

    if "hoy" in q:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, f"Hoy ({_format_date(now)})"

    if "ayer" in q:
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59)
        return start, end, f"Ayer ({_format_date(yesterday)})"

    # Período por defecto: últimos 30 días
    start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now, f"Últimos 30 días ({_format_date(start)} al {_format_date(now)})"


# --- Funciones de consulta sobre la base de datos real (Cero Alucinaciones) ----------------------------


def query_ingredient_spending(db: Session, date_from: datetime, date_to: datetime, limit: int = 5) -> dict[str, Any]:
    """Consulta insumos con mayor gasto acumulado en pedidos completados del período."""
    utc_from = date_from.astimezone(timezone.utc)
    utc_to = date_to.astimezone(timezone.utc)

    consumed = consumption_totals(db, utc_from, utc_to, ingredient_id=None)
    if not consumed:
        return {"items": [], "total_spent": 0.0, "count": 0}

    ing_ids = {c[0] for c in consumed}
    ingredients = ingredient_repository.get_many(db, ing_ids)

    ranked = []
    total_spent = 0.0
    for ing_id, name, unit, qty in consumed:
        ing_obj = ingredients.get(ing_id)
        unit_cost = float(ing_obj.cost or 0.0) if ing_obj else 0.0
        spent = round(qty * unit_cost, 2)
        total_spent += spent
        ranked.append(
            {
                "ingredient_id": ing_id,
                "ingredient_name": name,
                "unit": unit,
                "consumed_quantity": round(qty, 2),
                "unit_cost": unit_cost,
                "total_spent": spent,
            }
        )

    ranked.sort(key=lambda x: (x["total_spent"], x["consumed_quantity"]), reverse=True)
    return {
        "items": ranked[:limit],
        "total_spent": round(total_spent, 2),
        "count": len(ranked),
    }


def query_cancellations(db: Session, date_from: datetime, date_to: datetime) -> dict[str, Any]:
    """Analiza pedidos cancelados en el período: cantidad, tasa, día con mayor impacto y dinero caído."""
    utc_from = date_from.astimezone(timezone.utc)
    utc_to = date_to.astimezone(timezone.utc)

    orders = db.query(Order).filter(Order.created_at >= utc_from, Order.created_at <= utc_to).all()

    total_orders = len(orders)
    cancelled_orders = [o for o in orders if o.status == OrderStatus.CANCELLED.value]
    completed_orders = [o for o in orders if o.status == OrderStatus.COMPLETED.value]

    cancellations_by_dow: dict[str, int] = collections.defaultdict(int)
    cancellations_revenue_by_dow: dict[str, float] = collections.defaultdict(float)

    for o in cancelled_orders:
        local_dt = (
            o.created_at.astimezone(RESTAURANT_TZ)
            if o.created_at.tzinfo
            else o.created_at.replace(tzinfo=timezone.utc).astimezone(RESTAURANT_TZ)
        )
        dow_name = WEEKDAYS[local_dt.weekday()]
        cancellations_by_dow[dow_name] += 1
        cancellations_revenue_by_dow[dow_name] += float(o.total_amount or 0.0)

    worst_day = None
    worst_count = 0
    worst_revenue = 0.0
    if cancellations_by_dow:
        worst_day = max(cancellations_by_dow, key=lambda k: cancellations_by_dow[k])
        worst_count = cancellations_by_dow[worst_day]
        worst_revenue = cancellations_revenue_by_dow[worst_day]

    total_lost_revenue = sum(float(o.total_amount or 0.0) for o in cancelled_orders)
    cancellation_rate = round(len(cancelled_orders) / total_orders * 100.0, 1) if total_orders > 0 else 0.0

    return {
        "total_orders": total_orders,
        "completed_count": len(completed_orders),
        "cancelled_count": len(cancelled_orders),
        "cancellation_rate": cancellation_rate,
        "worst_day": worst_day,
        "worst_day_cancellations": worst_count,
        "worst_day_lost_revenue": round(worst_revenue, 2),
        "total_lost_revenue": round(total_lost_revenue, 2),
        "by_day": dict(cancellations_by_dow),
    }


def query_revenue_and_orders(db: Session, date_from: datetime, date_to: datetime) -> dict[str, Any]:
    """Facturación real, cantidad de pedidos y ticket promedio."""
    utc_from = date_from.astimezone(timezone.utc)
    utc_to = date_to.astimezone(timezone.utc)

    rev, billable_count = analytics_repository.billable_revenue_and_count(db, utc_from, utc_to)
    status_counts = analytics_repository.order_counts_by_status(db, utc_from, utc_to)
    completed_count = status_counts.get(OrderStatus.COMPLETED.value, 0)
    cancelled_count = status_counts.get(OrderStatus.CANCELLED.value, 0)
    total_orders = sum(status_counts.values())

    avg_ticket = (
        round(rev / completed_count, 2)
        if completed_count > 0
        else (round(rev / billable_count, 2) if billable_count > 0 else 0.0)
    )
    cancellation_rate = round(cancelled_count / total_orders * 100.0, 1) if total_orders > 0 else 0.0

    return {
        "revenue": round(rev, 2),
        "billable_orders": billable_count,
        "completed_orders": completed_count,
        "cancelled_orders": cancelled_count,
        "total_orders": total_orders,
        "average_ticket": avg_ticket,
        "cancellation_rate": cancellation_rate,
    }


def query_profitable_products(db: Session, date_from: datetime, date_to: datetime, limit: int = 5) -> dict[str, Any]:
    """Platos más rentables y su margen bruto según costos de recetas e ingredientes."""
    utc_from = date_from.astimezone(timezone.utc)
    utc_to = date_to.astimezone(timezone.utc)

    best_selling = order_repository.best_selling_products(db, utc_from, utc_to, limit=20)
    if not best_selling:
        return {"products": []}

    prod_names = [name for name, _, _ in best_selling]
    unit_costs = analytics_service.get_products_unit_cost(db, prod_names)

    products = []
    for name, qty, rev in best_selling:
        quantity = int(qty)
        revenue = float(rev)
        unit_cost = unit_costs.get(name, 0.0)
        total_cost = round(quantity * unit_cost, 2)
        profit = round(revenue - total_cost, 2)
        margin_pct = round((profit / revenue * 100.0), 1) if revenue > 0 else 0.0

        products.append(
            {
                "product_name": name,
                "quantity": quantity,
                "revenue": revenue,
                "unit_cost": unit_cost,
                "estimated_cost": total_cost,
                "gross_profit": profit,
                "margin_pct": margin_pct,
            }
        )

    # Ordenar por rentabilidad total y margen
    products.sort(key=lambda p: (p["gross_profit"], p["margin_pct"]), reverse=True)
    return {"products": products[:limit]}


def query_goals_progress(db: Session) -> dict[str, Any]:
    """Estado y cumplimiento de metas comerciales configuradas."""
    kpis = analytics_service.calculate_dashboard_kpis(db)
    goals = analytics_service.get_business_goals(db)

    goal_list = []
    for g in goals:
        progress_rev = round((kpis.revenue.current / g.target_revenue * 100.0), 1) if g.target_revenue > 0 else 0.0
        progress_ord = round((kpis.completed_orders_count / g.target_orders * 100.0), 1) if g.target_orders > 0 else 0.0
        rem_rev = max(0.0, g.target_revenue - kpis.revenue.current)
        rem_ord = max(0, g.target_orders - kpis.completed_orders_count)
        goal_list.append(
            {
                "period_type": g.period_type,
                "target_revenue": g.target_revenue,
                "actual_revenue": kpis.revenue.current,
                "revenue_progress_pct": progress_rev,
                "revenue_remaining": round(rem_rev, 2),
                "target_orders": g.target_orders,
                "actual_orders": kpis.completed_orders_count,
                "orders_progress_pct": progress_ord,
                "orders_remaining": rem_ord,
            }
        )

    return {
        "goals": goal_list,
        "current_revenue": kpis.revenue.current,
        "current_completed_orders": kpis.completed_orders_count,
    }


def query_weekend_purchases_forecast(db: Session) -> dict[str, Any]:
    """Insumos necesarios a comprar antes del fin de semana según proyecciones de demanda."""
    predictions = predictive_service.calculate_predictions(db, historical_weeks=8)

    weekend_days = [d for d in predictions.days if d.is_weekend]
    weekend_orders = sum(d.projected_orders for d in weekend_days)
    weekend_revenue = sum(d.projected_revenue for d in weekend_days)

    return {
        "weekend_projected_orders": weekend_orders,
        "weekend_projected_revenue": round(weekend_revenue, 2),
        "weekend_days": [d.model_dump() for d in weekend_days],
        "top_ingredient_demands": [ing.model_dump() for ing in predictions.ingredient_demands[:6]],
        "strategic_prescriptions": predictions.strategic_prescriptions,
    }


# --- Detección de intención y ejecución ----------------------------------------------------------------


def _detect_intent(question: str) -> str:
    """Clasifica la intención temática de la pregunta."""
    q = question.lower()

    if any(
        k in q
        for k in ["antes del fin de semana", "comprar antes", "insumos para el fin de semana", "compras fin de semana"]
    ):
        return "weekend_purchases"

    if any(k in q for k in ["cancelac", "cancelad", "pedidos caídos", "rechazad"]):
        return "cancellations"

    if any(
        k in q
        for k in ["insumo", "ingrediente", "mayor gasto", "más gasto", "mas gasto", "gasto acumulado", "costo insumos"]
    ):
        return "ingredient_spending"

    if any(
        k in q
        for k in [
            "rentab",
            "margen",
            "platos más rentables",
            "platos mas rentables",
            "plato más rentable",
            "más ganancia",
            "mas ganancia",
        ]
    ):
        return "profitable_dishes"

    if any(k in q for k in ["meta", "metas", "objetivo", "cumplimiento"]):
        return "goals"

    if any(k in q for k in ["factura", "venta", "cuánto vend", "cuanto vend", "recaud", "ticket promedio"]):
        return "revenue"

    if any(
        k in q for k in ["proyecci", "pronóstic", "pronostic", "próximos 7 días", "proximos 7 dias", "demanda futura"]
    ):
        return "weekend_purchases"

    # Default a facturación y pedidos
    return "revenue"


def _format_deterministic_answer(intent: str, data: dict[str, Any], cited_period: str) -> tuple[str, list[str]]:
    """Genera una respuesta determinística clara, precisa y profesional basada exclusivamente en los datos reales."""
    if intent == "ingredient_spending":
        items = data.get("items", [])
        if not items:
            return (
                f"En el período {cited_period} no se registraron consumos de insumos en pedidos completados.",
                ["¿Cuánto facturamos en este período?", "¿Cuáles son los platos más vendidos?"],
            )
        lines = [f"📊 **Insumos con mayor gasto acumulado en el período {cited_period}:**\n"]
        for i, item in enumerate(items[:5], 1):
            lines.append(
                f"{i}. **{item['ingredient_name']}**: Gasto acumulado de **${item['total_spent']:,.2f}** "
                f"({item['consumed_quantity']} {item['unit']} consumidos a ${item['unit_cost']:,.2f}/{item['unit']})."
            )
        lines.append(f"\n*Gasto total acumulado en insumos del período:* **${data.get('total_spent', 0):,.2f}**.")
        return "\n".join(lines), [
            "¿Qué insumos debería comprar antes del fin de semana?",
            "¿Cuáles son los platos más rentables?",
            "¿Qué día tuvimos más cancelaciones?",
        ]

    if intent == "cancellations":
        cancelled = data.get("cancelled_count", 0)
        total = data.get("total_orders", 0)
        rate = data.get("cancellation_rate", 0.0)
        worst_day = data.get("worst_day")
        worst_count = data.get("worst_day_cancellations", 0)
        lost = data.get("total_lost_revenue", 0.0)

        if cancelled == 0:
            return (
                f"✅ En el período {cited_period} **no se registraron cancelaciones** (tasa del 0% sobre {total} pedidos ingresados).",
                ["¿Cuánto facturamos en el período?", "¿Cuáles son los platos más rentables?"],
            )

        worst_text = (
            f"El día con mayor concentración de cancelaciones fue **{worst_day}** con **{worst_count} pedidos cancelados**."
            if worst_day
            else ""
        )
        text = (
            f"⚠️ **Reporte de cancelaciones en el período {cited_period}:**\n\n"
            f"- **Pedidos cancelados:** {cancelled} de {total} pedidos (Tasa de cancelación: **{rate}%**).\n"
            f"- **Día más afectado:** {worst_text}\n"
            f"- **Facturación caída estimada:** **${lost:,.2f}**.\n\n"
            "💡 *Recomendación:* Verificar la exactitud de los tiempos de demora informados al cliente para evitar cancelaciones por espera prolongada."
        )
        return text, [
            "¿Cuáles son los 3 insumos con más gasto este mes?",
            "¿Qué insumos debería comprar antes del fin de semana?",
            "¿Cuánto facturamos la última semana?",
        ]

    if intent == "weekend_purchases":
        weekend_orders = data.get("weekend_projected_orders", 0)
        weekend_rev = data.get("weekend_projected_revenue", 0.0)
        ings = data.get("top_ingredient_demands", [])

        lines = [
            "🛒 **Insumos recomendados para comprar antes del fin de semana:**\n",
            f"Para el próximo fin de semana se proyecta un volumen de **{weekend_orders} pedidos** con una facturación estimada de **${weekend_rev:,.2f}**.\n",
            "**Insumos clave que deberías asegurar antes del viernes:**\n",
        ]
        for i, ing in enumerate(ings[:5], 1):
            prods = ", ".join(ing.get("contributing_products", [])[:2])
            lines.append(
                f"{i}. **{ing['ingredient_name']}**: Proyección de **{ing['projected_quantity']} {ing['unit']}** "
                f"(gasto estimado: ${ing['estimated_cost']:,.2f}) para cubrir platos como {prods}."
            )
        lines.append(
            "\n💡 *Acción recomendada:* Realizar las compras a distribuidores antes del jueves para evitar quiebres de stock en cocina durante el pico de ventas."
        )
        return "\n".join(lines), [
            "¿Cuáles son los 3 insumos con más gasto este mes?",
            "¿Qué día tuvimos más cancelaciones?",
            "¿Cómo viene el cumplimiento de las metas?",
        ]

    if intent == "profitable_dishes":
        products = data.get("products", [])
        if not products:
            return (
                f"En el período {cited_period} no se registran platos vendidos con receta para calcular rentabilidad.",
                ["¿Cuánto facturamos en este período?", "¿Qué insumos debería comprar antes del fin de semana?"],
            )
        lines = [f"🏆 **Platos más rentables en el período {cited_period}:**\n"]
        for i, p in enumerate(products[:5], 1):
            lines.append(
                f"{i}. **{p['product_name']}**: Margen del **{p['margin_pct']}%** "
                f"(Ganancia bruta: **${p['gross_profit']:,.2f}** sobre {p['quantity']} unidades vendidas. Costo unitario de insumos: ${p['unit_cost']:,.2f})."
            )
        return "\n".join(lines), [
            "¿Cuáles son los 3 insumos con más gasto este mes?",
            "¿Qué día tuvimos más cancelaciones?",
            "¿Cómo viene el cumplimiento de metas comerciales?",
        ]

    if intent == "goals":
        goals = data.get("goals", [])
        lines = [f"🎯 **Seguimiento del cumplimiento de metas comerciales ({cited_period}):**\n"]
        for g in goals:
            p_name = {"monthly": "Mensual", "weekly": "Semanal", "daily": "Diario"}.get(
                g["period_type"], g["period_type"].title()
            )
            lines.append(
                f"- **Meta {p_name}:** {g['revenue_progress_pct']}% alcanzado en facturación "
                f"(${g['actual_revenue']:,.2f} de ${g['target_revenue']:,.2f}, faltan ${g['revenue_remaining']:,.2f}) "
                f"y {g['orders_progress_pct']}% en pedidos ({g['actual_orders']} de {g['target_orders']} pedidos)."
            )
        return "\n".join(lines), [
            "¿Cuánto facturamos en este período?",
            "¿Cuáles son los platos más rentables?",
            "¿Qué insumos debería comprar antes del fin de semana?",
        ]

    # Intent default: revenue
    rev = data.get("revenue", 0.0)
    completed = data.get("completed_orders", 0)
    ticket = data.get("average_ticket", 0.0)
    rate = data.get("cancellation_rate", 0.0)
    text = (
        f"💰 **Rendimiento de ventas en el período {cited_period}:**\n\n"
        f"- **Facturación total:** **${rev:,.2f}**\n"
        f"- **Pedidos finalizados:** **{completed}**\n"
        f"- **Ticket promedio:** **${ticket:,.2f}** por pedido\n"
        f"- **Tasa de cancelación:** **{rate}%**\n"
    )
    return text, [
        "¿Cuáles son los 3 insumos con más gasto este mes?",
        "¿Cuáles son los platos más rentables?",
        "¿Qué día tuvimos más cancelaciones?",
    ]


def _synthesize_with_gemini(
    question: str,
    intent: str,
    data: dict[str, Any],
    cited_period: str,
    history: list[ConversationMessage] | None = None,
) -> tuple[str, list[str]] | None:
    """Solicita a Gemini sintetizar una respuesta ejecutiva y natural respetando 100% las cifras reales."""
    if not settings.GOOGLE_API_KEY:
        return None

    history_text = ""
    if history:
        history_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in history[-4:])

    prompt = f"""
Sos el Asistente Inteligente Comercial y Copilot de Negocio de un restaurante gastronómico.
El administrador te hace una consulta comercial puntual.
Respondé de manera ejecutiva, clara, directa y amable, citando explícitamente el período consultado.

REGLAS ESTRICTAS DE CERO ALUCINACIÓN:
1. Basate ÚNICAMENTE en estos DATOS REALES extraídos de la base de datos para responder.
2. NO inventes cifras, montos ni porcentajes que no estén en los DATOS REALES provistos.
3. Citá explícitamente el período: "{cited_period}".
4. Devolvé un JSON con:
   - "answer": Respuesta completa formateada en markdown con negritas y viñetas cuando corresponda.
   - "suggested_followups": Lista de 3 preguntas breves sugeridas de seguimiento para el administrador.

DATOS REALES DEL PERÍODO ({cited_period}):
{json.dumps(data, indent=2, ensure_ascii=False)}

HISTORIAL PREVIO (si aplica):
{history_text}

PREGUNTA DEL ADMINISTRADOR:
"{question}"

Respondé ÚNICAMENTE con un JSON válido con este esquema:
{{
  "answer": "Respuesta...",
  "suggested_followups": ["Pregunta 1", "Pregunta 2", "Pregunta 3"]
}}
"""
    try:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=modelos.principal,
            contents=prompt,
        )
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        parsed = json.loads(text)
        ans = parsed.get("answer")
        followups = parsed.get("suggested_followups", [])
        if ans:
            return ans, followups
    except Exception as e:
        logger.warning("Fallo en Gemini Copilot Q&A: %s. Procediendo a degradación controlada.", e)

    return None


def ask_copilot(db: Session, payload: CopilotQuestionPayload) -> CopilotAnswerResponse:
    """Procesa una consulta del usuario mediante ejecución de consultas reales sobre la base de datos e IA."""
    question = payload.question.strip()
    date_from, date_to, cited_period = _get_date_range_from_question(question)
    intent = _detect_intent(question)

    # 1. Ejecutar la función interna de consulta correspondiente sobre la base de datos real
    data_summary: dict[str, Any] = {}
    if intent == "ingredient_spending":
        data_summary = query_ingredient_spending(db, date_from, date_to, limit=5)
    elif intent == "cancellations":
        data_summary = query_cancellations(db, date_from, date_to)
    elif intent == "profitable_dishes":
        data_summary = query_profitable_products(db, date_from, date_to, limit=5)
    elif intent == "goals":
        data_summary = query_goals_progress(db)
    elif intent == "weekend_purchases":
        data_summary = query_weekend_purchases_forecast(db)
        cited_period = "Próximo fin de semana y demanda estimada a 7 días"
    else:  # revenue
        data_summary = query_revenue_and_orders(db, date_from, date_to)

    # 2. Intentar síntesis con Gemini
    gemini_result = _synthesize_with_gemini(
        question=question,
        intent=intent,
        data=data_summary,
        cited_period=cited_period,
        history=payload.conversation_history,
    )

    if gemini_result:
        answer, followups = gemini_result
        return CopilotAnswerResponse(
            answer=answer,
            cited_period=cited_period,
            data_summary=data_summary,
            suggested_followups=followups,
            is_fallback=False,
            generated_at=datetime.now(timezone.utc),
        )

    # 3. Degradación controlada: generar respuesta determinística fundamentada
    det_answer, det_followups = _format_deterministic_answer(intent, data_summary, cited_period)
    fallback_note = (
        "\n\n*(Respuesta directa calculada a partir de los datos registrados en el sistema. "
        "Si deseás análisis interpretativo por IA, podés reintentar en un momento)*"
    )

    return CopilotAnswerResponse(
        answer=det_answer + fallback_note,
        cited_period=cited_period,
        data_summary=data_summary,
        suggested_followups=det_followups,
        is_fallback=True,
        generated_at=datetime.now(timezone.utc),
    )
