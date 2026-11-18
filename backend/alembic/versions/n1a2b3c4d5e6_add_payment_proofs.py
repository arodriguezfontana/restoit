"""add payment proofs

Revision ID: n1a2b3c4d5e6
Revises: m1a2b3c4d5e6
Create Date: 2026-11-18 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'n1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'm1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # En desarrollo la app puede haber creado la tabla sola (create_all al arrancar) antes de esta migración: se
    # suma solo lo que falta.
    inspector = sa.inspect(op.get_bind())
    config_columns = {column['name'] for column in inspector.get_columns('store_configs')}
    if 'proof_retention_hours' not in config_columns:
        op.add_column('store_configs', sa.Column('proof_retention_hours', sa.Integer(), nullable=False, server_default='48'))
    if not inspector.has_table('payment_proofs'):
        op.create_table(
            'payment_proofs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=False),
            sa.Column('content_type', sa.String(length=20), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=False),
            sa.Column('data', sa.LargeBinary(), nullable=False),
            sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    existing_indexes = {index['name'] for index in sa.inspect(op.get_bind()).get_indexes('payment_proofs')}
    if 'ix_payment_proofs_order_id' not in existing_indexes:
        op.create_index('ix_payment_proofs_order_id', 'payment_proofs', ['order_id'], unique=True)
    if 'ix_payment_proofs_expires_at' not in existing_indexes:
        op.create_index('ix_payment_proofs_expires_at', 'payment_proofs', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_payment_proofs_expires_at', table_name='payment_proofs')
    op.drop_index('ix_payment_proofs_order_id', table_name='payment_proofs')
    op.drop_table('payment_proofs')
    op.drop_column('store_configs', 'proof_retention_hours')
