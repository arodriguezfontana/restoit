from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class DelayRule(Base):
    """Regla de demora fija: con una cantidad de pedidos en cola dentro del rango, un método de entrega promete
    `minutes` minutos. `max_orders` vacío significa "o más" (rango abierto)."""

    __tablename__ = "delay_rules"
    __table_args__ = (
        CheckConstraint("delivery_method IN ('retiro', 'domicilio')", name="ck_delay_rules_delivery_method"),
        CheckConstraint("min_orders >= 0", name="ck_delay_rules_min_orders"),
        CheckConstraint("max_orders IS NULL OR max_orders >= min_orders", name="ck_delay_rules_max_orders"),
        CheckConstraint("minutes > 0", name="ck_delay_rules_minutes"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    delivery_method: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    min_orders: Mapped[int] = mapped_column(Integer, nullable=False)
    max_orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    def covers(self, queue_size: int) -> bool:
        return queue_size >= self.min_orders and (self.max_orders is None or queue_size <= self.max_orders)
