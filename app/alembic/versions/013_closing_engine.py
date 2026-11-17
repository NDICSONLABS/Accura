"""closing engine: fx revaluation and fiscal year close

Revision ID: 013
Revises: 012
Create Date: 2026-11-18 09:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    entry_status = sa.Enum(
        "DRAFT", "SUBMITTED", "APPROVED", "POSTED",
        name="entrystatus", create_type=False,
    )

    op.create_table(
        "fx_revaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fiscal_year_id", sa.Integer(), sa.ForeignKey("fiscal_years.id"), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("accounting_periods.id"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("status", entry_status, nullable=False, server_default="DRAFT"),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("reversal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("total_latent_loss_base", sa.Numeric(18, 0), nullable=False, server_default="0"),
        sa.Column("total_latent_gain_base", sa.Numeric(18, 0), nullable=False, server_default="0"),
        sa.Column("provision_expense_account_id", sa.Integer(), sa.ForeignKey("accounts.id")),
        sa.Column("provision_account_id", sa.Integer(), sa.ForeignKey("accounts.id")),
        sa.Column("provision_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "fx_revaluation_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("fx_revaluation_runs.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("third_party_id", sa.Integer(), sa.ForeignKey("third_parties.id")),
        sa.Column("currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("foreign_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("historical_base", sa.Numeric(18, 0), nullable=False),
        sa.Column("closing_rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("revalued_base", sa.Numeric(18, 0), nullable=False),
        sa.Column("difference_base", sa.Numeric(18, 0), nullable=False),
        sa.Column("direction", sa.Enum("LOSS", "GAIN", name="fxdirection"), nullable=False),
    )

    op.create_table(
        "fiscal_year_closes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fiscal_year_id", sa.Integer(), sa.ForeignKey("fiscal_years.id"), nullable=False, unique=True),
        sa.Column("result_base", sa.Numeric(18, 0), nullable=False),
        sa.Column("result_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id"), nullable=False),
        sa.Column("next_fiscal_year_id", sa.Integer(), sa.ForeignKey("fiscal_years.id")),
        sa.Column("carry_forward_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("closed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Upsert — never DO NOTHING (lessons from 447 / 161).
    op.execute("""
        INSERT INTO accounts
            (code, label, account_class, normal_balance, is_postable,
             requires_third_party, is_active, default_currency_code, created_at, updated_at)
        VALUES
            ('121', 'Report à nouveau', 1, 'CREDIT', true, false, true, 'XAF', NOW(), NOW()),
            ('131', 'Résultat net de l''exercice', 1, 'CREDIT', true, false, true, 'XAF', NOW(), NOW())
        ON CONFLICT (code) DO UPDATE SET
            is_postable = true, requires_third_party = false, is_active = true, updated_at = NOW();
    """)

    op.execute("""
        UPDATE accounts
        SET is_postable = true, requires_third_party = false, is_active = true, updated_at = NOW()
        WHERE code IN ('478', '479');
    """)

    op.execute("""
        INSERT INTO accounting_journals (code, label, journal_type, created_at, updated_at)
        VALUES ('CLOT', 'Clôture & Réévaluation', 'CLOSING', NOW(), NOW())
        ON CONFLICT (code) DO UPDATE SET label = EXCLUDED.label, updated_at = NOW();
    """)


def downgrade() -> None:
    op.drop_table("fx_revaluation_lines")
    op.drop_table("fiscal_year_closes")
    op.drop_table("fx_revaluation_runs")
    op.execute("DELETE FROM accounting_journals WHERE code = 'CLOT';")
    sa.Enum(name="fxdirection").drop(op.get_bind(), checkfirst=True)