"""postable restricted fund sub-accounts and flag assertions

Revision ID: 011
Revises: 010
Create Date: 2026-11-17 18:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postable sub-accounts under the existing 161 / 162 control accounts.
    op.execute("""
        INSERT INTO accounts
            (code, label, account_class, parent_id, normal_balance,
             is_postable, requires_third_party, is_active, default_currency_code,
             created_at, updated_at)
        VALUES
            ('1611', 'Fonds dédiés — Subventions d''exploitation', 1,
             (SELECT id FROM accounts WHERE code = '161'),
             'CREDIT', true, false, true, 'XAF', NOW(), NOW()),
            ('1621', 'Fonds dédiés — Subventions d''investissement', 1,
             (SELECT id FROM accounts WHERE code = '162'),
             'CREDIT', true, false, true, 'XAF', NOW(), NOW())
        ON CONFLICT (code) DO UPDATE SET
            label = EXCLUDED.label,
            account_class = 1,
            normal_balance = 'CREDIT',
            is_postable = true,
            requires_third_party = false,
            is_active = true,
            updated_at = NOW();
    """)

    # Idempotent assertions: every account the posting engine targets must be usable.
    op.execute("""
        UPDATE accounts
        SET is_postable = true, requires_third_party = false, is_active = true, updated_at = NOW()
        WHERE code IN ('445', '447', '478', '479', '681', '284', '676', '776', '521', '571');
    """)

    op.execute("""
        UPDATE accounts
        SET is_postable = true, requires_third_party = true, is_active = true, updated_at = NOW()
        WHERE code IN ('401', '411');
    """)


def downgrade() -> None:
    op.execute("DELETE FROM accounts WHERE code IN ('1611', '1621');")