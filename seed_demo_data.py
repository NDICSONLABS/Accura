"""
Idempotent demo data seeder for Accura SYCEBNL.
Run: python seed_demo_data.py
"""
import calendar
from datetime import date, datetime, timezone
from decimal import Decimal

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.models.enums import UserRole, FiscalYearStatus, PeriodStatus, NormalBalance
from app.models.period import FiscalYear, AccountingPeriod
from app.models.account import Account
from app.models.master_data import AccountingJournal, ThirdParty, Fund, Project, BudgetLine
from app.models.currency import Currency
from app.models.settings import OrganizationSetting


def get_or_create(db, model, defaults=None, **kwargs):
    instance = db.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    params = dict(kwargs)
    params.update(defaults or {})
    instance = model(**params)
    db.add(instance)
    db.flush()
    return instance, True


def run() -> None:
    db = SessionLocal()
    try:
        # -------------------------------------------------- USERS
        users = [
            ("admin@local.com", UserRole.SYSTEM_ADMIN),
            ("preparer@local.com", UserRole.ACCOUNTANT_PREPARER),
            ("approver@local.com", UserRole.FINANCE_MANAGER_APPROVER),
            ("auditor@local.com", UserRole.AUDITOR_VIEWER),
        ]
        for email, role in users:
            _, created = get_or_create(
                db, User,
                email=email,
                defaults={
                    "password_hash": get_password_hash("admin123"),
                    "role": role,
                    "is_active": True,
                    "language": "fr",
                },
            )
            if created:
                print(f"  + user {email}")

        # -------------------------------------------------- CURRENCIES
        for code, name, functional in [
            ("XAF", "Franc CFA (BEAC)", True),
            ("USD", "US Dollar", False),
            ("EUR", "Euro", False),
        ]:
            get_or_create(db, Currency, code=code, defaults={"name": name, "is_functional": functional})

        # -------------------------------------------------- FISCAL YEAR + PERIODS
        fy, created = get_or_create(
            db, FiscalYear,
            code="2026",
            defaults={
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 12, 31),
                "status": FiscalYearStatus.OPEN,
            },
        )
        if created:
            print("  + fiscal year 2026")

        for month in range(1, 13):
            last_day = calendar.monthrange(2026, month)[1]
            _, p_created = get_or_create(
                db, AccountingPeriod,
                fiscal_year_id=fy.id,
                period_number=month,
                defaults={
                    "start_date": date(2026, month, 1),
                    "end_date": date(2026, month, last_day),
                    "status": PeriodStatus.OPEN,
                },
            )
            if p_created:
                print(f"  + period 2026-{month:02d}")

        # -------------------------------------------------- JOURNALS
        for code, label, jtype in [
            ("ACH", "Achats", "PURCHASE"),
            ("VTE", "Ventes", "SALE"),
            ("BQ1", "Banque Principale", "BANK"),
            ("CAI", "Caisse", "CASH"),
            ("OD", "Opérations Diverses", "MANUAL"),
        ]:
            get_or_create(
                db, AccountingJournal,
                code=code,
                defaults={"label": label, "journal_type": jtype},
            )

        # -------------------------------------------------- FUNDS / PROJECTS
        general_fund, _ = get_or_create(
            db, Fund,
            code="GENERAL",
            defaults={
                "label": "Fonds Non Affectés",
                "donor_name": "Local",
                "currency_code": "XAF",
                "is_restricted": False,
            },
        )

        usaid_fund, _ = get_or_create(
            db, Fund,
            code="USAID-2026",
            defaults={
                "label": "USAID Grant 2026",
                "donor_name": "USAID",
                "currency_code": "USD",
                "is_restricted": True,
            },
        )

        default_project, _ = get_or_create(
            db, Project,
            code="DEFAULT",
            defaults={"label": "Projet Par Défaut", "fund_id": general_fund.id},
        )

        health_project, _ = get_or_create(
            db, Project,
            code="HEALTH-01",
            defaults={"label": "Community Health Program", "fund_id": usaid_fund.id},
        )

        # -------------------------------------------------- THIRD PARTIES
        acc_401 = db.query(Account).filter(Account.code == "401").first()
        acc_411 = db.query(Account).filter(Account.code == "411").first()

        if acc_401:
            for name, tax_id in [
                ("CAMWATER", "M012345678901"),
                ("ENEO CAMEROUN", "M098765432109"),
                ("FOURNISSEUR LOCAL SARL", "M055555555555"),
            ]:
                get_or_create(
                    db, ThirdParty,
                    name=name,
                    defaults={"tax_id": tax_id, "account_id": acc_401.id},
                )

        if acc_411:
            get_or_create(
                db, ThirdParty,
                name="BAILLEUR INSTITUTIONNEL",
                defaults={"tax_id": None, "account_id": acc_411.id},
            )

        # -------------------------------------------------- BUDGET LINES
        acc_601 = db.query(Account).filter(Account.code == "601").first()
        if acc_601:
            get_or_create(
                db, BudgetLine,
                account_id=acc_601.id,
                fiscal_year_id=fy.id,
                project_id=health_project.id,
                fund_id=usaid_fund.id,
                defaults={"approved_amount": Decimal("5000000")},
            )
            get_or_create(
                db, BudgetLine,
                account_id=acc_601.id,
                fiscal_year_id=fy.id,
                project_id=default_project.id,
                fund_id=general_fund.id,
                defaults={"approved_amount": Decimal("2000000")},
            )

        # -------------------------------------------------- SETTINGS
        settings = db.query(OrganizationSetting).first()
        if not settings:
            settings = OrganizationSetting(
                default_unrestricted_fund_id=general_fund.id,
                default_project_id=default_project.id,
            )
            db.add(settings)

        db.commit()

        print("\nSeed complete.")
        print("Login: admin@local.com / admin123")
        print("Other users: preparer@local.com, approver@local.com, auditor@local.com (same password)")
        print(f"Fiscal year 2026 has 12 OPEN periods.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()