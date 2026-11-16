"""add period lock metadata

Revision ID: 006
Revises: 005
Create Date: 2026-11-16 18:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('accounting_periods', sa.Column('closed_by_id', sa.Integer(), sa.ForeignKey('users.id')))
    op.add_column('accounting_periods', sa.Column('closed_at', sa.DateTime(timezone=True)))

def downgrade() -> None:
    op.drop_column('accounting_periods', 'closed_at')
    op.drop_column('accounting_periods', 'closed_by_id')