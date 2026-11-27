"""Servicio de Asistente Comercial Q&A asistido por consultas directas a la base de datos real e IA."""

import collections
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from google import genai
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.time import RESTAURANT_TZ, ahora_local
from app.db.session import transaction
from app.models.menu import Category, Ingredient, Product, ProductIngredient
from app.models.order import Order, OrderStatus
from app.models.promotion import Promotion
from app.repositories import (
    analytics_repository,
    coupon_repository,
    ingredient_repository,
    order_repository,
    promotion_repository,
)
from app.schemas.coupon_schemas import CouponCreate
from app.schemas.predictive_schemas import (
    ConversationMessage,
    CopilotActionExecutionPayload,
    CopilotActionExecutionResponse,
    CopilotAnswerResponse,
    CopilotQuestionPayload,
    CopilotSuggestedAction,
)
from app.services import analytics_service, coupon_service, predictive_service, promotion_service
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


def query_promotions_advice(db: Session) -> dict[str, Any]:
    """Genera recomendación de promoción comercial para impulsar ventas basada en rotación y margen."""
    active_products = (
        db.query(Product)
        .filter(Product.is_active.is_(True), Product.is_archived.is_(False))
        .all()
    )
    if len(active_products) < 2:
        return {"can_create_promo": False, "reason": "Se requieren al menos 2 productos activos en la carta."}

    now = ahora_local()
    date_from = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    utc_from = date_from.astimezone(timezone.utc)
    utc_to = now.astimezone(timezone.utc)
    best_sellers = order_repository.best_selling_products(db, utc_from, utc_to, limit=20)
    best_seller_names = [name for name, _, _ in best_sellers]

    selected: list[Product] = []
    for name in best_seller_names:
        for p in active_products:
            if p.name == name and p not in selected:
                selected.append(p)
                break
        if len(selected) == 2:
            break

    if len(selected) < 2:
        for p in active_products:
            if p not in selected:
                selected.append(p)
            if len(selected) == 2:
                break

    p1, p2 = selected[0], selected[1]
    orig_price = float(p1.price) + float(p2.price)
    discount_pct = 15
    promo_price = round(orig_price * (1 - discount_pct / 100.0), 2)
    promo_name = f"Promo {p1.name} + {p2.name}"

    return {
        "can_create_promo": True,
        "product_1": {"id": p1.id, "name": p1.name, "price": float(p1.price)},
        "product_2": {"id": p2.id, "name": p2.name, "price": float(p2.price)},
        "original_price": orig_price,
        "discount_pct": discount_pct,
        "promo_price": promo_price,
        "recommended_promo": {
            "title": f"Crear {promo_name}",
            "description": f"Combo con 15% de descuento (${promo_price:,.2f} en vez de ${orig_price:,.2f}) uniendo {p1.name} y {p2.name} para dinamizar las ventas.",
            "payload": {
                "name": promo_name,
                "description": f"Combo promocional con 15% de descuento: {p1.name} y {p2.name}.",
                "price": promo_price,
                "is_active": True,
                "items": [
                    {"product_id": p1.id, "quantity": 1},
                    {"product_id": p2.id, "quantity": 1},
                ],
            },
        },
    }


def query_activate_product(db: Session, term: str | None = None) -> dict[str, Any]:
    """Consulta productos pausados de la carta que el administrador podría reactivar."""
    inactive_products = (
        db.query(Product)
        .filter(Product.is_active.is_(False), Product.is_archived.is_(False))
        .all()
    )
    if not inactive_products:
        return {"has_inactive": False, "target_product": None, "inactive_products": []}

    target = None
    if term:
        norm_t = _normalize_token(term)
        for p in inactive_products:
            if norm_t in _normalize_token(p.name):
                target = p
                break

    if target is None:
        target = inactive_products[0]

    return {
        "has_inactive": True,
        "target_product": {"id": target.id, "name": target.name, "price": float(target.price or 0.0)},
        "inactive_products": [{"id": p.id, "name": p.name} for p in inactive_products],
    }


def _extract_percentage(question: str, default: int = 10) -> int:
    m = re.search(r"(\d+)\s*%", question)
    if m:
        return max(1, min(100, int(m.group(1))))
    m = re.search(r"\b(5|10|15|20|25|30|35|40|50)\b", question)
    if m:
        return int(m.group(1))
    return default


def _extract_amount(question: str) -> float | None:
    m = re.search(r"\$\s*(\d+(?:[.,]\d+)?)", question)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        return float(val)
    m = re.search(r"\ba\s+(\d{3,7})\b", question)
    if m:
        return float(m.group(1))
    return None


def _find_mentioned_category(db: Session, question: str) -> Category | None:
    categories = db.query(Category).all()
    norm_q = _normalize_token(question)
    for cat in categories:
        norm_c = _normalize_token(cat.name)
        if norm_c in norm_q or norm_c.rstrip("s") in norm_q or (len(norm_c) >= 4 and norm_c[:4] in norm_q):
            return cat
    return categories[0] if categories else None


def query_product_price_adjustment(db: Session, question: str, term: str | None = None) -> dict[str, Any]:
    """Prepara sugerencia de ajuste de precio para un plato puntual."""
    prod = None
    if term:
        norm_t = _normalize_token(term)
        prods = db.query(Product).filter(Product.is_archived.is_(False)).all()
        for p in prods:
            if norm_t in _normalize_token(p.name):
                prod = p
                break
    if not prod:
        prod = db.query(Product).filter(Product.is_active.is_(True), Product.is_archived.is_(False)).first()
    if not prod:
        return {"found": False}

    cur_price = float(prod.price)
    extracted_amt = _extract_amount(question)
    pct = _extract_percentage(question, default=10)
    if extracted_amt and extracted_amt > 100:
        new_price = extracted_amt
    elif "bajar" in question.lower() or "reducir" in question.lower() or "descuento" in question.lower():
        new_price = round(cur_price * (1 - pct / 100.0), 2)
    else:
        new_price = round(cur_price * (1 + pct / 100.0), 2)

    return {
        "found": True,
        "product_id": prod.id,
        "product_name": prod.name,
        "current_price": cur_price,
        "new_price": new_price,
        "percentage": pct,
    }


def query_category_price_adjustment(db: Session, question: str) -> dict[str, Any]:
    """Prepara sugerencia de ajuste porcentual masivo para una categoría de productos."""
    cat = _find_mentioned_category(db, question)
    if not cat:
        return {"found": False}

    prods = db.query(Product).filter(
        Product.category_id == cat.id,
        Product.is_active.is_(True),
        Product.is_archived.is_(False),
    ).all()
    pct = _extract_percentage(question, default=10)

    return {
        "found": True,
        "category_id": cat.id,
        "category_name": cat.name,
        "product_count": len(prods),
        "percentage": pct,
        "preview_products": [
            {
                "id": p.id,
                "name": p.name,
                "old_price": float(p.price),
                "new_price": round(float(p.price) * (1 + pct / 100.0), 2),
            }
            for p in prods[:5]
        ],
    }


def query_toggle_promotion(db: Session, question: str) -> dict[str, Any]:
    """Prepara sugerencia para pausar o reactivar una promoción de la carta."""
    is_pause = any(w in question.lower() for w in ["pausar", "desactivar", "ocultar", "sacar", "bajar"])
    promos = db.query(Promotion).all()
    if not promos:
        return {"found": False}

    norm_q = _normalize_token(question)
    target = None
    for p in promos:
        norm_p = _normalize_token(p.name)
        if norm_p in norm_q or any((len(w) >= 5 and w in norm_q) for w in norm_p.split()):
            target = p
            break
    if not target:
        for p in promos:
            if (is_pause and p.is_active) or (not is_pause and not p.is_active):
                target = p
                break
    if not target:
        target = promos[0]

    target_is_active = not is_pause
    return {
        "found": True,
        "promotion_id": target.id,
        "promotion_name": target.name,
        "current_is_active": target.is_active,
        "target_is_active": target_is_active,
        "action_label": "Pausar" if not target_is_active else "Reactivar",
    }


def query_shopping_list(db: Session) -> dict[str, Any]:
    """Genera lista de compras consolidada para los próximos 7 días a partir de proyecciones."""
    predictions = predictive_service.calculate_predictions(db, historical_weeks=26)
    demands = predictions.ingredient_demands
    items = [
        {
            "name": d.ingredient_name,
            "quantity": d.projected_quantity,
            "unit": d.unit,
            "cost": d.estimated_cost,
        }
        for d in demands
    ]
    total_cost = sum(it["cost"] for it in items)
    return {
        "items": items,
        "count": len(items),
        "total_estimated_cost": round(total_cost, 2),
    }


def query_compensate_customers(db: Session) -> dict[str, Any]:
    """Prepara sugerencia de cupón de descuento para resarcir cancelaciones o demoras."""
    return {
        "code": "DISCULPAS-15",
        "discount_percentage": 15,
        "reason": "Compensación para clientes con pedidos cancelados o incidencias de demora.",
    }


def query_targeted_promotion(db: Session, question: str) -> dict[str, Any]:
    """Prepara sugerencia de combo o promoción dirigida a días lentos o franjas horarias."""
    active_prods = db.query(Product).filter(
        Product.is_active.is_(True),
        Product.is_archived.is_(False),
    ).all()
    if len(active_prods) < 2:
        return {"can_create": False}

    p1, p2 = active_prods[0], active_prods[1]
    orig_price = float(p1.price) + float(p2.price)
    discount_pct = 20
    promo_price = round(orig_price * (1 - discount_pct / 100.0), 2)
    name = f"Promo Días Lentos ({p1.name} + {p2.name})"

    return {
        "can_create": True,
        "name": name,
        "product_1": p1.name,
        "product_2": p2.name,
        "orig_price": orig_price,
        "promo_price": promo_price,
        "discount_pct": discount_pct,
        "items": [
            {"product_id": p1.id, "quantity": 1},
            {"product_id": p2.id, "quantity": 1},
        ],
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

    if any(k in q or k in norm_q for k in ["lista de compras", "orden de compra", "generar lista de compras", "armar lista de compras", "compras de insumos"]):
        return "shopping_list", None

    if any(k in q or k in norm_q for k in ["compensar", "resarcir", "cupon de disculpas", "cupón de disculpas", "descuento por cancelacion", "descuento por cancelación", "compensacion", "compensación"]):
        return "compensate_customers", None

    if any(k in q or k in norm_q for k in ["promocion dirigida", "promoción dirigida", "promo dirigida", "dias lentos", "días lentos", "para martes", "para dias lentos"]):
        return "targeted_promotion", None

    if any(k in q or k in norm_q for k in ["pausar promo", "pausar promocion", "pausar promoción", "desactivar promo", "desactivar promocion", "reactivar promo", "reactivar promocion", "reactivar promoción"]):
        return "toggle_promotion", None

    cat_price_triggers = [
        "aumentar categoria",
        "aumentar categoría",
        "subir precios de la categoria",
        "subir precios de la categoría",
        "ajustar precios de",
        "precios por categoria",
        "precios por categoría",
        "aumentar a la categoria",
        "aumentar a la categoría",
    ]
    if any(t in q or t in norm_q for t in cat_price_triggers) or (
        any(w in q for w in ["aumentar", "subir", "ajustar"])
        and any(c in q for c in ["pizza", "empanada", "bebida", "postre", "categoria", "categoría"])
        and ("%" in q or any(num in q for num in ["10", "15", "20", "25", "30"]))
    ):
        return "category_price_adjustment", None

    prod_price_triggers = [
        "precio de",
        "subir precio de",
        "aumentar precio de",
        "bajar precio de",
        "cambiar precio de",
        "ajustar precio de",
    ]
    if any(t in q or t in norm_q for t in prod_price_triggers) and prod_matches:
        return "product_price_adjustment", prod_matches[0]

    promo_triggers = [
        "promocion",
        "promoción",
        "promo",
        "combo",
        "descuento",
        "aumentar ventas",
        "aumentar las ventas",
        "subir ventas",
        "subir las ventas",
        "impulsar ventas",
        "crear oferta",
        "oferta",
    ]
    if any(t in q or t in norm_q for t in promo_triggers):
        return "promotions_advice", None

    activation_triggers = [
        "activar",
        "reactivar",
        "habilitar plato",
        "habilitar producto",
        "volver a poner",
        "volver a la carta",
        "poner en la carta",
    ]
    if any(t in q or t in norm_q for t in activation_triggers):
        target = prod_matches[0] if prod_matches else None
        return "activate_product", target

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

    if intent == "promotions_advice":
        promo_data = data.get("recommended_promo")
        if not promo_data or not data.get("can_create_promo"):
            return (
                "Para armar una promoción necesitás contar con al menos dos productos activos en la carta.",
                ["¿Cuáles son los platos más vendidos?", "¿Cuáles son los platos más rentables?"],
            )
        p1 = data["product_1"]
        p2 = data["product_2"]
        orig = data["original_price"]
        promo_p = data["promo_price"]
        desc = data["discount_pct"]
        text = (
            f"Te recomiendo lanzar una promoción combinando {p1['name']} y {p2['name']}. "
            f"El precio regular conjunto es de ${orig:,.2f}, y con un {desc}% de descuento promocional "
            f"quedaría en ${promo_p:,.2f} para impulsar el volumen de pedidos."
        )
        return text, [
            "¿Cuáles son los platos más vendidos?",
            "¿Cuáles son los platos más rentables?",
            "¿Cómo viene el cumplimiento de metas?",
        ]

    if intent == "activate_product":
        if not data.get("has_inactive"):
            return (
                "Actualmente todos los productos del menú se encuentran activos en la carta.",
                ["¿Qué producto podría eliminar y por qué cambiarlo?", "¿Cuáles son los platos más vendidos?"],
            )
        target = data["target_product"]
        text = (
            f"El producto {target['name']} se encuentra actualmente pausado fuera de la carta. "
            f"Podés reactivarlo para que los clientes vuelvan a encontrarlo en el menú digital."
        )
        return text, [
            "¿Cuáles son los platos más vendidos?",
            "¿Qué producto podría eliminar y por qué cambiarlo?",
        ]

    if intent == "product_price_adjustment":
        if not data.get("found"):
            return (
                "No encontré el producto solicitado para modificar su precio.",
                ["¿Cuáles son los platos más vendidos?", "¿Cuáles son los platos más rentables?"],
            )
        name = data["product_name"]
        cur = data["current_price"]
        new_p = data["new_price"]
        diff = new_p - cur
        text = (
            f"El plato {name} tiene un precio actual de ${cur:,.2f}. "
            f"El precio ajustado sugerido es de ${new_p:,.2f} ({'+' if diff >= 0 else ''}${diff:,.2f})."
        )
        return text, [
            f"¿Cuánto vendimos de {name} este mes?",
            "¿Cuáles son los platos más rentables?",
        ]

    if intent == "category_price_adjustment":
        if not data.get("found") or not data.get("product_count"):
            return (
                "No encontré productos activos en la categoría seleccionada.",
                ["¿Cuáles son las categorías con más ventas?", "¿Cuáles son los platos más vendidos?"],
            )
        cat = data["category_name"]
        pct = data["percentage"]
        count = data["product_count"]
        text = (
            f"La categoría {cat} cuenta con {count} productos activos. "
            f"Un aumento general del {pct}% actualizará los precios para absorber la inflación de insumos "
            f"y preservar el margen de ganancia."
        )
        return text, [
            "¿Cuáles son los 3 insumos con más gasto este mes?",
            "¿Cómo viene el cumplimiento de metas?",
        ]

    if intent == "toggle_promotion":
        if not data.get("found"):
            return (
                "No hay promociones registradas en el sistema para modificar.",
                ["¿Qué promoción me recomendás crear?", "¿Cuáles son los platos más vendidos?"],
            )
        name = data["promotion_name"]
        act = data["action_label"]
        text = (
            f"Podés {act.lower()} la promoción '{name}' para actualizar la oferta disponible "
            f"en el menú digital según la rotación de ventas."
        )
        return text, [
            "¿Qué promoción me recomendás crear?",
            "¿Cuáles son los platos más rentables?",
        ]

    if intent == "shopping_list":
        cnt = data.get("count", 0)
        tot = data.get("total_estimated_cost", 0.0)
        text = (
            f"Se calcularon {cnt} insumos críticos requeridos para la demanda de los próximos 7 días, "
            f"con un gasto total estimado de ${tot:,.2f}. Podés generar la orden de compras detallada "
            f"para abastecer la cocina a tiempo."
        )
        return text, [
            "¿Qué insumos debería comprar antes del fin de semana?",
            "¿Cuáles son los 3 insumos con más gasto este mes?",
        ]

    if intent == "compensate_customers":
        code = data.get("code", "DISCULPAS-15")
        pct = data.get("discount_percentage", 15)
        text = (
            f"Para resarcir a clientes que experimentaron pedidos cancelados o demoras imprevistas, "
            f"te sugiero habilitar el cupón web '{code}' con un {pct}% de descuento en su próxima compra."
        )
        return text, [
            "¿Qué día tuvimos más cancelaciones?",
            "¿Cuánto facturamos la última semana?",
        ]

    if intent == "targeted_promotion":
        if not data.get("can_create"):
            return (
                "Se requieren al menos 2 productos activos para estructurar una promoción dirigida.",
                ["¿Cuáles son los platos más vendidos?", "¿Qué promoción me recomendás crear?"],
            )
        name = data["name"]
        p1 = data["product_1"]
        p2 = data["product_2"]
        promo_p = data["promo_price"]
        pct = data["discount_pct"]
        text = (
            f"Para estimular las ventas durante los días de menor demanda (como martes o miércoles), "
            f"te recomiendo lanzar '{name}' con un {pct}% de descuento (${promo_p:,.2f}) combinando {p1} y {p2}."
        )
        return text, [
            "¿Cuáles son los platos más vendidos?",
            "¿Cómo viene el cumplimiento de metas?",
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
5. SI PREGUNTAN POR PROMOCIONES O CÓMO AUMENTAR VENTAS:
   - Respondé directamente recomendando la promoción sugerida en recommended_promo, con el precio promocional, productos incluidos y el porcentaje de ahorro.
6. SI PREGUNTAN POR ACTIVAR O REACTIVAR UN PLATO:
   - Respondé directamente indicando el plato pausado y la posibilidad de reactivarlo en el menú digital.
7. FORMATO:
   - TODO EN TEXTO PLANO LIMPIO.
   - PROHIBIDO usar asteriscos dobles (NO uses ** en ninguna parte).
   - PROHIBIDO usar asteriscos simples (*).
   - Podés usar guiones (-) o números para listar items.
8. CERO ALUCINACIÓN:
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
    elif intent == "promotions_advice":
        data_summary = query_promotions_advice(db)
    elif intent == "activate_product":
        data_summary = query_activate_product(db, term=target_entity)
    elif intent == "product_price_adjustment":
        data_summary = query_product_price_adjustment(db, question, term=target_entity)
    elif intent == "category_price_adjustment":
        data_summary = query_category_price_adjustment(db, question)
    elif intent == "toggle_promotion":
        data_summary = query_toggle_promotion(db, question)
    elif intent == "shopping_list":
        data_summary = query_shopping_list(db)
        cited_period = "Próximos 7 días"
    elif intent == "compensate_customers":
        data_summary = query_compensate_customers(db)
    elif intent == "targeted_promotion":
        data_summary = query_targeted_promotion(db, question)
    elif intent == "goals":
        data_summary = query_goals_progress(db)
    elif intent == "weekend_purchases":
        data_summary = query_weekend_purchases_forecast(db)
        cited_period = "Próximo fin de semana y demanda estimada a 7 días"
    else:  # revenue
        data_summary = query_revenue_and_orders(db, date_from, date_to)

    # Determinar acción sugerida opcional (Human-in-the-Loop)
    suggested_action: CopilotSuggestedAction | None = None
    if intent == "underperforming_products":
        under = data_summary.get("underperforming_products", [])
        if under and under[0].get("product_id"):
            worst = under[0]
            suggested_action = CopilotSuggestedAction(
                action_type="deactivate_product",
                title=f"Pausar {worst['product_name']} de la carta",
                description=f"Ocultar temporalmente '{worst['product_name']}' del menú digital para optimizar la oferta comercial.",
                button_label="Pausar de la carta",
                payload={
                    "product_id": worst["product_id"],
                    "product_name": worst["product_name"],
                },
            )
    elif intent == "promotions_advice":
        promo = data_summary.get("recommended_promo")
        if promo:
            suggested_action = CopilotSuggestedAction(
                action_type="create_promotion",
                title=promo["title"],
                description=promo["description"],
                button_label="Crear promoción",
                payload=promo["payload"],
            )
    elif intent == "activate_product":
        target = data_summary.get("target_product")
        if target:
            suggested_action = CopilotSuggestedAction(
                action_type="activate_product",
                title=f"Reactivar {target['name']} en la carta",
                description=f"Hacer visible nuevamente '{target['name']}' para que los clientes puedan pedirlo.",
                button_label="Reactivar en la carta",
                payload={
                    "product_id": target["id"],
                    "product_name": target["name"],
                },
            )
    elif intent == "product_price_adjustment":
        if data_summary.get("found"):
            p_name = data_summary["product_name"]
            new_pr = data_summary["new_price"]
            suggested_action = CopilotSuggestedAction(
                action_type="update_product_price",
                title=f"Ajustar precio de {p_name}",
                description=f"Modificar el precio de '{p_name}' a ${new_pr:,.2f}.",
                button_label="Actualizar precio",
                payload={
                    "product_id": data_summary["product_id"],
                    "product_name": p_name,
                    "new_price": new_pr,
                },
            )
    elif intent == "category_price_adjustment":
        if data_summary.get("found") and data_summary.get("product_count", 0) > 0:
            c_name = data_summary["category_name"]
            pct = data_summary["percentage"]
            suggested_action = CopilotSuggestedAction(
                action_type="update_category_prices",
                title=f"Aumentar {pct}% a categoría {c_name}",
                description=f"Actualizar precios de los {data_summary['product_count']} productos de '{c_name}' con un aumento del {pct}%.",
                button_label="Aplicar aumento",
                payload={
                    "category_id": data_summary["category_id"],
                    "category_name": c_name,
                    "percentage": pct,
                },
            )
    elif intent == "toggle_promotion":
        if data_summary.get("found"):
            p_name = data_summary["promotion_name"]
            act_lbl = data_summary["action_label"]
            suggested_action = CopilotSuggestedAction(
                action_type="toggle_promotion_status",
                title=f"{act_lbl} promoción '{p_name}'",
                description=f"{'Ocultar' if not data_summary['target_is_active'] else 'Habilitar nuevamente'} la promoción '{p_name}' en la carta digital.",
                button_label=f"{act_lbl} promoción",
                payload={
                    "promotion_id": data_summary["promotion_id"],
                    "promotion_name": p_name,
                    "target_is_active": data_summary["target_is_active"],
                },
            )
    elif intent == "shopping_list":
        if data_summary.get("count", 0) > 0:
            suggested_action = CopilotSuggestedAction(
                action_type="generate_shopping_list",
                title="Generar lista de compras",
                description=f"Armar orden de compra consolidada con los {data_summary['count']} insumos proyectados a 7 días (${data_summary['total_estimated_cost']:,.2f}).",
                button_label="Generar lista",
                payload={
                    "items": data_summary["items"],
                    "total_estimated_cost": data_summary["total_estimated_cost"],
                },
            )
    elif intent == "compensate_customers":
        c_code = data_summary.get("code", "DISCULPAS-15")
        c_pct = data_summary.get("discount_percentage", 15)
        suggested_action = CopilotSuggestedAction(
            action_type="compensate_customers_coupon",
            title=f"Crear cupón {c_code} ({c_pct}% OFF)",
            description=f"Generar el cupón web '{c_code}' con {c_pct}% de descuento para resarcir pedidos cancelados o demoras.",
            button_label="Crear cupón",
            payload={
                "code": c_code,
                "discount_percentage": c_pct,
            },
        )
    elif intent == "targeted_promotion":
        if data_summary.get("can_create"):
            suggested_action = CopilotSuggestedAction(
                action_type="create_targeted_promotion",
                title=f"Crear {data_summary['name']}",
                description=f"Combo dirigido con 20% de descuento (${data_summary['promo_price']:,.2f}) uniendo {data_summary['product_1']} y {data_summary['product_2']}.",
                button_label="Crear promo dirigida",
                payload={
                    "name": data_summary["name"],
                    "description": f"Promoción dirigida para dinamizar ventas: {data_summary['product_1']} + {data_summary['product_2']} con 20% OFF.",
                    "price": data_summary["promo_price"],
                    "is_active": True,
                    "items": data_summary["items"],
                },
            )

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
            suggested_action=suggested_action,
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
        suggested_action=suggested_action,
        is_fallback=True,
        generated_at=datetime.now(timezone.utc),
    )


def execute_copilot_action(
    db: Session,
    payload: CopilotActionExecutionPayload,
) -> CopilotActionExecutionResponse:
    """Ejecuta una acción comercial aprobada por el administrador generada por el Copilot (Human-in-the-Loop)."""
    action = payload.action_type
    p_data = payload.payload or {}

    if action == "deactivate_product":
        prod_id = p_data.get("product_id")
        if not prod_id:
            raise BusinessRuleError("Identificador de producto faltante para pausar.")
        prod = db.query(Product).filter(Product.id == prod_id).first()
        if not prod:
            raise NotFoundError(f"No se encontró el producto con id {prod_id}.")
        with transaction(db):
            prod.is_active = False
        return CopilotActionExecutionResponse(
            success=True,
            message=f"El producto '{prod.name}' fue pausado y ya no se muestra en la carta.",
            executed_action="deactivate_product",
            affected_entity_id=prod.id,
        )

    if action == "activate_product":
        prod_id = p_data.get("product_id")
        if not prod_id:
            raise BusinessRuleError("Identificador de producto faltante para reactivar.")
        prod = db.query(Product).filter(Product.id == prod_id).first()
        if not prod:
            raise NotFoundError(f"No se encontró el producto con id {prod_id}.")
        with transaction(db):
            prod.is_active = True
        return CopilotActionExecutionResponse(
            success=True,
            message=f"El producto '{prod.name}' fue reactivado y vuelve a estar visible en la carta.",
            executed_action="activate_product",
            affected_entity_id=prod.id,
        )

    if action == "create_promotion":
        name = p_data.get("name")
        desc = p_data.get("description")
        price = p_data.get("price")
        is_active = p_data.get("is_active", True)
        raw_items = p_data.get("items", [])

        if not name or price is None or not raw_items:
            raise BusinessRuleError("Parámetros incompletos para crear la promoción.")

        class _PromoItem:
            def __init__(self, product_id: int, quantity: int = 1):
                self.product_id = product_id
                self.quantity = quantity

        items = [_PromoItem(it["product_id"], it.get("quantity", 1)) for it in raw_items]

        final_name = name
        counter = 1
        while promotion_repository.name_taken(db, final_name):
            counter += 1
            final_name = f"{name} #{counter}"

        created_promo = promotion_service.create_promotion(
            db=db,
            name=final_name,
            description=desc,
            price=price,
            is_active=is_active,
            items=items,
        )
        return CopilotActionExecutionResponse(
            success=True,
            message=f"Promoción '{created_promo.name}' creada exitosamente por ${float(created_promo.price):,.2f}.",
            executed_action="create_promotion",
            affected_entity_id=created_promo.id,
        )

    if action == "update_business_goal":
        period_type = p_data.get("period_type")
        target_revenue = p_data.get("target_revenue")
        target_orders = p_data.get("target_orders")

        if not period_type or target_revenue is None or target_orders is None:
            raise BusinessRuleError("Parámetros incompletos para actualizar la meta comercial.")

        goal_data = analytics_service.BusinessGoalData(
            period_type=period_type,
            target_revenue=float(target_revenue),
            target_orders=int(target_orders),
        )
        analytics_service.update_business_goals(db, [goal_data])
        return CopilotActionExecutionResponse(
            success=True,
            message=f"Meta {period_type} actualizada a ${float(target_revenue):,.2f} y {int(target_orders)} pedidos.",
            executed_action="update_business_goal",
        )

    if action == "update_product_price":
        prod_id = p_data.get("product_id")
        new_price = p_data.get("new_price")
        if not prod_id or new_price is None:
            raise BusinessRuleError("Parámetros incompletos para actualizar el precio del producto.")
        prod = db.query(Product).filter(Product.id == prod_id).first()
        if not prod:
            raise NotFoundError(f"No se encontró el producto con id {prod_id}.")
        if prod.has_variants:
            raise BusinessRuleError(
                f"'{prod.name}' tiene un precio por variante ({prod.describe_variants()}): cambialo desde el catálogo."
            )
        with transaction(db):
            prod.price = round(float(new_price), 2)
        return CopilotActionExecutionResponse(
            success=True,
            message=f"Precio de '{prod.name}' actualizado correctamente a ${float(new_price):,.2f}.",
            executed_action="update_product_price",
            affected_entity_id=prod.id,
        )

    if action == "update_category_prices":
        cat_id = p_data.get("category_id")
        pct = p_data.get("percentage") if p_data.get("percentage") is not None else p_data.get("percentage_increase")
        if not cat_id or pct is None:
            raise BusinessRuleError("Parámetros incompletos para actualizar los precios por categoría.")
        cat = db.query(Category).filter(Category.id == cat_id).first()
        if not cat:
            raise NotFoundError(f"No se encontró la categoría con id {cat_id}.")
        prods = db.query(Product).filter(
            Product.category_id == cat_id,
            Product.is_active.is_(True),
            Product.is_archived.is_(False),
        ).all()
        with transaction(db):
            for p in prods:
                p.scale_prices(1 + Decimal(str(pct)) / 100)
        return CopilotActionExecutionResponse(
            success=True,
            message=f"Se aplicó un aumento del {pct}% a los {len(prods)} productos de la categoría '{cat.name}'.",
            executed_action="update_category_prices",
            affected_entity_id=cat.id,
        )

    if action == "toggle_promotion_status":
        promo_id = p_data.get("promotion_id")
        target_is_active = p_data.get("target_is_active") if p_data.get("target_is_active") is not None else (p_data.get("activate") if p_data.get("activate") is not None else p_data.get("is_active"))
        if not promo_id or target_is_active is None:
            raise BusinessRuleError("Parámetros incompletos para modificar el estado de la promoción.")
        promo = db.query(Promotion).filter(Promotion.id == promo_id).first()
        if not promo:
            raise NotFoundError(f"No se encontró la promoción con id {promo_id}.")
        with transaction(db):
            promo.is_active = bool(target_is_active)
        status_txt = "reactivada y visible en la carta" if target_is_active else "pausada correctamente"
        return CopilotActionExecutionResponse(
            success=True,
            message=f"Promoción '{promo.name}' {status_txt}.",
            executed_action="toggle_promotion_status",
            affected_entity_id=promo.id,
        )

    if action == "generate_shopping_list":
        items = p_data.get("items", [])
        tot = p_data.get("total_estimated_cost", 0.0)
        lines = ["🛒 ORDEN DE COMPRA SUGERIDA (PRÓXIMOS 7 DÍAS):"]
        for it in items:
            lines.append(f"• {it['name']}: {it['quantity']} {it['unit']} (~${float(it['cost']):,.2f})")
        lines.append(f"\nTotal estimado: ${float(tot):,.2f}")
        return CopilotActionExecutionResponse(
            success=True,
            message="\n".join(lines),
            executed_action="generate_shopping_list",
        )

    if action == "compensate_customers_coupon":
        code = (p_data.get("code") or p_data.get("coupon_code") or "DISCULPAS-15").strip().upper()
        discount_pct = int(p_data.get("discount_percentage", 15))
        existing = coupon_repository.get_by_code(db, code)
        if existing:
            with transaction(db):
                existing.is_active = True
                existing.discount_percentage = discount_pct
            c_id = existing.id
        else:
            created_coupon = coupon_service.create_coupon(
                db, CouponCreate(code=code, discount_percentage=discount_pct, is_active=True)
            )
            c_id = created_coupon.id
        return CopilotActionExecutionResponse(
            success=True,
            message=f"Cupón web '{code}' creado con {discount_pct}% de descuento para compensar clientes.",
            executed_action="compensate_customers_coupon",
            affected_entity_id=c_id,
        )

    if action == "create_targeted_promotion":
        name = p_data.get("name") or "Promoción Especial Dirigida"
        desc = p_data.get("description")
        price = p_data.get("price") if p_data.get("price") is not None else p_data.get("promo_price")
        is_active = p_data.get("is_active", True)
        raw_items = p_data.get("items", [])
        if not raw_items:
            active_prods = db.query(Product).filter(
                Product.is_active.is_(True),
                Product.is_archived.is_(False),
            ).limit(2).all()
            if active_prods:
                raw_items = [{"product_id": p.id, "quantity": 1} for p in active_prods]
                if price is None:
                    discount_pct = float(p_data.get("discount_percent") or p_data.get("discount_pct") or 20)
                    sum_price = sum(float(p.price) for p in active_prods)
                    price = round(sum_price * (1 - discount_pct / 100.0), 2)
        if not name or price is None or not raw_items:
            raise BusinessRuleError("Parámetros incompletos para crear la promoción dirigida.")

        class _PromoItem:
            def __init__(self, product_id: int, quantity: int = 1):
                self.product_id = product_id
                self.quantity = quantity

        items = [_PromoItem(it["product_id"], it.get("quantity", 1)) for it in raw_items]
        final_name = name
        counter = 1
        while promotion_repository.name_taken(db, final_name):
            counter += 1
            final_name = f"{name} #{counter}"

        created_promo = promotion_service.create_promotion(
            db=db,
            name=final_name,
            description=desc,
            price=price,
            is_active=is_active,
            items=items,
        )
        return CopilotActionExecutionResponse(
            success=True,
            message=f"Promoción dirigida '{created_promo.name}' creada exitosamente por ${float(created_promo.price):,.2f}.",
            executed_action="create_targeted_promotion",
            affected_entity_id=created_promo.id,
        )

    raise BusinessRuleError(f"Tipo de acción '{action}' no soportado.")

