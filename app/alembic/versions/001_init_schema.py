"""init schema

Revision ID: 001
Revises:
Create Date: 2026-11-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Currencies
    op.create_table('currencies',
                    sa.Column('code', sa.String(3), primary_key=True),
                    sa.Column('name', sa.String(50), nullable=False),
                    sa.Column('is_functional', sa.Boolean(), nullable=False, default=False)
                    )

    # 2. Users
    op.create_table('users',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('email', sa.String(255), unique=True, nullable=False),
                    sa.Column('password_hash', sa.String(255), nullable=False),
                    sa.Column('role', sa.Enum('AUDITOR_VIEWER', 'ACCOUNTANT_PREPARER', 'FINANCE_MANAGER_APPROVER',
                                              'SYSTEM_ADMIN', name='userrole'), nullable=False),
                    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    # 3. Funds
    op.create_table('funds',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('code', sa.String(20), unique=True, nullable=False),
                    sa.Column('label', sa.String(255), nullable=False),
                    sa.Column('donor_name', sa.String(255)),
                    sa.Column('currency_code', sa.String(3), sa.ForeignKey('currencies.code'), nullable=False),
                    sa.Column('is_restricted', sa.Boolean(), nullable=False, default=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    # 4. Projects
    op.create_table('projects',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('code', sa.String(20), unique=True, nullable=False),
                    sa.Column('label', sa.String(255), nullable=False),
                    sa.Column('fund_id', sa.Integer(), sa.ForeignKey('funds.id')),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    # 5. Accounts
    op.create_table('accounts',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('code', sa.String(20), unique=True, nullable=False),
                    sa.Column('label', sa.String(255), nullable=False),
                    sa.Column('account_class', sa.Integer(), nullable=False),
                    sa.Column('parent_id', sa.Integer(), sa.ForeignKey('accounts.id')),
                    sa.Column('normal_balance', sa.Enum('DEBIT', 'CREDIT', name='normalbalance'), nullable=False),
                    sa.Column('is_postable', sa.Boolean(), nullable=False, default=False),
                    sa.Column('requires_third_party', sa.Boolean(), nullable=False, default=False),
                    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
                    sa.Column('default_currency_code', sa.String(3), sa.ForeignKey('currencies.code')),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    # 6. Fiscal Years & Periods
    op.create_table('fiscal_years',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('code', sa.String(10), unique=True, nullable=False),
                    sa.Column('start_date', sa.Date(), nullable=False),
                    sa.Column('end_date', sa.Date(), nullable=False),
                    sa.Column('status', sa.Enum('OPEN', 'CLOSED', name='fiscalyearstatus'), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    op.create_table('accounting_periods',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('fiscal_year_id', sa.Integer(), sa.ForeignKey('fiscal_years.id'), nullable=False),
                    sa.Column('period_number', sa.Integer(), nullable=False),
                    sa.Column('start_date', sa.Date(), nullable=False),
                    sa.Column('end_date', sa.Date(), nullable=False),
                    sa.Column('status', sa.Enum('OPEN', 'SOFT_LOCKED', 'CLOSED', name='periodstatus'), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    # 7. Journals & Third Parties
    op.create_table('accounting_journals',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('code', sa.String(10), unique=True, nullable=False),
                    sa.Column('label', sa.String(100), nullable=False),
                    sa.Column('journal_type', sa.String(50), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    op.create_table('third_parties',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('name', sa.String(255), nullable=False),
                    sa.Column('tax_id', sa.String(50)),
                    sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    # 8. Budget Lines
    op.create_table('budget_lines',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
                    sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id')),
                    sa.Column('fund_id', sa.Integer(), sa.ForeignKey('funds.id')),
                    sa.Column('fiscal_year_id', sa.Integer(), sa.ForeignKey('fiscal_years.id'), nullable=False),
                    sa.Column('approved_amount', sa.Numeric(18, 0), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    # 9. Ledger (Entries & Lines)
    op.create_table('journal_entries',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('journal_id', sa.Integer(), sa.ForeignKey('accounting_journals.id'), nullable=False),
                    sa.Column('period_id', sa.Integer(), sa.ForeignKey('accounting_periods.id'), nullable=False),
                    sa.Column('entry_date', sa.Date(), nullable=False),
                    sa.Column('voucher_number', sa.String(50), unique=True, nullable=False),
                    sa.Column('reference', sa.String(100)),
                    sa.Column('description', sa.String(500), nullable=False),
                    sa.Column('status', sa.Enum('DRAFT', 'SUBMITTED', 'APPROVED', 'POSTED', name='entrystatus'),
                              nullable=False),
                    sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('approved_by_id', sa.Integer(), sa.ForeignKey('users.id')),
                    sa.Column('posted_at', sa.DateTime(timezone=True)),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    op.create_table('journal_lines',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('entry_id', sa.Integer(), sa.ForeignKey('journal_entries.id'), nullable=False),
                    sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
                    sa.Column('third_party_id', sa.Integer(), sa.ForeignKey('third_parties.id')),
                    sa.Column('fund_id', sa.Integer(), sa.ForeignKey('funds.id')),
                    sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id')),
                    sa.Column('budget_line_id', sa.Integer(), sa.ForeignKey('budget_lines.id')),
                    sa.Column('currency_code', sa.String(3), sa.ForeignKey('currencies.code'), nullable=False),
                    sa.Column('exchange_rate', sa.Numeric(18, 6), nullable=False),
                    sa.Column('foreign_debit', sa.Numeric(18, 2), nullable=False, default=0),
                    sa.Column('foreign_credit', sa.Numeric(18, 2), nullable=False, default=0),
                    sa.Column('base_debit', sa.Numeric(18, 0), nullable=False, default=0),
                    sa.Column('base_credit', sa.Numeric(18, 0), nullable=False, default=0),
                    sa.Column('description', sa.String(255))
                    )

    # 10. Settings & Audit
    op.create_table('organization_settings',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('multi_currency_enabled', sa.Boolean(), nullable=False, default=False),
                    sa.Column('donor_fund_tracking_enabled', sa.Boolean(), nullable=False, default=False),
                    sa.Column('project_cost_center_enabled', sa.Boolean(), nullable=False, default=False),
                    sa.Column('budget_control_enabled', sa.Boolean(), nullable=False, default=False),
                    sa.Column('budget_enforcement_mode',
                              sa.Enum('NONE', 'WARN', 'STRICT', name='budgetenforcementmode'), nullable=False),
                    sa.Column('maker_checker_approval_enabled', sa.Boolean(), nullable=False, default=False),
                    sa.Column('tax_withholding_enabled', sa.Boolean(), nullable=False, default=False),
                    sa.Column('default_unrestricted_fund_id', sa.Integer(), sa.ForeignKey('funds.id')),
                    sa.Column('default_project_id', sa.Integer(), sa.ForeignKey('projects.id')),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    op.create_table('audit_log',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
                    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('ip_address', sa.String(45)),
                    sa.Column('entity_type', sa.String(100), nullable=False),
                    sa.Column('entity_id', sa.Integer(), nullable=False),
                    sa.Column('action', sa.String(50), nullable=False),
                    sa.Column('before_state', postgresql.JSONB()),
                    sa.Column('after_state', postgresql.JSONB())
                    )

    op.create_table('exchange_rates',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('currency_code', sa.String(3), sa.ForeignKey('currencies.code'), nullable=False),
                    sa.Column('rate', sa.Numeric(18, 6), nullable=False),
                    sa.Column('effective_date', sa.Date(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
                    )

    # --- STRICT LOCKDOWN TRIGGERS ---

    # 1. Audit Log Immutability
    op.execute("""
               CREATE
               OR REPLACE FUNCTION prevent_audit_log_modification() RETURNS TRIGGER AS $$
               BEGIN
        RAISE
               EXCEPTION 'Audit log is append-only. UPDATE and DELETE are not allowed.';
               END;
    $$
               LANGUAGE plpgsql;

               CREATE TRIGGER trg_prevent_audit_log_mod
                   BEFORE UPDATE OR
               DELETE
               ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_modification();
               """)

    # 2. Journal Entry Immutability
    op.execute("""
               CREATE
               OR REPLACE FUNCTION prevent_posted_entry_modification() RETURNS TRIGGER AS $$
               BEGIN
        IF
               OLD.status = 'POSTED' THEN
            RAISE EXCEPTION 'Cannot modify a POSTED journal entry. Use Contre-passation (Reversal).';
               END IF;
               RETURN NEW;
               END;
    $$
               LANGUAGE plpgsql;

               CREATE TRIGGER trg_prevent_posted_entry_mod
                   BEFORE UPDATE OR
               DELETE
               ON journal_entries
    FOR EACH ROW EXECUTE FUNCTION prevent_posted_entry_modification();
               """)

    # 3. Journal Line Immutability (if parent is POSTED)
    op.execute("""
               CREATE
               OR REPLACE FUNCTION prevent_posted_line_modification() RETURNS TRIGGER AS $$
    DECLARE
               entry_status TEXT;
               BEGIN
               SELECT status
               INTO entry_status
               FROM journal_entries
               WHERE id = COALESCE(NEW.entry_id, OLD.entry_id);
               IF
               entry_status = 'POSTED' THEN
            RAISE EXCEPTION 'Cannot modify lines of a POSTED journal entry.';
               END IF;
               RETURN COALESCE(NEW, OLD);
               END;
    $$
               LANGUAGE plpgsql;

               CREATE TRIGGER trg_prevent_posted_line_mod
                   BEFORE INSERT OR
               UPDATE OR
               DELETE
               ON journal_lines
                   FOR EACH ROW EXECUTE FUNCTION prevent_posted_line_modification();
               """)

    # 4. Balance Invariant on Post
    op.execute("""
               CREATE
               OR REPLACE FUNCTION check_journal_balance() RETURNS TRIGGER AS $$
    DECLARE
               total_debit NUMERIC(18,0);
        total_credit
               NUMERIC(18,0);
               BEGIN
        IF
               NEW.status = 'POSTED' THEN
               SELECT COALESCE(SUM(base_debit), 0), COALESCE(SUM(base_credit), 0)
               INTO total_debit, total_credit
               FROM journal_lines
               WHERE entry_id = NEW.id;

               IF
               total_debit != total_credit OR total_debit = 0 THEN
                RAISE EXCEPTION 'Journal entry % is unbalanced or zero. Debit: %, Credit: %', NEW.id, total_debit, total_credit;
               END IF;
               END IF;
               RETURN NEW;
               END;
    $$
               LANGUAGE plpgsql;

               CREATE TRIGGER trg_check_journal_balance_on_post
                   BEFORE UPDATE OF status
                   ON journal_entries
                   FOR EACH ROW WHEN (NEW.status = 'POSTED' AND OLD.status != 'POSTED')
    EXECUTE FUNCTION check_journal_balance();
               """)


def downgrade() -> None:
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS trg_check_journal_balance_on_post ON journal_entries")
    op.execute("DROP FUNCTION IF EXISTS check_journal_balance()")
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_posted_line_mod ON journal_lines")
    op.execute("DROP FUNCTION IF EXISTS prevent_posted_line_modification()")
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_posted_entry_mod ON journal_entries")
    op.execute("DROP FUNCTION IF EXISTS prevent_posted_entry_modification()")
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_log_mod ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_modification()")

    # Drop tables in reverse order of creation to respect foreign keys
    op.drop_table('exchange_rates')
    op.drop_table('audit_log')
    op.drop_table('organization_settings')
    op.drop_table('journal_lines')
    op.drop_table('journal_entries')
    op.drop_table('budget_lines')
    op.drop_table('third_parties')
    op.drop_table('accounting_journals')
    op.drop_table('accounting_periods')
    op.drop_table('fiscal_years')
    op.drop_table('accounts')
    op.drop_table('projects')
    op.drop_table('funds')
    op.drop_table('users')
    op.drop_table('currencies')