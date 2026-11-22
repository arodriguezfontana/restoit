"""remove the order acceptance stage: no more 'Pendiente' / 'Rechazado', add orders.needs_attention

Revision ID: q1a2b3c4d5e6
Revises: p1a2b3c4d5e6
Create Date: 2026-11-20 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'q1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'p1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_STATUSES = "'Confirmado', 'En Camino', 'Listo para Retirar', 'Finalizado', 'Cancelado'"
_OLD_STATUSES = "'Pendiente', 'Confirmado', 'En Camino', 'Listo para Retirar', 'Finalizado', 'Rechazado', 'Cancelado'"


def upgrade() -> None:
    # Los pedidos que esperaban respuesta pasan a prepararse (sin demora: nunca se les asignó una); los rechazados
    # quedan como cancelados. Ojo: los pendientes abiertos nunca se imprimieron ni recibieron su link de pago.
    op.execute("UPDATE orders SET status = 'Confirmado' WHERE status = 'Pendiente'")
    op.execute("UPDATE orders SET status = 'Cancelado' WHERE status = 'Rechazado'")
    op.execute("UPDATE order_status_events SET status = 'Cancelado' WHERE status = 'Rechazado'")
    with op.batch_alter_table('orders') as batch_op:
        batch_op.add_column(sa.Column('needs_attention', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.drop_constraint('ck_orders_status', type_='check')
        batch_op.create_check_constraint('ck_orders_status', f"status IN ({_NEW_STATUSES})")


def downgrade() -> None:
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_constraint('ck_orders_status', type_='check')
        batch_op.create_check_constraint('ck_orders_status', f"status IN ({_OLD_STATUSES})")
        batch_op.drop_column('needs_attention')
