"""donor grants and budget control

Revision ID: 010
Revises: 009
Create Date: 2026-11-17 16:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # entrystatus already exists (migration 001) — never recreate it.
    entry_status = sa.Enum(
        "DRAFT", "SUBMITTED", "APPROVED", "POSTED",
        name="entrystatus", create_type=False,
    )

    op.create_table(
        "donor_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("donor_third_party_id", sa.Integer(), sa.ForeignKey("third_parties.id"), nullable=False),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("funds.id"), nullable=False),
        sa.Column("currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("total_committed_foreign", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("fund_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("receivable_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("status", sa.Enum("DRAFT", "ACTIVE", "CLOSED", name="grantstatus"), nullable=False, server_default="DRAFT"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "grant_tranches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("grant_id", sa.Integer(), sa.ForeignKey("donor_grants.id"), nullable=False),
        sa.Column("tranche_number", sa.Integer(), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=False),
        sa.Column("foreign_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.Enum("PLANNED", "CALLED", "RECEIVED", name="tranchestatus"), nullable=False, server_default="PLANNED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("grant_id", "tranche_number", name="uq_grant_tranche_number"),
    )

    op.create_table(
        "fund_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("grant_id", sa.Integer(), sa.ForeignKey("donor_grants.id"), nullable=False),
        sa.Column("tranche_id", sa.Integer(), sa.ForeignKey("grant_tranches.id")),
        sa.Column("call_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("foreign_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 0), nullable=False),
        sa.Column("status", entry_status, nullable=False, server_default="DRAFT"),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("accounting_periods.id")),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "grant_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fund_call_id", sa.Integer(), sa.ForeignKey("fund_calls.id"), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("journal_code", sa.String(10), nullable=False),
        sa.Column("treasury_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("reference", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("foreign_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 0), nullable=False),
        sa.Column("receivable_cleared_base", sa.Numeric(18, 0), nullable=False),
        sa.Column("fx_gain_loss_base", sa.Numeric(18, 0), nullable=False, server_default="0"),
        sa.Column("status", entry_status, nullable=False, server_default="DRAFT"),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("accounting_periods.id")),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # SYCEBNL restricted fund accounts (Class 16x) + grant journal.
    op.execute("""
        INSERT INTO accounts
            (code, label, account_class, normal_balance, is_postable, requires_third_party,
             is_active, default_currency_code, created_at, updated_at)
        VALUES
            ('161', 'Fonds dédiés — Subventions d''exploitation', 1, 'CREDIT', true, false, true, 'XAF', NOW(), NOW()),
            ('162', 'Fonds dédiés — Subventions d''investissement', 1, 'CREDIT', true, false, true, 'XAF', NOW(), NOW())
        ON CONFLICT (code) DO NOTHING;
    """)

    op.execute("""
        INSERT INTO accounting_journals (code, label, journal_type, created_at, updated_at)
        VALUES ('SUB', 'Subventions & Appels de Fonds', 'GRANT', NOW(), NOW())
        ON CONFLICT (code) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("grant_receipts")
    op.drop_table("fund_calls")
    op.drop_table("grant_tranches")
    op.drop_table("donor_grants")
    op.execute("DELETE FROM accounting_journals WHERE code = 'SUB';")
    op.execute("DELETE FROM accounts WHERE code IN ('161', '162');")
    sa.Enum(name="tranchestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="grantstatus").drop(op.get_bind(), checkfirst=True)