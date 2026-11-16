"""fixed assets and depreciation

Revision ID: 007
Revises: 006
Create Date: 2026-11-17 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fixed_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("in_service_date", sa.Date(), nullable=False),
        sa.Column("acquisition_cost", sa.Numeric(18, 0), nullable=False),
        sa.Column("residual_value", sa.Numeric(18, 0), nullable=False, server_default="0"),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column(
            "method",
            sa.Enum("STRAIGHT_LINE", "DECLINING_BALANCE", name="depreciationmethod"),
            nullable=False,
            server_default="STRAIGHT_LINE",
        ),
        sa.Column("declining_rate_percent", sa.Numeric(5, 2)),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "FULLY_DEPRECIATED", "DISPOSED", name="assetstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("asset_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("expense_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("accum_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("funds.id")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id")),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "depreciation_schedule_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("fixed_assets.id"), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("accounting_periods.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("proposed_amount", sa.Numeric(18, 0), nullable=False),
        sa.Column("amount", sa.Numeric(18, 0), nullable=False),
        sa.Column(
            "status",
            sa.Enum("SCHEDULED", "POSTED", "SKIPPED", name="depreciationstatus"),
            nullable=False,
            server_default="SCHEDULED",
        ),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("asset_id", "period_id", name="uq_depreciation_asset_period"),
    )

    # Seed SYCEBNL depreciation accounts and journal.
    op.execute("""
        INSERT INTO accounts
            (code, label, account_class, normal_balance, is_postable, requires_third_party,
             is_active, default_currency_code, created_at, updated_at)
        VALUES
            ('681', 'Dotations aux amortissements', 6, 'DEBIT', true, false, true, 'XAF', NOW(), NOW()),
            ('284', 'Amortissements du matériel', 2, 'CREDIT', true, false, true, 'XAF', NOW(), NOW())
        ON CONFLICT (code) DO NOTHING;
    """)

    op.execute("""
        INSERT INTO accounting_journals (code, label, journal_type, created_at, updated_at)
        VALUES ('AMOR', 'Amortissements', 'DEPRECIATION', NOW(), NOW())
        ON CONFLICT (code) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("depreciation_schedule_lines")
    op.drop_table("fixed_assets")
    op.execute("DELETE FROM accounting_journals WHERE code = 'AMOR';")
    op.execute("DELETE FROM accounts WHERE code IN ('681', '284');")
    sa.Enum(name="depreciationstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="assetstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="depreciationmethod").drop(op.get_bind(), checkfirst=True)