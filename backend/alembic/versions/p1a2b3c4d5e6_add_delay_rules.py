"""add delay rules, smart delay switch and fixed estimate source

Revision ID: p1a2b3c4d5e6
Revises: o1a2b3c4d5e6
Create Date: 2026-11-20 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'p1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'o1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('store_configs', sa.Column('smart_delay_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table(
        'delay_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('delivery_method', sa.String(length=10), nullable=False),
        sa.Column('min_orders', sa.Integer(), nullable=False),
        sa.Column('max_orders', sa.Integer(), nullable=True),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.CheckConstraint("delivery_method IN ('retiro', 'domicilio')", name='ck_delay_rules_delivery_method'),
        sa.CheckConstraint('min_orders >= 0', name='ck_delay_rules_min_orders'),
        sa.CheckConstraint('max_orders IS NULL OR max_orders >= min_orders', name='ck_delay_rules_max_orders'),
        sa.CheckConstraint('minutes > 0', name='ck_delay_rules_minutes'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_delay_rules_id'), 'delay_rules', ['id'], unique=False)
    op.create_index(op.f('ix_delay_rules_delivery_method'), 'delay_rules', ['delivery_method'], unique=False)
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_constraint('ck_orders_estimate_source', type_='check')
        batch_op.create_check_constraint(
            'ck_orders_estimate_source', "estimate_source IN ('smart', 'fixed', 'manual', 'default')"
        )


def downgrade() -> None:
    op.execute(sa.text("UPDATE orders SET estimate_source = 'default' WHERE estimate_source = 'fixed'"))
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_constraint('ck_orders_estimate_source', type_='check')
        batch_op.create_check_constraint(
            'ck_orders_estimate_source', "estimate_source IN ('smart', 'manual', 'default')"
        )
    op.drop_index(op.f('ix_delay_rules_delivery_method'), table_name='delay_rules')
    op.drop_index(op.f('ix_delay_rules_id'), table_name='delay_rules')
    op.drop_table('delay_rules')
    op.drop_column('store_configs', 'smart_delay_enabled')
