"""bills and settlements completion

Revision ID: 008
Revises: 007
Create Date: 2026-11-17 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("supplier_bills", sa.Column("deductible_vat_base", sa.Numeric(18, 0), nullable=False, server_default="0"))
    op.add_column("supplier_bills", sa.Column("vat_account_id", sa.Integer(), sa.ForeignKey("accounts.id")))
    op.add_column("supplier_bills", sa.Column("period_id", sa.Integer(), sa.ForeignKey("accounting_periods.id")))

    op.add_column("supplier_bill_lines", sa.Column("vat_amount", sa.Numeric(18, 0), nullable=False, server_default="0"))
    op.add_column("supplier_bill_lines", sa.Column("vat_deductible", sa.Boolean(), nullable=False, server_default="false"))

    op.add_column("treasury_settlements", sa.Column("third_party_id", sa.Integer(), sa.ForeignKey("third_parties.id")))
    op.add_column("treasury_settlements", sa.Column("treasury_account_id", sa.Integer(), sa.ForeignKey("accounts.id")))
    op.add_column("treasury_settlements", sa.Column("currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False, server_default="XAF"))
    op.add_column("treasury_settlements", sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=False, server_default="1.000000"))
    op.add_column("treasury_settlements", sa.Column("period_id", sa.Integer(), sa.ForeignKey("accounting_periods.id")))
    op.add_column("treasury_settlements", sa.Column("total_base_amount", sa.Numeric(18, 0), nullable=False, server_default="0"))
    op.add_column("treasury_settlements", sa.Column("fx_gain_loss_base", sa.Numeric(18, 0), nullable=False, server_default="0"))

    op.add_column("settlement_allocations", sa.Column("cash_base_amount", sa.Numeric(18, 0), nullable=False, server_default="0"))

    op.execute("""
        INSERT INTO accounts
            (code, label, account_class, normal_balance, is_postable, requires_third_party,
             is_active, default_currency_code, created_at, updated_at)
        VALUES
            ('445', 'État, TVA récupérable', 4, 'DEBIT', true, false, true, 'XAF', NOW(), NOW())
        ON CONFLICT (code) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM accounts WHERE code = '445';")
    op.drop_column("settlement_allocations", "cash_base_amount")
    op.drop_column("treasury_settlements", "fx_gain_loss_base")
    op.drop_column("treasury_settlements", "total_base_amount")
    op.drop_column("treasury_settlements", "period_id")
    op.drop_column("treasury_settlements", "exchange_rate")
    op.drop_column("treasury_settlements", "currency_code")
    op.drop_column("treasury_settlements", "treasury_account_id")
    op.drop_column("treasury_settlements", "third_party_id")
    op.drop_column("supplier_bill_lines", "vat_deductible")
    op.drop_column("supplier_bill_lines", "vat_amount")
    op.drop_column("supplier_bills", "period_id")
    op.drop_column("supplier_bills", "vat_account_id")
    op.drop_column("supplier_bills", "deductible_vat_base")