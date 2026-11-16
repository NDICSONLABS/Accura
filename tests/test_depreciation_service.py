import pytest
from decimal import Decimal
from datetime import date

from app.models.enums import (
    UserRole, PeriodStatus, FiscalYearStatus,
    DepreciationMethod, AssetStatus, DepreciationStatus,
)
from app.models.user import User
from app.models.account import Account
from app.models.period import FiscalYear, AccountingPeriod
from app.models.fixed_asset import FixedAsset, DepreciationScheduleLine
from app.models.settings import OrganizationSetting
from app.models.currency import Currency
from app.services.depreciation_service import (
    create_fixed_asset,
    generate_period_depreciation,
    post_period_depreciation,
    FixedAssetCreateSchema,
)
from app.services.statements_service import get_compte_de_resultat, get_bilan


@pytest.fixture
def dep_context(db_session):
    settings = db_session.query(OrganizationSetting).first()
    settings.maker_checker_approval_enabled = False
    db_session.commit()

    user = User(email="dep@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add(user)
    db_session.flush()

    fy = FiscalYear(code="2080", start_date=date(2080, 1, 1), end_date=date(2080, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    p1 = AccountingPeriod(fiscal_year_id=fy.id, period_number=1, start_date=date(2080, 1, 1), end_date=date(2080, 1, 31), status=PeriodStatus.OPEN)
    p2 = AccountingPeriod(fiscal_year_id=fy.id, period_number=2, start_date=date(2080, 2, 1), end_date=date(2080, 2, 29), status=PeriodStatus.OPEN)
    db_session.add_all([p1, p2])
    db_session.flush()

    asset_acc = db_session.query(Account).filter(Account.code == "211").first()
    expense_acc = db_session.query(Account).filter(Account.code == "681").first()
    accum_acc = db_session.query(Account).filter(Account.code == "284").first()

    return {"user": user, "fy": fy, "p1": p1, "p2": p2,
            "asset_acc": asset_acc, "expense_acc": expense_acc, "accum_acc": accum_acc}


def _asset(ctx, code, method=DepreciationMethod.STRAIGHT_LINE, rate=None, cost="1200000", residual="0", life=12):
    return FixedAssetCreateSchema(
        code=code,
        label=f"Asset {code}",
        acquisition_date=date(2080, 1, 1),
        in_service_date=date(2080, 1, 1),
        acquisition_cost=Decimal(cost),
        residual_value=Decimal(residual),
        useful_life_months=life,
        method=method,
        declining_rate_percent=Decimal(rate) if rate else None,
        asset_account_code=ctx["asset_acc"].code,
        expense_account_code=ctx["expense_acc"].code,
        accum_account_code=ctx["accum_acc"].code,
    )


def test_straight_line_depreciation_posts_balanced_entry(db_session, dep_context):
    ctx = dep_context
    asset = create_fixed_asset(db_session, ctx["user"].id, _asset(ctx, "FA-TST-001"))

    lines = generate_period_depreciation(db_session, ctx["p1"].id)
    assert len(lines) == 1
    assert lines[0].amount == Decimal("100000")

    entry = post_period_depreciation(db_session, ctx["p1"].id, ctx["user"].id)
    assert entry.status.value == "POSTED"

    posted_line = db_session.query(DepreciationScheduleLine).filter_by(asset_id=asset.id).first()
    assert posted_line.status == DepreciationStatus.POSTED
    assert posted_line.journal_entry_id == entry.id

    cr = get_compte_de_resultat(db_session, ctx["fy"].id)
    assert cr.total_charges == Decimal("100000")

    bilan = get_bilan(db_session, ctx["fy"].id)
    assert bilan.total_actif == bilan.total_passif


def test_declining_balance_first_month(db_session, dep_context):
    ctx = dep_context
    create_fixed_asset(
        db_session, ctx["user"].id,
        _asset(ctx, "FA-TST-002", method=DepreciationMethod.DECLINING_BALANCE,
               rate="20", cost="1200000", residual="100000", life=60),
    )

    lines = generate_period_depreciation(db_session, ctx["p1"].id)
    assert lines[0].amount == Decimal("20000")


def test_cannot_post_depreciation_twice(db_session, dep_context):
    ctx = dep_context
    create_fixed_asset(db_session, ctx["user"].id, _asset(ctx, "FA-TST-003"))

    generate_period_depreciation(db_session, ctx["p1"].id)
    post_period_depreciation(db_session, ctx["p1"].id, ctx["user"].id)

    with pytest.raises(ValueError) as excinfo:
        post_period_depreciation(db_session, ctx["p1"].id, ctx["user"].id)

    assert "No scheduled depreciation lines" in str(excinfo.value)