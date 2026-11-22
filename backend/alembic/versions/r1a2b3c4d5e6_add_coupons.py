"""add coupons table

Revision ID: r1a2b3c4d5e6
Revises: q1a2b3c4d5e6
Create Date: 2026-11-21 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'q1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'coupons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('discount_percentage', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('discount_percentage >= 1 AND discount_percentage <= 100', name='ck_coupons_discount_percentage'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_coupons_code', 'coupons', ['code'], unique=True)
    op.create_index('ix_coupons_id', 'coupons', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_coupons_id', table_name='coupons')
    op.drop_index('ix_coupons_code', table_name='coupons')
    op.drop_table('coupons')
