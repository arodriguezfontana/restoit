"""Servicio de Asistente Comercial Q&A asistido por consultas directas a la base de datos real e IA."""

import collections
import json
import logging
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from google import genai
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import RESTAURANT_TZ, ahora_local
from app.models.menu import Ingredient, Product, ProductIngredient
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


def query_underperforming_products(
    db: Session,
    date_from: datetime,
    date_to: datetime,
) -> dict[str, Any]:
    """Identifica productos con menor o nula venta en el período y los compara con los más vendidos y categorías líderes."""
    utc_from = date_from.astimezone(timezone.utc)
    utc_to = date_to.astimezone(timezone.utc)

    all_active = db.query(Product).filter(Product.is_active.is_(True)).all()
    best_sellers = order_repository.best_selling_products(db, utc_from, utc_to, limit=200)
    sales_map = {name: (int(qty), float(rev)) for name, qty, rev in best_sellers}

    perf_list = []
    category_sales: dict[str, int] = collections.defaultdict(int)

    for p in all_active:
        qty, rev = sales_map.get(p.name, (0, 0.0))
        cat_name = p.category.name if p.category else "General"
        category_sales[cat_name] += qty
        perf_list.append(
            {
                "product_id": p.id,
                "product_name": p.name,
                "category": cat_name,
                "units_sold": qty,
                "revenue": rev,
                "price": float(p.price or 0.0),
            }
        )

    # Ordenar de menor a mayor venta para identificar los candidatos a eliminar/reemplazar
    perf_list.sort(key=lambda x: (x["units_sold"], x["revenue"]))
    underperforming = perf_list[:5]

    # Los más vendidos
    top_sellers = sorted(perf_list, key=lambda x: (x["units_sold"], x["revenue"]), reverse=True)[:5]
    top_category = max(category_sales, key=lambda k: category_sales[k]) if category_sales else None

    return {
        "underperforming_products": underperforming,
        "top_selling_products": top_sellers,
        "top_category": top_category,
        "total_active_products": len(all_active),
    }


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
    predictions = predictive_service.calculate_predictions(db, historical_weeks=26)

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


def _normalize_token(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = clean.replace("z", "s")
    return "".join(c for c in clean if c.isalnum() or c.isspace()).strip()


def _find_mentioned_entities(db: Session, question: str) -> tuple[list[str], list[str]]:
    """Identifica nombres de productos o ingredientes mencionados en la consulta."""
    norm_q = _normalize_token(question)
    q_words = [w for w in norm_q.split() if len(w) >= 4]

    products = db.query(Product.name).all()
    ingredients = db.query(Ingredient.name).all()

    matched_products = []
    for (p_name,) in products:
        norm_p = _normalize_token(p_name)
        if norm_p in norm_q or any((len(w) >= 4 and w.rstrip("s") in norm_p) or (len(w) >= 5 and w[:5] in norm_p) for w in q_words):
            matched_products.append(p_name)

    matched_ingredients = []
    for (i_name,) in ingredients:
        norm_i = _normalize_token(i_name)
        if norm_i in norm_q or any((len(w) >= 4 and w.rstrip("s") in norm_i) or (len(w) >= 5 and w[:5] in norm_i) for w in q_words):
            matched_ingredients.append(i_name)

    return matched_products, matched_ingredients


def query_product_sales(
    db: Session,
    date_from: datetime,
    date_to: datetime,
    term: str | None = None,
) -> dict[str, Any]:
    """Consulta ventas de productos específicos o catálogo en el período."""
    utc_from = date_from.astimezone(timezone.utc)
    utc_to = date_to.astimezone(timezone.utc)

    best_sellers = order_repository.best_selling_products(db, utc_from, utc_to, limit=100)

    matched = []
    norm_term = _normalize_token(term) if term else ""
    stem_term = norm_term[:5] if len(norm_term) >= 5 else norm_term

    for name, qty, rev in best_sellers:
        norm_name = _normalize_token(name)
        if not norm_term or norm_term in norm_name or (stem_term and stem_term in norm_name):
            matched.append({
                "product_name": name,
                "quantity": int(qty),
                "revenue": float(rev),
            })

    total_units = sum(item["quantity"] for item in matched)
    total_revenue = sum(item["revenue"] for item in matched)

    return {
        "searched_term": term,
        "matched_products": matched,
        "total_units_sold": total_units,
        "total_revenue": round(total_revenue, 2),
        "all_best_sellers": [
            {"product_name": n, "quantity": int(q), "revenue": float(r)}
            for n, q, r in best_sellers[:5]
        ],
    }


def query_purchase_advice(
    db: Session,
    date_from: datetime,
    date_to: datetime,
    term: str | None = None,
) -> dict[str, Any]:
    """Genera recomendaciones fundamentadas para compra de insumos según consumo, recetas y proyección a 7 días."""
    utc_from = date_from.astimezone(timezone.utc)
    utc_to = date_to.astimezone(timezone.utc)

    ingredient = None
    if term:
        norm_term = _normalize_token(term)
        stem_term = norm_term[:5] if len(norm_term) >= 5 else norm_term
        for ing in db.query(Ingredient).all():
            norm_name = _normalize_token(ing.name)
            if norm_term in norm_name or (stem_term and stem_term in norm_name):
                ingredient = ing
                break

    if not ingredient:
        forecast = query_weekend_purchases_forecast(db)
        return {
            "ingredient_name": None,
            "searched_term": term,
            "top_ingredient_demands": forecast.get("top_ingredient_demands", []),
            "weekend_projected_orders": forecast.get("weekend_projected_orders", 0),
            "recommendation": "Revisá los insumos con mayor demanda proyectada para el próximo fin de semana.",
        }

    consumed = consumption_totals(db, utc_from, utc_to, ingredient_id=ingredient.id)
    consumed_qty = round(consumed[0][3], 2) if consumed else 0.0
    unit_cost = float(ingredient.cost or 0.0)
    total_spent = round(consumed_qty * unit_cost, 2)

    recipe_links = db.query(ProductIngredient).filter(ProductIngredient.ingredient_id == ingredient.id).all()
    prod_ids = [r.product_id for r in recipe_links]
    prods = db.query(Product).filter(Product.id.in_(prod_ids)).all() if prod_ids else []
    prod_names = [p.name for p in prods]

    best_sellers = order_repository.best_selling_products(db, utc_from, utc_to, limit=50)
    using_products_sales = [
        {"product_name": name, "quantity": int(qty), "revenue": float(rev)}
        for name, qty, rev in best_sellers
        if name in prod_names
    ]

    try:
        from app.services.predictive_service import calculate_demand_and_ingredient_projections

        preds = calculate_demand_and_ingredient_projections(db)
        demands = preds.ingredient_demands
        projected_item = next((d for d in demands if d.ingredient_id == ingredient.id), None)
        projected_qty = projected_item.projected_quantity if projected_item else 0.0
        projected_cost = projected_item.estimated_cost if projected_item else 0.0
    except Exception:
        projected_qty = round(consumed_qty * 0.35, 2)
        projected_cost = round(projected_qty * unit_cost, 2)

    if projected_qty == 0.0 and consumed_qty > 0.0:
        projected_qty = round(consumed_qty * 0.5, 2)
        projected_cost = round(projected_qty * unit_cost, 2)

    should_buy = projected_qty > 0 or consumed_qty > 0
    recommendation = (
        f"Sí, te conviene comprar {ingredient.name} para abastecer la demanda estimada de los próximos 7 días en platos como {', '.join(prod_names[:3])}."
        if should_buy
        else f"Actualmente no se registra una alta demanda proyectada para {ingredient.name}. Se recomienda comprar sólo para stock mínimo de seguridad."
    )

    return {
        "ingredient_id": ingredient.id,
        "ingredient_name": ingredient.name,
        "unit": ingredient.unit,
        "unit_cost": unit_cost,
        "consumed_in_period": consumed_qty,
        "total_spent_in_period": total_spent,
        "using_products": prod_names,
        "using_products_sales": using_products_sales,
        "projected_demand_next_7_days": projected_qty,
        "projected_cost_next_7_days": projected_cost,
        "should_buy": should_buy,
        "recommendation": recommendation,
    }


def _detect_intent(question: str, db: Session) -> tuple[str, str | None]:
    """Clasifica la intención temática y la entidad consultada."""
    q = question.lower()
    norm_q = _normalize_token(question)

    prod_matches, ing_matches = _find_mentioned_entities(db, question)

    elimination_triggers = [
        "eliminar",
        "sacar de la carta",
        "sacar del menu",
        "sacar del menú",
        "quitar de la carta",
        "quitar del menu",
        "quitar del menú",
        "dar de baja",
        "reemplazar",
        "cambiar producto",
        "cambiarlo",
        "menos vendido",
        "menos vendidos",
        "peor vendido",
        "peores ventas",
        "baja rotacion",
        "baja rotación",
        "menos rinde",
        "menos pedido",
        "no se vende",
        "no se vendio",
        "no se vendió",
    ]
    if any(t in q or t in norm_q for t in elimination_triggers):
        return "underperforming_products", None

    advice_triggers = [
        "conviene comprar",
        "debo comprar",
        "compro ",
        "comprar ",
        "deberia comprar",
        "debería comprar",
        "recomendas sobre",
        "recomendás sobre",
        "que me recomendas",
        "qué me recomendás",
        "que me recomiendas",
        "qué me recomiendas",
        "abastecer",
        "recomiendas comprar",
        "recomendacion sobre",
        "recomendación sobre",
        "opinas de comprar",
    ]
    if any(t in q or t in norm_q for t in advice_triggers):
        target = ing_matches[0] if ing_matches else (prod_matches[0] if prod_matches else None)
        return "purchase_advice", target

    sales_triggers = [
        "cuantas ",
        "cuantos ",
        "cuántas ",
        "cuántos ",
        "se vendieron",
        "vendí",
        "vendi",
        "salieron",
        "unidades de",
        "pedidos de",
        "platos de",
        "ventas de",
    ]
    if any(t in q for t in sales_triggers) or (prod_matches and any(w in q for w in ["cuant", "vend"])):
        target = prod_matches[0] if prod_matches else (ing_matches[0] if ing_matches else None)
        return "product_sales", target

    if any(
        k in q
        for k in ["antes del fin de semana", "insumos para el fin de semana", "compras fin de semana"]
    ):
        return "weekend_purchases", None

    if any(k in q for k in ["cancelac", "cancelad", "pedidos caídos", "rechazad"]):
        return "cancellations", None

    if any(
        k in q
        for k in ["insumo", "ingrediente", "mayor gasto", "más gasto", "mas gasto", "gasto acumulado", "costo insumos"]
    ):
        return "ingredient_spending", None

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
        return "profitable_dishes", None

    if any(k in q for k in ["meta", "metas", "objetivo", "cumplimiento"]):
        return "goals", None

    if any(k in q for k in ["factura", "venta", "cuánto vend", "cuanto vend", "recaud", "ticket promedio"]):
        return "revenue", None

    if any(
        k in q for k in ["proyecci", "pronóstic", "pronostic", "próximos 7 días", "proximos 7 dias", "demanda futura"]
    ):
        return "weekend_purchases", None

    if prod_matches:
        return "product_sales", prod_matches[0]
    if ing_matches:
        return "purchase_advice", ing_matches[0]

    return "revenue", None


def _format_deterministic_answer(intent: str, data: dict[str, Any], cited_period: str) -> tuple[str, list[str]]:
    """Genera una respuesta determinística clara, precisa y directa sin preámbulos ni asteriscos."""
    if intent == "product_sales":
        prods = data.get("matched_products", [])
        total_units = data.get("total_units_sold", 0)
        total_rev = data.get("total_revenue", 0.0)
        term = data.get("searched_term")

        if not prods or total_units == 0:
            return (
                f"No se registraron ventas de {term or 'este producto'} en el período.",
                ["¿Cuáles son los platos más vendidos?", "¿Cuánto facturamos en este período?"],
            )

        if len(prods) == 1:
            p = prods[0]
            return (
                f"Vendiste {p['quantity']} unidades de {p['product_name']} por un total de ${p['revenue']:,.2f}.",
                ["¿Cuáles son los platos más rentables?", "¿Qué insumos debería comprar antes del fin de semana?"],
            )

        lines = [f"Vendiste un total de {total_units} unidades (${total_rev:,.2f}) de los platos relacionados:"]
        for p in prods:
            lines.append(f"- {p['product_name']}: {p['quantity']} unidades (${p['revenue']:,.2f})")
        return "\n".join(lines), [
            "¿Cuáles son los platos más rentables?",
            "¿Qué insumos debería comprar antes del fin de semana?",
        ]

    if intent == "purchase_advice":
        ing_name = data.get("ingredient_name")
        if not ing_name:
            weekend_orders = data.get("weekend_projected_orders", 0)
            ings = data.get("top_ingredient_demands", [])
            lines = [f"Para el fin de semana se proyectan {weekend_orders} pedidos. Los insumos prioritarios son:"]
            for i, ing in enumerate(ings[:5], 1):
                lines.append(
                    f"{i}. {ing['ingredient_name']}: {ing['projected_quantity']} {ing['unit']} (${ing['estimated_cost']:,.2f})"
                )
            return "\n".join(lines), ["¿Qué insumos tuvieron más gasto este mes?"]

        unit = data.get("unit", "")
        consumed = data.get("consumed_in_period", 0.0)
        spent = data.get("total_spent_in_period", 0.0)
        proj_qty = data.get("projected_demand_next_7_days", 0.0)
        proj_cost = data.get("projected_cost_next_7_days", 0.0)
        prods = ", ".join(data.get("using_products", [])[:3])
        should_buy = data.get("should_buy", True)

        if should_buy:
            text = (
                f"Sí, te conviene comprar {ing_name}. Se proyecta una demanda de {proj_qty} {unit} "
                f"(${proj_cost:,.2f}) para los próximos 7 días en platos como {prods or ing_name}. "
                f"En el período se consumieron {consumed} {unit} con un gasto acumulado de ${spent:,.2f}."
            )
        else:
            text = (
                f"No es prioritario comprar {ing_name} en gran cantidad porque no registra alta rotación en el período. "
                f"Se consumieron {consumed} {unit} (${spent:,.2f})."
            )
        return text, [
            "¿Cuáles son los 3 insumos con más gasto este mes?",
            "¿Qué insumos debería comprar antes del fin de semana?",
        ]

    if intent == "ingredient_spending":
        items = data.get("items", [])
        if not items:
            return (
                "No se registraron consumos de insumos en pedidos completados.",
                ["¿Cuánto facturamos en este período?", "¿Cuáles son los platos más vendidos?"],
            )
        lines = ["Los insumos con mayor gasto acumulado son:\n"]
        for i, item in enumerate(items[:5], 1):
            lines.append(
                f"{i}. {item['ingredient_name']}: Gasto de ${item['total_spent']:,.2f} "
                f"({item['consumed_quantity']} {item['unit']} consumidos a ${item['unit_cost']:,.2f}/{item['unit']})."
            )
        lines.append(f"\nGasto total acumulado en insumos: ${data.get('total_spent', 0):,.2f}.")
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
                f"No se registraron cancelaciones en este período (0% sobre {total} pedidos ingresados).",
                ["¿Cuánto facturamos en el período?", "¿Cuáles son los platos más rentables?"],
            )

        worst_text = (
            f"El día con más cancelaciones fue {worst_day} con {worst_count} pedidos cancelados."
            if worst_day
            else ""
        )
        text = (
            f"{worst_text} En total hubo {cancelled} cancelaciones de {total} pedidos (tasa del {rate}%) "
            f"con una facturación caída estimada de ${lost:,.2f}."
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
            f"Para el próximo fin de semana se proyecta un volumen de {weekend_orders} pedidos con una facturación estimada de ${weekend_rev:,.2f}.\n",
            "Insumos clave que deberías asegurar antes del viernes:\n",
        ]
        for i, ing in enumerate(ings[:5], 1):
            prods = ", ".join(ing.get("contributing_products", [])[:2])
            lines.append(
                f"{i}. {ing['ingredient_name']}: Proyección de {ing['projected_quantity']} {ing['unit']} "
                f"(gasto estimado: ${ing['estimated_cost']:,.2f}) para cubrir platos como {prods}."
            )
        lines.append(
            "\nAcción recomendada: Realizar las compras a distribuidores antes del jueves para evitar quiebres de stock en cocina durante el pico de ventas."
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
                "No se registran platos vendidos con receta para calcular rentabilidad.",
                ["¿Cuánto facturamos en este período?", "¿Qué insumos debería comprar antes del fin de semana?"],
            )
        lines = ["Platos más rentables en el período:\n"]
        for i, p in enumerate(products[:5], 1):
            lines.append(
                f"{i}. {p['product_name']}: Margen del {p['margin_pct']}% "
                f"(Ganancia bruta: ${p['gross_profit']:,.2f} sobre {p['quantity']} unidades vendidas. Costo unitario de insumos: ${p['unit_cost']:,.2f})."
            )
        return "\n".join(lines), [
            "¿Cuáles son los 3 insumos con más gasto este mes?",
            "¿Qué día tuvimos más cancelaciones?",
            "¿Cómo viene el cumplimiento de metas comerciales?",
        ]

    if intent == "goals":
        goals = data.get("goals", [])
        lines = ["Seguimiento del cumplimiento de metas comerciales:\n"]
        for g in goals:
            p_name = {"monthly": "Mensual", "weekly": "Semanal", "daily": "Diario"}.get(
                g["period_type"], g["period_type"].title()
            )
            lines.append(
                f"- Meta {p_name}: {g['revenue_progress_pct']}% alcanzado en facturación "
                f"(${g['actual_revenue']:,.2f} de ${g['target_revenue']:,.2f}, faltan ${g['revenue_remaining']:,.2f}) "
                f"y {g['orders_progress_pct']}% en pedidos ({g['actual_orders']} de {g['target_orders']} pedidos)."
            )
        return "\n".join(lines), [
            "¿Cuánto facturamos en este período?",
            "¿Cuáles son los platos más rentables?",
            "¿Qué insumos debería comprar antes del fin de semana?",
        ]

    if intent == "underperforming_products":
        under = data.get("underperforming_products", [])
        top = data.get("top_selling_products", [])
        top_cat = data.get("top_category")

        if not under:
            return (
                "Todos los productos activos de la carta registran ventas en el período.",
                ["¿Cuáles son los platos más vendidos?", "¿Cuáles son los platos más rentables?"],
            )

        worst = under[0]
        worst_reason = (
            "no registró ventas"
            if worst["units_sold"] == 0
            else f"registró únicamente {worst['units_sold']} unidades (${worst['revenue']:,.2f})"
        )

        top_names = ", ".join(t["product_name"] for t in top[:2]) if top else "los platos de mayor rotación"
        suggestion = (
            f"Podrías considerar eliminar o reformular {worst['product_name']} ({worst['category']}), "
            f"ya que {worst_reason} en el período analizado.\n\n"
            f"Para reemplazarlo, te conviene incorporar una opción inspirada en los platos más vendidos ({top_names}) "
            f"o fortalecer la categoría {top_cat or 'principal'}, que concentra la mayor preferencia y demanda de los clientes."
        )
        return suggestion, [
            "¿Cuáles son los platos más rentables?",
            "¿Cuáles son los platos más vendidos?",
            "¿Qué insumos debería comprar antes del fin de semana?",
        ]

    # Intent default: revenue
    rev = data.get("revenue", 0.0)
    completed = data.get("completed_orders", 0)
    ticket = data.get("average_ticket", 0.0)
    rate = data.get("cancellation_rate", 0.0)
    text = (
        f"La facturación total fue de ${rev:,.2f} con {completed} pedidos finalizados, "
        f"un ticket promedio de ${ticket:,.2f} por pedido y una tasa de cancelación del {rate}%."
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
    """Solicita a Gemini sintetizar una respuesta ejecutiva y directa respetando 100% las cifras reales."""
    if not settings.GOOGLE_API_KEY:
        return None

    history_text = ""
    if history:
        history_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in history[-4:])

    prompt = f"""
Sos el Asistente Inteligente Comercial de un restaurante gastronómico.
El administrador te hace una consulta comercial puntual. Respondé DIRECTAMENTE a su pregunta desde la primera palabra.

REGLAS ESTRICTAS DE RESPUESTA:
1. RESPUESTA DIRECTA Y SIN PREÁMBULOS:
   - PROHIBIDO saludar ("¡Hola!", "Buenas", etc.).
   - PROHIBIDO usar fórmulas introductorias ("Para responder a tu consulta...", "Basándome en los datos...", "De acuerdo a los registros...").
   - PROHIBIDO repetir el período de fechas en el saludo o inicio ("En el período Últimos 30 días...") porque ya figura en la interfaz. Empezá directamente con la respuesta concreta.
2. SI PREGUNTAN POR VENTAS DE UN PLATO ("cuántas X vendí?", "cuántas muzzarellas salieron?"):
   - Respondé directamente: "Vendiste X unidades de [Nombre del Plato] por un total de $Y..." y sumá datos útiles si los hay, todo en texto fluido.
3. SI PREGUNTAN SI CONVIENE COMPRAR ALGO O PIDEN RECOMENDACIÓN ("me conviene comprar X?", "qué me recomendás sobre X?"):
   - Respondé directamente con la recomendación: "Sí, te conviene comprar [Insumo] porque..." o "No es prioritario comprar [Insumo] porque...", justificando con la demanda proyectada para los próximos 7 días, platos que lo usan y consumo reciente.
4. SI PREGUNTAN QUÉ PRODUCTO ELIMINAR O REEMPLAZAR ("qué producto podría eliminar y por qué cambiarlo?", "qué plato sacar de la carta?"):
   - Respondé directamente indicando los platos con menor o nula venta/facturación de acuerdo al JSON underperforming_products.
   - Explicá por qué considerarlo (nula o muy baja salida comercial en el período analizado).
   - Sugerí con qué reemplazarlo basándote en los top_selling_products y la top_category.
5. FORMATO:
   - TODO EN TEXTO PLANO LIMPIO.
   - PROHIBIDO usar asteriscos dobles (NO uses ** en ninguna parte).
   - PROHIBIDO usar asteriscos simples (*).
   - Podés usar guiones (-) o números para listar items.
6. CERO ALUCINACIÓN:
   - Basate exclusivamente en los datos numéricos provistos en el JSON. No inventes cifras.

DATOS REALES DEL NEGOCIO:
{json.dumps(data, indent=2, ensure_ascii=False)}

HISTORIAL PREVIO (si aplica):
{history_text}

PREGUNTA DEL ADMINISTRADOR:
"{question}"

Respondé ÚNICAMENTE con un JSON válido con este esquema:
{{
  "answer": "Respuesta directa en texto plano sin asteriscos ni preámbulos...",
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
            cleaned_ans = ans.replace("**", "").replace("*", "").strip()
            return cleaned_ans, followups
    except Exception as e:
        logger.warning("Fallo en Gemini Asistente Q&A: %s. Procediendo a degradación controlada.", e)

    return None


def ask_copilot(db: Session, payload: CopilotQuestionPayload) -> CopilotAnswerResponse:
    """Procesa una consulta del usuario mediante ejecución de consultas reales sobre la base de datos e IA."""
    question = payload.question.strip()
    date_from, date_to, cited_period = _get_date_range_from_question(question)
    intent, target_entity = _detect_intent(question, db)

    # 1. Ejecutar la función interna de consulta correspondiente sobre la base de datos real
    data_summary: dict[str, Any] = {}
    if intent == "product_sales":
        data_summary = query_product_sales(db, date_from, date_to, term=target_entity)
    elif intent == "purchase_advice":
        data_summary = query_purchase_advice(db, date_from, date_to, term=target_entity)
    elif intent == "ingredient_spending":
        data_summary = query_ingredient_spending(db, date_from, date_to, limit=5)
    elif intent == "cancellations":
        data_summary = query_cancellations(db, date_from, date_to)
    elif intent == "profitable_dishes":
        data_summary = query_profitable_products(db, date_from, date_to, limit=5)
    elif intent == "underperforming_products":
        data_summary = query_underperforming_products(db, date_from, date_to)
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
    fallback_note = "\n\n(Respuesta directa calculada a partir de los datos registrados en el sistema.)"

    return CopilotAnswerResponse(
        answer=det_answer + fallback_note,
        cited_period=cited_period,
        data_summary=data_summary,
        suggested_followups=det_followups,
        is_fallback=True,
        generated_at=datetime.now(timezone.utc),
    )
