from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.sql import func

from app.db.base_class import Base


class Coupon(Base):
    """Cupón de descuento porcentual exclusivo para pedidos de la web."""

    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint("discount_percentage >= 1 AND discount_percentage <= 100", name="ck_coupons_discount_percentage"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    discount_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @validates("code")
    def _validate_code(self, _key: str, code: str) -> str:
        cleaned = code.strip().upper()
        if not cleaned:
            raise ValueError("El código de cupón no puede estar vacío.")
        return cleaned
