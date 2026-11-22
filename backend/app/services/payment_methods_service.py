"""Medios de pago que acepta el local: de acá salen las opciones de la web, el bot y el mostrador, y es lo que
se verifica al registrar o cambiar el pago de un pedido."""

from sqlalchemy.orm import Session

from app.core.payments import mercadopago_configured
from app.models.order import DeliveryMethod, InvalidOrderError, PaymentMethod
from app.models.store_config import StoreConfig
from app.services.store_config_service import get_or_create_store_config

PAYMENT_LABELS = {
    PaymentMethod.CASH: "Efectivo",
    PaymentMethod.TRANSFER: "Transferencia",
    PaymentMethod.CARD: "Tarjeta",
    PaymentMethod.MERCADOPAGO: "MercadoPago",
}


# Cómo se dice que se paga con cada medio ("lo abonás en efectivo", "por transferencia", "con tarjeta"...).
PAYMENT_PHRASES = {
    PaymentMethod.CASH.value: "en efectivo",
    PaymentMethod.TRANSFER.value: "por transferencia",
    PaymentMethod.CARD.value: "con tarjeta",
    PaymentMethod.MERCADOPAGO.value: "por MercadoPago",
}


def options_text(methods: list[PaymentMethod]) -> str:
    """Los medios en texto: 'Efectivo', 'Efectivo y Tarjeta' o 'Efectivo, Tarjeta y MercadoPago'."""
    names = [PAYMENT_LABELS[method] for method in methods]
    return " y ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else "".join(names)


class PaymentMethodNotAcceptedError(InvalidOrderError):
    def __init__(self, method: PaymentMethod, accepted: list[PaymentMethod]):
        options = ", ".join(PAYMENT_LABELS[m] for m in accepted)
        super().__init__(f"El local no acepta {PAYMENT_LABELS[method]} para este pedido. Medios disponibles: {options}.")


def accepted_methods(config: StoreConfig, delivery_method: DeliveryMethod | str | None = None) -> list[PaymentMethod]:
    """Medios con los que se puede pagar un pedido (de retiro o envío, si se indica) según la configuración."""
    accepted = []
    if config.accepts_cash:
        accepted.append(PaymentMethod.CASH)
    if config.accepts_transfer:
        accepted.append(PaymentMethod.TRANSFER)
    if config.accepts_card and _card_applies(config.card_applies_to, delivery_method):
        accepted.append(PaymentMethod.CARD)
    # Sin credenciales no se puede cobrar por MercadoPago, aunque haya quedado activado.
    if config.accepts_mercadopago and mercadopago_configured():
        accepted.append(PaymentMethod.MERCADOPAGO)
    return accepted


def _card_applies(applies_to: str, delivery_method: DeliveryMethod | str | None) -> bool:
    if applies_to == "both" or delivery_method is None:
        return True
    pickup = DeliveryMethod(delivery_method) == DeliveryMethod.PICKUP
    return applies_to == ("pickup" if pickup else "delivery")


def accepted_payment_methods(db: Session, delivery_method: DeliveryMethod | str | None = None) -> list[PaymentMethod]:
    return accepted_methods(get_or_create_store_config(db), delivery_method)


def ensure_payment_method_accepted(
    db: Session, method: PaymentMethod | str | None, delivery_method: DeliveryMethod | str | None = None
) -> None:
    """Rechaza (PaymentMethodNotAcceptedError) un medio que el local no tiene habilitado. Sin medio, no controla."""
    if method is None:
        return
    method = PaymentMethod(method)
    accepted = accepted_payment_methods(db, delivery_method)
    if method not in accepted:
        raise PaymentMethodNotAcceptedError(method, accepted)


def transfer_instructions(db: Session) -> str:
    """Datos para transferir (alias, CBU y titular) en texto."""
    config = get_or_create_store_config(db)
    data = [f"alias {config.transfer_alias}" if config.transfer_alias else "", f"CBU {config.transfer_cbu}" if config.transfer_cbu else ""]
    return f"{', '.join(d for d in data if d)}, titular {config.transfer_holder}"


def describe_for_bot(db: Session) -> str:
    """Bloque de instrucciones del bot con los medios de pago que ofrece el local y sus datos de cobro."""
    config = get_or_create_store_config(db)
    lines = ["MEDIOS DE PAGO DEL LOCAL (ofrecé únicamente estos; nunca otro):"]
    for method in accepted_methods(config):
        text = f"- {PAYMENT_LABELS[method]} (valor para la herramienta: \"{method.value}\")"
        if method == PaymentMethod.TRANSFER:
            text += f": datos para transferir: {transfer_instructions(db)}"
        elif method == PaymentMethod.CARD:
            text += {
                "pickup": ": solo en pedidos con retiro por el local",
                "delivery": ": solo en pedidos con envío a domicilio",
            }.get(config.card_applies_to, "")
        lines.append(text)
    return "\n".join(lines)
