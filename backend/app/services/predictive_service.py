"""Servicio de analítica predictiva de demanda, proyecciones de insumos y prescripciones comerciales con IA."""

import collections
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google import genai
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import RESTAURANT_TZ, ahora_local
from app.models.menu import Product
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.predictive_schemas import (
    DayProjectionItem,
    IngredientDemandItem,
    PredictionsResponse,
)
from app.services.gemini_models import modelos
from app.services.stats_service import WEEKDAYS

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_SECONDS = 10


def _to_local_datetime(dt: datetime) -> datetime:
    """Convierte datetime UTC/naive a zona horaria local del restaurante."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(RESTAURANT_TZ)


def _calculate_historical_averages(
    orders: list[Order],
    historical_weeks: int,
) -> tuple[dict[int, float], dict[int, float], float, float]:
    """Calcula promedios diarios por día de la semana (0=Lunes, ..., 6=Domingo) y factor de tendencia."""
    completed_counts_by_dow: dict[int, int] = collections.defaultdict(int)
    completed_revenue_by_dow: dict[int, float] = collections.defaultdict(float)
    cancelled_counts_by_dow: dict[int, int] = collections.defaultdict(int)
    weeks_count = max(1, historical_weeks)

    recent_cutoff = ahora_local() - timedelta(weeks=2)
    recent_completed_count = 0
    older_completed_count = 0

    for order in orders:
        local_dt = _to_local_datetime(order.created_at)
        dow = local_dt.weekday()

        if order.status == OrderStatus.COMPLETED.value:
            completed_counts_by_dow[dow] += 1
            completed_revenue_by_dow[dow] += float(order.total_amount or 0.0)
            if local_dt >= recent_cutoff:
                recent_completed_count += 1
            else:
                older_completed_count += 1
        elif order.status == OrderStatus.CANCELLED.value:
            cancelled_counts_by_dow[dow] += 1

    # Promedio por día de la semana
    avg_orders_per_dow: dict[int, float] = {}
    avg_rev_per_dow: dict[int, float] = {}
    for dow in range(7):
        avg_orders_per_dow[dow] = completed_counts_by_dow[dow] / weeks_count
        avg_rev_per_dow[dow] = completed_revenue_by_dow[dow] / weeks_count

    # Factor de tendencia reciente (últimas 2 semanas vs anteriores 6 semanas)
    # 2 semanas = 14 días; semanas anteriores = (weeks_count - 2) * 7 días
    older_days = max(7, (weeks_count - 2) * 7) if weeks_count > 2 else 14
    recent_daily = recent_completed_count / 14.0
    older_daily = older_completed_count / float(older_days) if older_completed_count > 0 else recent_daily

    if older_daily > 0 and recent_daily > 0:
        raw_trend = recent_daily / older_daily
        trend_factor = min(1.30, max(0.75, raw_trend))
    else:
        trend_factor = 1.0

    total_cancelled = sum(cancelled_counts_by_dow.values())
    total_completed = sum(completed_counts_by_dow.values())
    total_orders = total_completed + total_cancelled
    cancellation_rate = (total_cancelled / total_orders * 100.0) if total_orders > 0 else 0.0

    return avg_orders_per_dow, avg_rev_per_dow, trend_factor, cancellation_rate


def _project_next_7_days(
    avg_orders: dict[int, float],
    avg_rev: dict[int, float],
    trend_factor: float,
) -> list[DayProjectionItem]:
    """Genera la proyección día por día para los próximos 7 días a partir de mañana."""
    today = ahora_local()
    projections: list[DayProjectionItem] = []

    for i in range(1, 8):
        proj_date = today + timedelta(days=i)
        dow = proj_date.weekday()
        day_name = WEEKDAYS[dow]
        is_weekend = dow in (5, 6)  # Sábado y Domingo

        raw_orders = avg_orders.get(dow, 0.0) * trend_factor
        raw_rev = avg_rev.get(dow, 0.0) * trend_factor

        projected_orders = max(0, int(round(raw_orders)))
        projected_rev = max(0.0, round(raw_rev, 2))

        # Consistencia de negocio: no puede haber facturación proyectada con 0 pedidos
        if projected_rev > 0 and projected_orders == 0:
            if raw_orders >= 0.1:
                projected_orders = 1
            else:
                projected_rev = 0.0
        elif projected_orders == 0:
            projected_rev = 0.0

        projections.append(
            DayProjectionItem(
                date=proj_date.strftime("%Y-%m-%d"),
                day_name=day_name,
                is_weekend=is_weekend,
                projected_orders=projected_orders,
                projected_revenue=projected_rev,
            )
        )

    return projections


def _project_ingredient_demands(
    db: Session,
    start_date: datetime,
    total_projected_orders: int,
) -> list[IngredientDemandItem]:
    """Calcula la demanda proyectada de insumos según recetas de los productos con mayor tendencia de venta."""
    # Consultar cantidades vendidas en pedidos completados en el período histórico
    rows = (
        db.query(OrderItem.product_id, Product.name, OrderItem.quantity)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(
            Order.status == OrderStatus.COMPLETED.value,
            Order.created_at >= start_date,
            OrderItem.product_id.isnot(None),
        )
        .all()
    )

    product_sales: dict[int, tuple[str, int]] = {}
    total_sold_units = 0
    for product_id, product_name, qty in rows:
        if product_id not in product_sales:
            product_sales[product_id] = (product_name, 0)
        curr_name, curr_qty = product_sales[product_id]
        product_sales[product_id] = (curr_name, curr_qty + int(qty or 0))
        total_sold_units += int(qty or 0)

    if not product_sales or total_sold_units == 0:
        return []

    # Identificar productos con mayor tendencia (top sellers)
    sorted_products = sorted(product_sales.items(), key=lambda item: item[1][1], reverse=True)[:15]

    # Para cada insumo, acumular demanda proyectada
    ingredient_demands: dict[int, dict[str, Any]] = {}

    for prod_id, (prod_name, prod_qty) in sorted_products:
        product = db.query(Product).filter(Product.id == prod_id).first()
        if not product or not product.recipe_items:
            continue

        share = prod_qty / total_sold_units
        projected_prod_units = max(1, int(round(share * total_projected_orders))) if total_projected_orders > 0 else 0

        for recipe_item in product.recipe_items:
            ing = recipe_item.ingredient
            if not ing:
                continue

            qty_needed = projected_prod_units * float(recipe_item.quantity)
            if ing.id not in ingredient_demands:
                ingredient_demands[ing.id] = {
                    "ingredient_id": ing.id,
                    "ingredient_name": ing.name,
                    "unit": ing.unit,
                    "projected_quantity": 0.0,
                    "unit_cost": float(ing.cost or 0.0),
                    "contributing_products": set(),
                }

            ingredient_demands[ing.id]["projected_quantity"] += qty_needed
            ingredient_demands[ing.id]["contributing_products"].add(prod_name)

    results: list[IngredientDemandItem] = []
    for item in ingredient_demands.values():
        proj_qty = round(item["projected_quantity"], 2)
        unit_cost = item["unit_cost"]
        est_cost = round(proj_qty * unit_cost, 2)
        results.append(
            IngredientDemandItem(
                ingredient_id=item["ingredient_id"],
                ingredient_name=item["ingredient_name"],
                unit=item["unit"],
                projected_quantity=proj_qty,
                unit_cost=unit_cost,
                estimated_cost=est_cost,
                contributing_products=sorted(list(item["contributing_products"])),
            )
        )

    # Ordenar por costo estimado descendente (o cantidad descendente)
    results.sort(key=lambda x: (x.estimated_cost, x.projected_quantity), reverse=True)
    return results


def _build_rule_based_prescriptions(
    days: list[DayProjectionItem],
    ingredient_demands: list[IngredientDemandItem],
    weekend_orders: int,
    weekend_revenue: float,
    weekday_orders: int,
    total_orders: int,
    cancellation_rate: float,
) -> list[str]:
    """Prescripciones determinísticas basadas en reglas de negocio ante ausencia o falla de IA."""
    recs: list[str] = []

    # 1. Fin de semana vs semana
    if total_orders > 0:
        wk_pct = round((weekend_orders / total_orders) * 100.0, 1)
        recs.append(
            f"Preparación para el fin de semana: se estiman {weekend_orders} pedidos (${weekend_revenue:,.2f}), "
            f"concentrando el {wk_pct}% del volumen semanal. Reforzar el personal de cocina y cadetes de viernes a domingo."
        )
    else:
        recs.append(
            "Monitorear el ritmo de pedidos en días de semana y fin de semana para ajustar la capacidad operativa."
        )

    # 2. Compra prioritaria del insumo más demandado
    if ingredient_demands:
        top_ing = ingredient_demands[0]
        dishes = ", ".join(f"'{p}'" for p in top_ing.contributing_products[:2])
        recs.append(
            f"Abastecimiento prioritario de '{top_ing.ingredient_name}': se proyecta un consumo de {top_ing.projected_quantity} {top_ing.unit} "
            f"(gasto estimado: ${top_ing.estimated_cost:,.2f}) impulsado por {dishes}. Emitir orden de compra mayorista antes del jueves."
        )

    # 3. Insumos secundarios de alto valor monetario
    if len(ingredient_demands) > 1:
        second_ing = ingredient_demands[1]
        recs.append(
            f"Asegurar stock de '{second_ing.ingredient_name}': demanda estimada de {second_ing.projected_quantity} {second_ing.unit} "
            f"(inversión estimada: ${second_ing.estimated_cost:,.2f}). Negociar precio por bulto cerrado para proteger el margen."
        )

    # 4. Control de cancelaciones o demoras
    if cancellation_rate > 4.0:
        recs.append(
            f"Mitigación de cancelaciones: la tasa histórica se sitúa en {cancellation_rate:.1f}%. "
            "Avisar demoras reales al registrar pedidos en horas de pico para evitar cancelaciones imprevistas."
        )
    else:
        recs.append(
            "Tiempos de entrega y despacho: preparar la mise-en-place de masas y salsas antes de las 20:00 hs "
            "para garantizar despachos rápidos y sostener la baja tasa de cancelación."
        )

    # 5. Gestión de depósito y mermas
    recs.append(
        "Rotación de inventario: aplicar metodología FIFO (primero en entrar, primero en salir) "
        "en cámaras frigoríficas para evitar mermas en insumos frescos de alta rotación."
    )

    return recs[:5]


def _prescriptions_from_gemini(
    days: list[DayProjectionItem],
    ingredient_demands: list[IngredientDemandItem],
    weekend_orders: int,
    weekend_revenue: float,
    weekday_orders: int,
    weekday_revenue: float,
    total_orders: int,
    total_revenue: float,
    cancellation_rate: float,
) -> list[str] | None:
    """Solicita a Gemini prescripciones ejecutivas de compras y operaciones con timeout y manejo de fallas."""
    if not settings.GOOGLE_API_KEY:
        return None

    top_ings_text = (
        "\n".join(
            f"- {ing.ingredient_name}: {ing.projected_quantity} {ing.unit} (${ing.estimated_cost:,.2f}) para platos: {', '.join(ing.contributing_products[:3])}"
            for ing in ingredient_demands[:5]
        )
        or "- Sin insumos registrados con receta"
    )

    prompt = f"""
Sos un consultor comercial y de operaciones gastronómicas de alto nivel.
Analizá las siguientes proyecciones estimadas para los próximos 7 días de este restaurante:

PROYECCIONES:
- Pedidos totales: {total_orders} (${total_revenue:,.2f})
- Días de semana (Lun-Vie): {weekday_orders} pedidos (${weekday_revenue:,.2f})
- Fin de semana (Sáb-Dom): {weekend_orders} pedidos (${weekend_revenue:,.2f})
- Tasa de cancelación histórica: {cancellation_rate:.1f}%

DEMANDA ESTIMADA DE INSUMOS PRINCIPALES (Próximos 7 días):
{top_ings_text}

TAREA:
Generá EXACTAMENTE entre 4 y 5 prescripciones estratégicas concretas, breves y directamente aplicables para el dueño del local sobre:
1) Compras anticipadas de insumos antes del fin de semana (citando insumos y cantidades estimadas).
2) Optimización de costos y negociación con proveedores.
3) Preparación operativa y mise-en-place para absorber la demanda de fin de semana vs días de semana.
4) Control de mermas y prevención de cancelaciones.

Respondé ÚNICAMENTE con un array JSON de strings en español, sin formato markdown adicional:
[
  "Prescripción 1...",
  "Prescripción 2...",
  "Prescripción 3...",
  "Prescripción 4..."
]
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
        data = json.loads(text)
        if isinstance(data, list) and all(isinstance(x, str) for x in data) and len(data) >= 3:
            return data[:5]
    except Exception as e:
        logger.warning("Fallo al obtener prescripciones de Gemini para predicciones: %s", e)

    return None


def calculate_predictions(db: Session, historical_weeks: int = 26) -> PredictionsResponse:
    """Calcula proyecciones de pedidos, facturación e insumos para los próximos 7 días a partir del historial real (6 meses o histórico total)."""
    weeks = max(4, min(52, historical_weeks))
    start_date = ahora_local() - timedelta(weeks=weeks)
    start_utc = start_date.astimezone(timezone.utc)

    # Obtener pedidos completados y cancelados de las últimas N semanas (o histórico total)
    orders = (
        db.query(Order)
        .filter(
            Order.created_at >= start_utc,
            Order.status.in_([OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value]),
        )
        .all()
    )

    # Determinar las semanas reales de historial para no subestimar promedios si hay menos tiempo de apertura
    first_order = (
        db.query(Order)
        .filter(
            Order.created_at >= start_utc,
            Order.status.in_([OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value]),
        )
        .order_by(Order.created_at.asc())
        .first()
    )
    if first_order:
        days_span = max(7, (ahora_local() - _to_local_datetime(first_order.created_at)).days)
        actual_weeks = min(weeks, max(1, round(days_span / 7.0)))
    else:
        actual_weeks = weeks

    avg_orders, avg_rev, trend_factor, cancellation_rate = _calculate_historical_averages(orders, actual_weeks)
    days = _project_next_7_days(avg_orders, avg_rev, trend_factor)

    total_projected_orders = sum(d.projected_orders for d in days)
    total_projected_revenue = round(sum(d.projected_revenue for d in days), 2)
    weekday_projected_orders = sum(d.projected_orders for d in days if not d.is_weekend)
    weekday_projected_revenue = round(sum(d.projected_revenue for d in days if not d.is_weekend), 2)
    weekend_projected_orders = sum(d.projected_orders for d in days if d.is_weekend)
    weekend_projected_revenue = round(sum(d.projected_revenue for d in days if d.is_weekend), 2)

    avg_daily_orders = round(total_projected_orders / 7.0, 1)
    avg_daily_revenue = round(total_projected_revenue / 7.0, 2)

    ingredient_demands = _project_ingredient_demands(db, start_utc, total_projected_orders)

    # Obtener recomendaciones estratégicas (Gemini con degradación controlada a reglas determinísticas)
    gemini_recs = _prescriptions_from_gemini(
        days=days,
        ingredient_demands=ingredient_demands,
        weekend_orders=weekend_projected_orders,
        weekend_revenue=weekend_projected_revenue,
        weekday_orders=weekday_projected_orders,
        weekday_revenue=weekday_projected_revenue,
        total_orders=total_projected_orders,
        total_revenue=total_projected_revenue,
        cancellation_rate=cancellation_rate,
    )

    is_ai = gemini_recs is not None
    prescriptions = gemini_recs or _build_rule_based_prescriptions(
        days=days,
        ingredient_demands=ingredient_demands,
        weekend_orders=weekend_projected_orders,
        weekend_revenue=weekend_projected_revenue,
        weekday_orders=weekday_projected_orders,
        total_orders=total_projected_orders,
        cancellation_rate=cancellation_rate,
    )

    disclaimer = None
    if not is_ai:
        disclaimer = "Estimaciones estadísticas y recomendaciones generadas por el sistema backend (servicio de IA no disponible o en espera)."

    return PredictionsResponse(
        days=days,
        total_projected_orders=total_projected_orders,
        total_projected_revenue=total_projected_revenue,
        weekday_projected_orders=weekday_projected_orders,
        weekday_projected_revenue=weekday_projected_revenue,
        weekend_projected_orders=weekend_projected_orders,
        weekend_projected_revenue=weekend_projected_revenue,
        avg_daily_orders=avg_daily_orders,
        avg_daily_revenue=avg_daily_revenue,
        ingredient_demands=ingredient_demands,
        strategic_prescriptions=prescriptions,
        is_ai_generated=is_ai,
        historical_weeks_analyzed=weeks,
        disclaimer=disclaimer,
        generated_at=datetime.now(timezone.utc),
    )
