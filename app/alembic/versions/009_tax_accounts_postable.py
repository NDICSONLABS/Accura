"""make tax and translation accounts postable

Revision ID: 009
Revises: 008
Create Date: 2026-11-17 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 447 = withholding tax, 445 = recoverable VAT,
    # 478/479 = translation adjustments (needed for FX revaluation).
    op.execute("""
        UPDATE accounts
        SET is_postable = true,
            requires_third_party = false,
            is_active = true,
            updated_at = NOW()
        WHERE code IN ('445', '447', '478', '479');
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE accounts
        SET is_postable = false,
            updated_at = NOW()
        WHERE code IN ('447', '478', '479');
    """)