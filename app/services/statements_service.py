from sqlalchemy.orm import Session
from sqlalchemy import func, select, extract
from decimal import Decimal
from datetime import date
from app.models.ledger import JournalLine, JournalEntry
from app.models.account import Account
from app.models.master_data import ThirdParty
from app.models.period import AccountingPeriod
from app.models.enums import EntryStatus
from pydantic import BaseModel


class StatementRow(BaseModel):
    account_code: str
    account_label: str
    amount: Decimal


class CompteResultat(BaseModel):
    charges: list[StatementRow]
    produits: list[StatementRow]
    total_charges: Decimal
    total_produits: Decimal
    resultat: Decimal


class BilanRow(BaseModel):
    account_code: str
    account_label: str
    amount: Decimal


class Bilan(BaseModel):
    actif: list[BilanRow]
    passif: list[BilanRow]
    total_actif: Decimal
    total_passif: Decimal


class AgedBalanceRow(BaseModel):
    third_party_name: str
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_over_90: Decimal
    total: Decimal


def get_compte_de_resultat(
        db: Session,
        fiscal_year_id: int,
        fund_id: int | None = None,
        project_id: int | None = None
) -> CompteResultat:
    base_q = (
        select(
            Account.code, Account.label, Account.account_class,
            func.sum(JournalLine.base_debit).label("d"),
            func.sum(JournalLine.base_credit).label("c")
        )
        .join(JournalLine, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(AccountingPeriod, JournalEntry.period_id == AccountingPeriod.id)
        .where(
            JournalEntry.status == EntryStatus.POSTED,
            AccountingPeriod.fiscal_year_id == fiscal_year_id,
            Account.account_class.in_([6, 7])
        )
    )
    if fund_id:
        base_q = base_q.where(JournalLine.fund_id == fund_id)
    if project_id:
        base_q = base_q.where(JournalLine.project_id == project_id)

    base_q = base_q.group_by(Account.code, Account.label, Account.account_class)
    results = db.execute(base_q).all()

    charges, produits = [], []
    total_charges, total_produits = Decimal("0"), Decimal("0")

    for row in results:
        net = (row.d or Decimal("0")) - (row.c or Decimal("0"))
        if row.account_class == 6:
            amt = net if net > 0 else Decimal("0")
            charges.append(StatementRow(account_code=row.code, account_label=row.label, amount=amt))
            total_charges += amt
        elif row.account_class == 7:
            amt = -net if net < 0 else Decimal("0")
            produits.append(StatementRow(account_code=row.code, account_label=row.label, amount=amt))
            total_produits += amt

    return CompteResultat(
        charges=charges, produits=produits,
        total_charges=total_charges, total_produits=total_produits,
        resultat=total_produits - total_charges
    )


def get_bilan(db: Session, fiscal_year_id: int) -> Bilan:
    base_q = (
        select(
            Account.code, Account.label, Account.account_class,
            func.sum(JournalLine.base_debit).label("d"),
            func.sum(JournalLine.base_credit).label("c")
        )
        .join(JournalLine, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(AccountingPeriod, JournalEntry.period_id == AccountingPeriod.id)
        .where(
            JournalEntry.status == EntryStatus.POSTED,
            AccountingPeriod.fiscal_year_id == fiscal_year_id,
            Account.account_class.in_([1, 2, 3, 4, 5])
        )
        .group_by(Account.code, Account.label, Account.account_class)
    )
    results = db.execute(base_q).all()

    actif, passif = [], []
    total_actif, total_passif = Decimal("0"), Decimal("0")

    for row in results:
        net = (row.d or Decimal("0")) - (row.c or Decimal("0"))

        # Class 2 and 3 balances stay in Actif even when credit (contra-asset).
        if row.account_class in (2, 3):
            actif.append(BilanRow(account_code=row.code, account_label=row.label, amount=net))
            total_actif += net
        elif row.account_class in (4, 5):
            if net >= 0:
                actif.append(BilanRow(account_code=row.code, account_label=row.label, amount=net))
                total_actif += net
            else:
                passif.append(BilanRow(account_code=row.code, account_label=row.label, amount=-net))
                total_passif += -net
        elif row.account_class == 1:
            passif.append(BilanRow(account_code=row.code, account_label=row.label, amount=-net))
            total_passif += -net

    # Include current year result in Passif so the Bilan balances.
    cr = get_compte_de_resultat(db, fiscal_year_id)
    if cr.resultat != 0:
        passif.append(
            BilanRow(
                account_code="RÉSULTAT",
                account_label="Résultat de l'exercice",
                amount=cr.resultat,
            )
        )
        total_passif += cr.resultat

    return Bilan(actif=actif, passif=passif, total_actif=total_actif, total_passif=total_passif)


def get_aged_balance(db: Session, is_payable: bool = True) -> list[AgedBalanceRow]:
    account_prefix = "40" if is_payable else "41"
    today = date.today()

    q = (
        select(
            ThirdParty.name,
            JournalEntry.entry_date,
            func.sum(JournalLine.base_debit).label("d"),
            func.sum(JournalLine.base_credit).label("c")
        )
        .join(JournalLine, ThirdParty.id == JournalLine.third_party_id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
        .where(
            JournalEntry.status == EntryStatus.POSTED,
            Account.code.like(f"{account_prefix}%")
        )
        .group_by(ThirdParty.name, JournalEntry.entry_date)
    )
    results = db.execute(q).all()

    tp_data = {}
    for row in results:
        name = row.name
        if name not in tp_data:
            tp_data[name] = {"0_30": Decimal("0"), "31_60": Decimal("0"), "61_90": Decimal("0"),
                             "over_90": Decimal("0")}

        # For payables, balance is Credit - Debit. For receivables, Debit - Credit.
        balance = (row.c or Decimal("0")) - (row.d or Decimal("0")) if is_payable else (row.d or Decimal("0")) - (
                    row.c or Decimal("0"))
        if balance <= 0:
            continue

        age_days = (today - row.entry_date).days
        if age_days <= 30:
            tp_data[name]["0_30"] += balance
        elif age_days <= 60:
            tp_data[name]["31_60"] += balance
        elif age_days <= 90:
            tp_data[name]["61_90"] += balance
        else:
            tp_data[name]["over_90"] += balance

    rows = []
    for name, buckets in tp_data.items():
        total = buckets["0_30"] + buckets["31_60"] + buckets["61_90"] + buckets["over_90"]
        rows.append(AgedBalanceRow(
            third_party_name=name,
            bucket_0_30=buckets["0_30"],
            bucket_31_60=buckets["31_60"],
            bucket_61_90=buckets["61_90"],
            bucket_over_90=buckets["over_90"],
            total=total
        ))
    return rows