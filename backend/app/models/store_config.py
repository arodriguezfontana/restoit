from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class StoreConfig(Base):
    """Configuración de identidad institucional y visual del local."""

    __tablename__ = "store_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_name: Mapped[str] = mapped_column(String(100), nullable=False, default="RestoIT")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme_color: Mapped[str] = mapped_column(String(30), nullable=False, default="black")
    login_bg: Mapped[str] = mapped_column(String(50), nullable=False, default="bistro")
    # Imagen propia (Data URL) que se usa como fondo cuando login_bg es "custom".
    login_bg_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fondo del panel de administración: "none" (liso, como siempre), "color" (un color a elección), una de las imágenes incluidas o "custom".
    panel_bg: Mapped[str] = mapped_column(String(50), nullable=False, default="none", server_default="none")
    # Imagen propia (Data URL) que se usa como fondo del panel cuando panel_bg es "custom".
    panel_bg_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Color (#rrggbb) que se usa como fondo del panel cuando panel_bg es "color".
    panel_bg_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # Links externos independientes para el menú y las promociones
    menu_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotions_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    mp_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Medios de pago que acepta el local.
    accepts_cash: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    accepts_transfer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Datos de cobro de la transferencia: alias o CBU, y el titular de la cuenta.
    transfer_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transfer_cbu: Mapped[str | None] = mapped_column(String(22), nullable=True)
    transfer_holder: Mapped[str | None] = mapped_column(String(100), nullable=True)
    accepts_card: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # A qué pedidos se cobra con tarjeta: "pickup" (retiro), "delivery" (envío) o "both" (los dos).
    card_applies_to: Mapped[str] = mapped_column(String(10), nullable=False, default="both", server_default="both")
    # Horas que se guarda el comprobante de una transferencia antes de eliminarse.
    proof_retention_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=48, server_default="48")
    accepts_mercadopago: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Seguridad de caja mediante PIN (opcional)
    cash_pin_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    cash_pin: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Demora inteligente: si está apagada el sistema no calcula demoras con el historial.
    smart_delay_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
