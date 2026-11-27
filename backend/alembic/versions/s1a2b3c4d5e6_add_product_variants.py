"""add product variants (ej. Grande / Chica, Carne / Pollo), the variant ordered in order_items and the variant
included in promotion_products

Revision ID: s1a2b3c4d5e6
Revises: r1a2b3c4d5e6
Create Date: 2026-11-25 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 's1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'r1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_variants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('price > 0', name='ck_product_variants_price'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'name', name='uq_product_variants_product_name'),
    )
    op.create_index('ix_product_variants_id', 'product_variants', ['id'], unique=False)
    op.create_index('ix_product_variants_product_id', 'product_variants', ['product_id'], unique=False)
    op.add_column('order_items', sa.Column('variant_name', sa.String(length=50), nullable=True))
    op.add_column('promotion_products', sa.Column('variant_name', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('promotion_products', 'variant_name')
    op.drop_column('order_items', 'variant_name')
    op.drop_index('ix_product_variants_product_id', table_name='product_variants')
    op.drop_index('ix_product_variants_id', table_name='product_variants')
    op.drop_table('product_variants')
