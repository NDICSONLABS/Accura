"""seed sycebnl coa

Revision ID: 002
Revises: 001
Create Date: 2026-11-16 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Currencies (no timestamps)
    op.execute("INSERT INTO currencies (code, name, is_functional) VALUES ('XAF', 'Franc CFA (BEAC)', true);")
    op.execute("INSERT INTO currencies (code, name, is_functional) VALUES ('USD', 'US Dollar', false);")
    op.execute("INSERT INTO currencies (code, name, is_functional) VALUES ('EUR', 'Euro', false);")

    # Default Fund & Project (with NOW() for timestamps)
    op.execute("""
        INSERT INTO funds (code, label, donor_name, currency_code, is_restricted, created_at, updated_at) 
        VALUES ('GENERAL', 'Fonds Non Affectés', 'Local', 'XAF', false, NOW(), NOW());
    """)
    op.execute("""
        INSERT INTO projects (code, label, fund_id, created_at, updated_at)
        SELECT 'DEFAULT', 'Projet Par Défaut', id, NOW(), NOW()FROM funds WHERE code = 'GENERAL';
               """)

    # Default Settings (with NOW() for timestamps)
    op.execute("""
        INSERT INTO organization_settings (
            multi_currency_enabled, donor_fund_tracking_enabled, project_cost_center_enabled, 
            budget_control_enabled, budget_enforcement_mode, maker_checker_approval_enabled, 
            tax_withholding_enabled, default_unrestricted_fund_id, default_project_id, created_at, updated_at
        )
        SELECT false, false, false, false, 'NONE', false, false, f.id, p.id, NOW(), NOW()
        FROM funds f, projects p WHERE f.code = 'GENERAL' AND p.code = 'DEFAULT';
    """)

    # SYCEBNL Chart of Accounts (Core Subset) (with NOW() for timestamps)
    accounts = [
        ("101", "Capital social", 1, "CREDIT", False, False),
        ("161", "Fonds associatif sans restriction", 1, "CREDIT", False, False),
        ("162", "Fonds dédiés sur subventions", 1, "CREDIT", False, False),
        ("211", "Immobilisations corporelles", 2, "DEBIT", False, False),
        ("401", "Fournisseurs", 4, "CREDIT", True, True),
        ("411", "Clients et comptes rattachés", 4, "DEBIT", True, True),
        ("447", "État, impôts retenus à la source", 4, "CREDIT", False, False),
        ("478", "Écarts de conversion - Actif", 4, "DEBIT", False, False),
        ("479", "Écarts de conversion - Passif", 4, "CREDIT", False, False),
        ("521", "Banques", 5, "DEBIT", True, False),
        ("571", "Caisse", 5, "DEBIT", True, False),
        ("601", "Achats stockés", 6, "DEBIT", True, False),
        ("676", "Pertes de change", 6, "DEBIT", True, False),
        ("701", "Ventes de produits finis", 7, "CREDIT", True, False),
        ("776", "Gains de change", 7, "CREDIT", True, False),
    ]

    for code, label, cls, balance, is_postable, requires_tp in accounts:
        op.execute(f"""
            INSERT INTO accounts (code, label, account_class, normal_balance, is_postable, requires_third_party, is_active, default_currency_code, created_at, updated_at)
            VALUES ('{code}', '{label}', {cls}, '{balance}', {str(is_postable).lower()}, {str(requires_tp).lower()}, true, 'XAF', NOW(), NOW());
        """)

    # Default Journals (with NOW() for timestamps)
    journals = [("ACH", "Achats", "PURCHASE"), ("VTE", "Ventes", "SALE"), ("BQ1", "Banque Principale", "BANK"), ("CAI", "Caisse", "CASH"), ("OD", "Opérations Diverses", "MANUAL")]
    for code, label, jtype in journals:
        op.execute(f"INSERT INTO accounting_journals (code, label, journal_type, created_at, updated_at) VALUES ('{code}', '{label}', '{jtype}', NOW(), NOW());")


def downgrade() -> None:
    op.execute("DELETE FROM accounting_journals WHERE code IN ('ACH', 'VTE', 'BQ1', 'CAI', 'OD');")
    op.execute("DELETE FROM accounts WHERE code IN ('101', '161', '162', '211', '401', '411', '447', '478', '479', '521', '571', '601', '676', '701', '776');")
    op.execute("DELETE FROM organization_settings;")
    op.execute("DELETE FROM projects WHERE code = 'DEFAULT';")
    op.execute("DELETE FROM funds WHERE code = 'GENERAL';")
    op.execute("DELETE FROM currencies WHERE code IN ('XAF', 'USD', 'EUR');")