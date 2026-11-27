"""background for the public menu page

Revision ID: t1a2b3c4d5e6
Revises: s1a2b3c4d5e6
Create Date: 2026-11-27 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 't1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 's1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('store_configs', sa.Column('menu_bg', sa.String(length=50), nullable=False, server_default='none'))
    op.add_column('store_configs', sa.Column('menu_bg_image', sa.Text(), nullable=True))
    op.add_column('store_configs', sa.Column('menu_bg_color', sa.String(length=7), nullable=True))


def downgrade() -> None:
    op.drop_column('store_configs', 'menu_bg_color')
    op.drop_column('store_configs', 'menu_bg_image')
    op.drop_column('store_configs', 'menu_bg')
