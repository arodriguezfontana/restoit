"""Estimación de la demora de un pedido a partir del historial real del local.

Modo inteligente (si el local lo tiene activado): si hay suficientes pedidos parecidos ya finalizados (mismo método de
entrega e ingresados con la misma cantidad de pedidos en cola), la demora es el promedio de su demora real
(`Order.actual_minutes`: desde que el pedido ingresó hasta que se finalizó). Si no, se aplica la regla de demora fija
del método de entrega y, si tampoco hay una, el pedido entra sin demora estimada. Los pedidos con demora manual o fija
también alimentan el historial.
"""

from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from app.models.order import DeliveryMethod
from app.repositories import order_repository
from app.services import delay_rule_service

# Pedidos parecidos necesarios para fiarse del promedio.
MIN_SAMPLES_FOR_SMART_ESTIMATE = 30
# Cuántos de los últimos pedidos parecidos se promedian (para que pese lo reciente).
MAX_SAMPLES_CONSIDERED = 100
# Tiempos fuera de este rango (pedido que quedó abierto, cambios de estado cargados a destiempo) se descartan.
MAX_PLAUSIBLE_MINUTES = 240


class EstimateMode(str, Enum):
    SMART = "smart"
    FIXED = "fixed"
    # Sin historial suficiente ni regla fija aplicable: no se informa demora.
    NONE = "none"


@dataclass(frozen=True)
class DelayEstimate:
    mode: EstimateMode
    # Demora calculada con el historial (modo inteligente) o de la regla fija que corresponde.
    minutes: int | None
    # Pedidos parecidos con los que se calculó (o los que hay, si todavía no alcanzan).
    samples: int
    min_samples: int
    # Pedidos en cola al momento de la estimación.
    queue_size: int

    @property
    def is_smart(self) -> bool:
        return self.mode == EstimateMode.SMART


def estimate_delay(db: Session, delivery_method: DeliveryMethod | str, queue_size: int) -> DelayEstimate:
    """Demora para un pedido que ingresa ahora, con `queue_size` pedidos en cola.

    Prioridad: la inteligente (si está activada y hay historial suficiente), después la regla fija del método de
    entrega que cubra la cantidad de pedidos en cola y, si no hay ninguna, no hay demora para informar.
    """
    method = DeliveryMethod(delivery_method).value
    samples = 0
    if delay_rule_service.is_smart_delay_enabled(db):
        durations = order_repository.finished_durations(db, method, queue_size, MAX_SAMPLES_CONSIDERED)
        durations = [m for m in durations if 0 < m <= MAX_PLAUSIBLE_MINUTES]
        samples = len(durations)
        if samples >= MIN_SAMPLES_FOR_SMART_ESTIMATE:
            average = max(1, round(sum(durations) / samples))
            return DelayEstimate(EstimateMode.SMART, average, samples, MIN_SAMPLES_FOR_SMART_ESTIMATE, queue_size)

    rule = delay_rule_service.rule_for(db, method, queue_size)
    if rule is not None:
        return DelayEstimate(EstimateMode.FIXED, rule.minutes, samples, MIN_SAMPLES_FOR_SMART_ESTIMATE, queue_size)
    return DelayEstimate(EstimateMode.NONE, None, samples, MIN_SAMPLES_FOR_SMART_ESTIMATE, queue_size)
