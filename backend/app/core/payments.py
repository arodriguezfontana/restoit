from app.core.config import settings


def mercadopago_configured() -> bool:
    """Si el sistema tiene credenciales de MercadoPago para cobrar."""
    return bool(settings.MERCADOPAGO_ACCESS_TOKEN.strip())
