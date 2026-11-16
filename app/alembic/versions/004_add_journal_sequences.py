"""add journal sequences

Revision ID: 004
Revises: 003
Create Date: 2026-11-16 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('journal_sequences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('journal_code', sa.String(10), nullable=False),
        sa.Column('fiscal_year_code', sa.String(10), nullable=False),
        sa.Column('current_sequence', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('journal_code', 'fiscal_year_code', name='uq_journal_fiscal_year')
    )

def downgrade() -> None:
    op.drop_table('journal_sequences')