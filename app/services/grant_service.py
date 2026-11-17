from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import func, select
from pydantic import BaseModel, Field

from app.models.grants import DonorGrant, GrantTranche, FundCall, GrantReceipt
from app.models.account import Account
from app.models.master_data import ThirdParty, Fund, AccountingJournal
from app.models.period import FiscalYear
from app.models.enums import EntryStatus, GrantStatus, TrancheStatus
from app.models.settings import OrganizationSetting
from app.services.accrual_service import resolve_open_period
from app.services.ledger_service import (
    create_and_validate_entry, post_journal_entry,
    JournalEntryCreateSchema, JournalLineSchema,
)

ZERO = Decimal("0")
ONE = Decimal("1")


def _q0(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q6(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ SCHEMAS


class GrantCreateSchema(BaseModel):
    code: str
    label: str
    donor_third_party_id: int
    fund_id: int
    currency_code: str = "XAF"
    total_committed_foreign: Decimal = Field(default=Decimal("0.00"), max_digits=18, decimal_places=2)
    start_date: date
    end_date: date
    fund_account_code: str = "1611"
    receivable_account_code: str = "411"


class TrancheCreateSchema(BaseModel):
    tranche_number: int
    expected_date: date
    foreign_amount: Decimal = Field(max_digits=18, decimal_places=2)
    exchange_rate: Decimal = Field(default=ONE, max_digits=18, decimal_places=6)


class FundCallCreateSchema(BaseModel):
    grant_id: int
    tranche_id: int | None = None
    call_date: date
    due_date: date
    reference: str
    description: str
    foreign_amount: Decimal = Field(max_digits=18, decimal_places=2)
    exchange_rate: Decimal = Field(default=ONE, max_digits=18, decimal_places=6)


class GrantReceiptCreateSchema(BaseModel):
    fund_call_id: int
    receipt_date: date
    journal_code: str
    treasury_account_code: str
    reference: str
    description: str
    foreign_amount: Decimal = Field(max_digits=18, decimal_places=2)
    exchange_rate: Decimal = Field(default=ONE, max_digits=18, decimal_places=6)


# ------------------------------------------------------------------ WEIGHTED RATE


def get_grant_weighted_rate(db: Session, grant_id: int) -> Decimal:
    """
    Weighted average rate of called/received tranches.
    Falls back to the first planned tranche rate, then 1.
    """
    rows = db.execute(
        select(GrantTranche.foreign_amount, GrantTranche.exchange_rate)
        .where(
            GrantTranche.grant_id == grant_id,
            GrantTranche.status.in_([TrancheStatus.CALLED, TrancheStatus.RECEIVED]),
        )
    ).all()

    total_foreign = sum((r.foreign_amount for r in rows), Decimal("0.00"))
    if total_foreign > ZERO:
        total_base = sum((r.foreign_amount * r.exchange_rate for r in rows), ZERO)
        return _q6(total_base / total_foreign)

    first = (
        db.query(GrantTranche)
        .filter(GrantTranche.grant_id == grant_id)
        .order_by(GrantTranche.tranche_number)
        .first()
    )
    return _q6(Decimal(first.exchange_rate)) if first else ONE


# ------------------------------------------------------------------ GRANTS


def create_grant(db: Session, user_id: int, data: GrantCreateSchema) -> DonorGrant:
    settings = db.query(OrganizationSetting).first()

    if data.end_date < data.start_date:
        raise ValueError("Grant end date cannot precede start date.")
    if data.total_committed_foreign < ZERO:
        raise ValueError("Committed amount cannot be negative.")
    if data.currency_code != "XAF" and not (settings and settings.multi_currency_enabled):
        raise ValueError("Multi-currency is not enabled in organization settings.")
    if not (settings and settings.donor_fund_tracking_enabled):
        raise ValueError("Donor fund tracking is not enabled in organization settings.")

    donor = db.get(ThirdParty, data.donor_third_party_id)
    if not donor:
        raise ValueError("Donor (Third Party) not found.")

    fund = db.get(Fund, data.fund_id)
    if not fund:
        raise ValueError("Fund not found.")
    if not fund.is_restricted:
        raise ValueError("Grant fund must be a restricted fund.")
    if fund.currency_code != data.currency_code:
        raise ValueError("Grant currency must match the fund currency.")

    fund_account = db.query(Account).filter(Account.code == data.fund_account_code).first()
    if not fund_account or fund_account.account_class != 1 or not fund_account.is_postable:
        raise ValueError("Restricted fund account must be a postable Class 1 account.")

    receivable = db.query(Account).filter(Account.code == data.receivable_account_code).first()
    if not receivable or not receivable.is_postable or not receivable.requires_third_party:
        raise ValueError("Receivable account must be a postable account requiring a Third Party.")

    grant = DonorGrant(
        code=data.code.strip(),
        label=data.label.strip(),
        donor_third_party_id=data.donor_third_party_id,
        fund_id=data.fund_id,
        currency_code=data.currency_code,
        total_committed_foreign=_q2(data.total_committed_foreign),
        start_date=data.start_date,
        end_date=data.end_date,
        fund_account_id=fund_account.id,
        receivable_account_id=receivable.id,
        status=GrantStatus.DRAFT,
        created_by_id=user_id,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def add_tranche(db: Session, grant_id: int, data: TrancheCreateSchema) -> GrantTranche:
    grant = db.get(DonorGrant, grant_id)
    if not grant:
        raise ValueError("Grant not found.")
    if data.foreign_amount <= ZERO:
        raise ValueError("Tranche amount must be positive.")
    if data.exchange_rate <= ZERO:
        raise ValueError("Exchange rate must be greater than zero.")
    if data.tranche_number <= 0:
        raise ValueError("Tranche number must be positive.")

    exists = (
        db.query(GrantTranche)
        .filter(GrantTranche.grant_id == grant_id, GrantTranche.tranche_number == data.tranche_number)
        .first()
    )
    if exists:
        raise ValueError("This tranche number already exists for the grant.")

    tranche = GrantTranche(
        grant_id=grant_id,
        tranche_number=data.tranche_number,
        expected_date=data.expected_date,
        foreign_amount=_q2(data.foreign_amount),
        exchange_rate=data.exchange_rate,
        status=TrancheStatus.PLANNED,
    )
    db.add(tranche)
    db.commit()
    db.refresh(tranche)
    return tranche


def activate_grant(db: Session, grant_id: int) -> DonorGrant:
    grant = db.get(DonorGrant, grant_id)
    if not grant:
        raise ValueError("Grant not found.")
    if grant.status == GrantStatus.ACTIVE:
        return grant
    count = db.query(GrantTranche).filter(GrantTranche.grant_id == grant_id).count()
    if count == 0:
        raise ValueError("Grant requires at least one tranche before activation.")
    grant.status = GrantStatus.ACTIVE
    db.commit()
    db.refresh(grant)
    return grant


# ------------------------------------------------------------------ FUND CALLS


def create_fund_call(db: Session, user_id: int, data: FundCallCreateSchema) -> FundCall:
    grant = db.get(DonorGrant, data.grant_id)
    if not grant:
        raise ValueError("Grant not found.")
    if grant.status != GrantStatus.ACTIVE:
        raise ValueError("Grant must be ACTIVE before issuing a fund call.")
    if data.foreign_amount <= ZERO:
        raise ValueError("Fund call amount must be positive.")
    if data.exchange_rate <= ZERO:
        raise ValueError("Exchange rate must be greater than zero.")
    if data.due_date < data.call_date:
        raise ValueError("Due date cannot precede call date.")

    resolve_open_period(db, data.call_date)

    tranche = None
    if data.tranche_id:
        tranche = db.get(GrantTranche, data.tranche_id)
        if not tranche or tranche.grant_id != grant.id:
            raise ValueError("Tranche does not belong to this grant.")
        if tranche.status != TrancheStatus.PLANNED:
            raise ValueError("Only PLANNED tranches can be called.")
        if data.foreign_amount > Decimal(tranche.foreign_amount):
            raise ValueError("Fund call cannot exceed the tranche amount.")

    call = FundCall(
        grant_id=grant.id,
        tranche_id=tranche.id if tranche else None,
        call_date=data.call_date,
        due_date=data.due_date,
        reference=data.reference.strip(),
        description=data.description.strip(),
        foreign_amount=_q2(data.foreign_amount),
        exchange_rate=data.exchange_rate,
        base_amount=_q0(data.foreign_amount * data.exchange_rate),
        status=EntryStatus.DRAFT,
        created_by_id=user_id,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return call


def post_fund_call(db: Session, call_id: int, approver_id: int) -> FundCall:
    call = db.query(FundCall).filter(FundCall.id == call_id).with_for_update().first()
    if not call:
        raise ValueError("Fund call not found.")
    if call.status != EntryStatus.DRAFT:
        raise ValueError("Fund call must be in DRAFT status to post.")

    grant = db.get(DonorGrant, call.grant_id)
    period = resolve_open_period(db, call.call_date)
    fiscal_year = db.get(FiscalYear, period.fiscal_year_id)

    journal = db.query(AccountingJournal).filter(AccountingJournal.code == "SUB").first()
    if not journal:
        raise ValueError("Grant journal 'SUB' is missing. Run migrations.")

    receivable = db.get(Account, grant.receivable_account_id)
    fund_account = db.get(Account, grant.fund_account_id)
    settings = db.query(OrganizationSetting).first()
    fund_id = grant.fund_id if settings and settings.donor_fund_tracking_enabled else None

    amount = Decimal(call.base_amount)

    entry_data = JournalEntryCreateSchema(
        journal_code=journal.code,
        fiscal_year_code=fiscal_year.code,
        period_id=period.id,
        entry_date=call.call_date,
        reference=call.reference,
        description=f"Appel de fonds — {grant.code} — {call.description}",
        lines=[
            JournalLineSchema(
                account_code=receivable.code,
                third_party_id=grant.donor_third_party_id,
                fund_id=fund_id,
                currency_code=grant.currency_code,
                exchange_rate=Decimal(call.exchange_rate),
                foreign_debit=Decimal(call.foreign_amount),
                base_debit=amount,
                description="Créance bailleur",
            ),
            JournalLineSchema(
                account_code=fund_account.code,
                fund_id=fund_id,
                currency_code=grant.currency_code,
                exchange_rate=Decimal(call.exchange_rate),
                foreign_credit=Decimal(call.foreign_amount),
                base_credit=amount,
                description="Fonds dédiés",
            ),
        ],
    )

    entry = create_and_validate_entry(db, approver_id, entry_data)
    posted = post_journal_entry(db, entry.id, approver_id)

    call.status = EntryStatus.POSTED
    call.journal_entry_id = posted.id
    call.period_id = period.id

    if call.tranche_id:
        tranche = db.get(GrantTranche, call.tranche_id)
        tranche.status = TrancheStatus.CALLED

    db.commit()
    db.refresh(call)
    return call


def get_call_outstanding(db: Session, call: FundCall) -> dict:
    received = db.execute(
        select(func.coalesce(func.sum(GrantReceipt.receivable_cleared_base), 0))
        .where(
            GrantReceipt.fund_call_id == call.id,
            GrantReceipt.status == EntryStatus.POSTED,
        )
    ).scalar()
    received = Decimal(received) if received else ZERO

    outstanding_base = Decimal(call.base_amount) - received
    rate = Decimal(call.exchange_rate) or ONE

    return {
        "received_base": received,
        "outstanding_base": outstanding_base,
        "outstanding_foreign": _q2(outstanding_base / rate),
        "payment_status": "RECEIVED" if outstanding_base <= ZERO else ("PARTIALLY_RECEIVED" if received > ZERO else "PENDING"),
    }


# ------------------------------------------------------------------ RECEIPTS


def create_grant_receipt(db: Session, user_id: int, data: GrantReceiptCreateSchema) -> GrantReceipt:
    call = db.get(FundCall, data.fund_call_id)
    if not call:
        raise ValueError("Fund call not found.")
    if call.status != EntryStatus.POSTED:
        raise ValueError("Only POSTED fund calls can be received.")
    if data.foreign_amount <= ZERO:
        raise ValueError("Receipt amount must be positive.")
    if data.exchange_rate <= ZERO:
        raise ValueError("Exchange rate must be greater than zero.")

    treasury = db.query(Account).filter(Account.code == data.treasury_account_code).first()
    if not treasury or treasury.account_class != 5 or not treasury.is_postable:
        raise ValueError("Treasury account must be a postable Class 5 account.")

    journal = db.query(AccountingJournal).filter(AccountingJournal.code == data.journal_code).first()
    if not journal:
        raise ValueError("Selected journal does not exist.")

    resolve_open_period(db, data.receipt_date)

    outstanding = get_call_outstanding(db, call)
    receivable_cleared = _q0(data.foreign_amount * Decimal(call.exchange_rate))
    if receivable_cleared > outstanding["outstanding_base"]:
        raise ValueError(
            f"Receipt exceeds outstanding fund call {call.reference}. "
            f"Outstanding: {outstanding['outstanding_base']}"
        )

    cash = _q0(data.foreign_amount * data.exchange_rate)

    receipt = GrantReceipt(
        fund_call_id=call.id,
        receipt_date=data.receipt_date,
        journal_code=data.journal_code,
        treasury_account_id=treasury.id,
        reference=data.reference.strip(),
        description=data.description.strip(),
        foreign_amount=_q2(data.foreign_amount),
        exchange_rate=data.exchange_rate,
        base_amount=cash,
        receivable_cleared_base=receivable_cleared,
        fx_gain_loss_base=cash - receivable_cleared,
        status=EntryStatus.DRAFT,
        created_by_id=user_id,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


def post_grant_receipt(db: Session, receipt_id: int, approver_id: int) -> GrantReceipt:
    receipt = db.query(GrantReceipt).filter(GrantReceipt.id == receipt_id).with_for_update().first()
    if not receipt:
        raise ValueError("Receipt not found.")
    if receipt.status != EntryStatus.DRAFT:
        raise ValueError("Receipt must be in DRAFT status to post.")

    call = db.get(FundCall, receipt.fund_call_id)
    grant = db.get(DonorGrant, call.grant_id)
    period = resolve_open_period(db, receipt.receipt_date)
    fiscal_year = db.get(FiscalYear, period.fiscal_year_id)

    receivable = db.get(Account, grant.receivable_account_id)
    treasury = db.get(Account, receipt.treasury_account_id)
    settings = db.query(OrganizationSetting).first()
    fund_id = grant.fund_id if settings and settings.donor_fund_tracking_enabled else None

    cash = Decimal(receipt.base_amount)
    cleared = Decimal(receipt.receivable_cleared_base)
    fx = Decimal(receipt.fx_gain_loss_base)

    lines = [
        JournalLineSchema(
            account_code=treasury.code,
            fund_id=fund_id,
            currency_code=grant.currency_code,
            exchange_rate=Decimal(receipt.exchange_rate),
            foreign_debit=Decimal(receipt.foreign_amount),
            base_debit=cash,
            description="Encaissement subvention",
        ),
        JournalLineSchema(
            account_code=receivable.code,
            third_party_id=grant.donor_third_party_id,
            fund_id=fund_id,
            currency_code=grant.currency_code,
            exchange_rate=Decimal(call.exchange_rate),
            foreign_credit=Decimal(receipt.foreign_amount),
            base_credit=cleared,
            description=f"Apurement créance {call.reference}",
        ),
    ]

    if fx > ZERO:
        gain = db.query(Account).filter(Account.code == "776").first()
        if not gain:
            raise ValueError("FX gain account 776 is missing.")
        lines.append(JournalLineSchema(
            account_code=gain.code, currency_code="XAF", exchange_rate=ONE,
            foreign_credit=_q2(fx), base_credit=_q0(fx),
            description="Gain de change réalisé",
        ))
    elif fx < ZERO:
        loss = db.query(Account).filter(Account.code == "676").first()
        if not loss:
            raise ValueError("FX loss account 676 is missing.")
        lines.append(JournalLineSchema(
            account_code=loss.code, currency_code="XAF", exchange_rate=ONE,
            foreign_debit=_q2(-fx), base_debit=_q0(-fx),
            description="Perte de change réalisée",
        ))

    entry_data = JournalEntryCreateSchema(
        journal_code=receipt.journal_code,
        fiscal_year_code=fiscal_year.code,
        period_id=period.id,
        entry_date=receipt.receipt_date,
        reference=receipt.reference,
        description=f"Encaissement subvention — {grant.code}",
        lines=lines,
    )

    entry = create_and_validate_entry(db, approver_id, entry_data)
    posted = post_journal_entry(db, entry.id, approver_id)

    receipt.status = EntryStatus.POSTED
    receipt.journal_entry_id = posted.id
    receipt.period_id = period.id

    # NOTE: receipt.status is already POSTED in this session, so get_call_outstanding
    # already accounts for it. Do NOT subtract `cleared` a second time.
    outstanding = get_call_outstanding(db, call)
    if outstanding["outstanding_base"] <= ZERO and call.tranche_id:
        tranche = db.get(GrantTranche, call.tranche_id)
        tranche.status = TrancheStatus.RECEIVED

    db.commit()
    db.refresh(receipt)
    return receipt


# ------------------------------------------------------------------ QUERIES


def get_grant_detail(db: Session, grant_id: int) -> dict | None:
    grant = db.get(DonorGrant, grant_id)
    if not grant:
        return None

    tranches = (
        db.query(GrantTranche)
        .filter(GrantTranche.grant_id == grant_id)
        .order_by(GrantTranche.tranche_number)
        .all()
    )
    calls = db.query(FundCall).filter(FundCall.grant_id == grant_id).order_by(FundCall.call_date).all()

    call_rows = []
    for call in calls:
        receipts = db.query(GrantReceipt).filter(GrantReceipt.fund_call_id == call.id).all()
        call_rows.append({
            "call": call,
            "outstanding": get_call_outstanding(db, call),
            "receipts": receipts,
        })

    called_foreign = sum(
        (Decimal(c.foreign_amount) for c in calls if c.status == EntryStatus.POSTED), Decimal("0.00")
    )

    return {
        "grant": grant,
        "donor": db.get(ThirdParty, grant.donor_third_party_id),
        "fund": db.get(Fund, grant.fund_id),
        "fund_account": db.get(Account, grant.fund_account_id),
        "receivable_account": db.get(Account, grant.receivable_account_id),
        "tranches": tranches,
        "call_rows": call_rows,
        "weighted_rate": get_grant_weighted_rate(db, grant_id),
        "called_foreign": called_foreign,
        "uncalled_foreign": Decimal(grant.total_committed_foreign) - called_foreign,
    }