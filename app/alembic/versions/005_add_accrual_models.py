"""add accrual models

Revision ID: 005
Revises: 004
Create Date: 2026-11-16 16:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Use create_type=False because 'entrystatus' was already created in migration 001
    entry_status_enum = sa.Enum('DRAFT', 'SUBMITTED', 'APPROVED', 'POSTED', name='entrystatus', create_type=False)

    op.create_table('supplier_bills',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('third_party_id', sa.Integer(), sa.ForeignKey('third_parties.id'), nullable=False),
        sa.Column('bill_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('reference', sa.String(50), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('currency_code', sa.String(3), sa.ForeignKey('currencies.code'), nullable=False, server_default='XAF'),
        sa.Column('exchange_rate', sa.Numeric(18, 6), nullable=False, server_default='1.000000'),
        sa.Column('withholding_tax_base', sa.Numeric(18, 0), nullable=False, server_default='0'),
        sa.Column('status', entry_status_enum, nullable=False, server_default='DRAFT'),
        sa.Column('journal_entry_id', sa.Integer(), sa.ForeignKey('journal_entries.id')),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
    )

    op.create_table('supplier_bill_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('bill_id', sa.Integer(), sa.ForeignKey('supplier_bills.id'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id')),
        sa.Column('fund_id', sa.Integer(), sa.ForeignKey('funds.id')),
        sa.Column('budget_line_id', sa.Integer(), sa.ForeignKey('budget_lines.id')),
        sa.Column('description', sa.String(255)),
        sa.Column('foreign_amount', sa.Numeric(18, 2), nullable=False, server_default='0.00'),
        sa.Column('base_amount', sa.Numeric(18, 0), nullable=False, server_default='0'),
        sa.Column('is_vat_capitalized', sa.Boolean(), nullable=False, server_default='false')
    )

    op.create_table('treasury_settlements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('settlement_date', sa.Date(), nullable=False),
        sa.Column('journal_code', sa.String(10), nullable=False),
        sa.Column('reference', sa.String(50), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('status', entry_status_enum, nullable=False, server_default='DRAFT'),
        sa.Column('journal_entry_id', sa.Integer(), sa.ForeignKey('journal_entries.id')),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
    )

    op.create_table('settlement_allocations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('settlement_id', sa.Integer(), sa.ForeignKey('treasury_settlements.id'), nullable=False),
        sa.Column('bill_id', sa.Integer(), sa.ForeignKey('supplier_bills.id'), nullable=False),
        sa.Column('allocated_base_amount', sa.Numeric(18, 0), nullable=False, server_default='0'),
        sa.Column('allocated_foreign_amount', sa.Numeric(18, 2), nullable=False, server_default='0.00'),
        sa.Column('fx_gain_loss_base', sa.Numeric(18, 0), nullable=False, server_default='0')
    )

def downgrade() -> None:
    op.drop_table('settlement_allocations')
    op.drop_table('treasury_settlements')
    op.drop_table('supplier_bill_lines')
    op.drop_table('supplier_bills')