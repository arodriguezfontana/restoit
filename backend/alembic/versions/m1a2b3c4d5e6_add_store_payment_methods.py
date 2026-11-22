"""add payment methods to store config

Revision ID: m1a2b3c4d5e6
Revises: l1a2b3c4d5e6
Create Date: 2026-11-18 12:00:00.000000

"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'm1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'l1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('store_configs', sa.Column('accepts_cash', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('store_configs', sa.Column('accepts_transfer', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('store_configs', sa.Column('transfer_alias', sa.String(length=100), nullable=True))
    op.add_column('store_configs', sa.Column('transfer_cbu', sa.String(length=22), nullable=True))
    op.add_column('store_configs', sa.Column('transfer_holder', sa.String(length=100), nullable=True))
    op.add_column('store_configs', sa.Column('accepts_card', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('store_configs', sa.Column('card_applies_to', sa.String(length=10), nullable=False, server_default='both'))
    op.add_column('store_configs', sa.Column('accepts_mercadopago', sa.Boolean(), nullable=False, server_default=sa.false()))
    # Los locales que ya cobraban con MercadoPago (hay credenciales) siguen haciéndolo.
    if os.environ.get('MERCADOPAGO_ACCESS_TOKEN', '').strip():
        op.execute(sa.text('UPDATE store_configs SET accepts_mercadopago = :yes').bindparams(yes=True))


def downgrade() -> None:
    for column in (
        'accepts_mercadopago', 'card_applies_to', 'accepts_card', 'transfer_holder',
        'transfer_cbu', 'transfer_alias', 'accepts_transfer', 'accepts_cash',
    ):
        op.drop_column('store_configs', column)
