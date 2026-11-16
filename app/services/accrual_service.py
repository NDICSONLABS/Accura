from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import func, select
from pydantic import BaseModel, Field

from app.models.accruals import (
    SupplierBill, SupplierBillLine, TreasurySettlement, SettlementAllocation,
)
from app.models.account import Account
from app.models.master_data import ThirdParty, AccountingJournal
from app.models.period import AccountingPeriod, FiscalYear
from app.models.enums import EntryStatus, PeriodStatus, FiscalYearStatus
from app.models.settings import OrganizationSetting
from app.services.ledger_service import (
    create_and_validate_entry, post_journal_entry,
    JournalEntryCreateSchema, JournalLineSchema,
)

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")


def _q0(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ SCHEMAS


class BillLineSchema(BaseModel):
    account_code: str
    base_amount: Decimal = Field(default=ZERO, max_digits=18, decimal_places=0)
    vat_amount: Decimal = Field(default=ZERO, max_digits=18, decimal_places=0)
    vat_deductible: bool = False
    description: str | None = None
    project_id: int | None = None
    fund_id: int | None = None
    budget_line_id: int | None = None


class SupplierBillCreateSchema(BaseModel):
    third_party_id: int
    bill_date: date
    due_date: date
    reference: str
    description: str
    currency_code: str = "XAF"
    exchange_rate: Decimal = Field(default=Decimal("1.000000"), max_digits=18, decimal_places=6)
    withholding_tax_base: Decimal = Field(default=ZERO, max_digits=18, decimal_places=0)
    vat_account_code: str | None = None
    lines: list[BillLineSchema]


class SettlementAllocationSchema(BaseModel):
    bill_id: int
    allocated_foreign_amount: Decimal = Field(default=Decimal("0.00"), max_digits=18, decimal_places=2)


class SettlementCreateSchema(BaseModel):
    third_party_id: int
    settlement_date: date
    journal_code: str
    treasury_account_code: str
    reference: str
    description: str
    currency_code: str = "XAF"
    exchange_rate: Decimal = Field(default=Decimal("1.000000"), max_digits=18, decimal_places=6)
    allocations: list[SettlementAllocationSchema]


# ------------------------------------------------------------------ HELPERS


def resolve_open_period(db: Session, on_date: date) -> AccountingPeriod:
    period = (
        db.query(AccountingPeriod)
        .join(FiscalYear, AccountingPeriod.fiscal_year_id == FiscalYear.id)
        .filter(
            AccountingPeriod.start_date <= on_date,
            AccountingPeriod.end_date >= on_date,
            AccountingPeriod.status == PeriodStatus.OPEN,
            FiscalYear.status == FiscalYearStatus.OPEN,
        )
        .order_by(AccountingPeriod.start_date)
        .first()
    )
    if not period:
        raise ValueError("No OPEN accounting period found for this date.")
    return period


def _line_expense_amount(line: SupplierBillLine) -> Decimal:
    """Non-deductible VAT is capitalized into the expense/asset cost."""
    base = Decimal(line.base_amount)
    if not line.vat_deductible:
        base += Decimal(line.vat_amount)
    return base


def get_bill_totals(db: Session, bill: SupplierBill) -> dict:
    lines = db.query(SupplierBillLine).filter(SupplierBillLine.bill_id == bill.id).all()

    expense_total = sum((_line_expense_amount(l) for l in lines), ZERO)
    deductible_vat = Decimal(bill.deductible_vat_base or ZERO)
    wht = Decimal(bill.withholding_tax_base or ZERO)
    net_payable = expense_total + deductible_vat - wht

    paid = db.execute(
        select(func.coalesce(func.sum(SettlementAllocation.allocated_base_amount), 0))
        .join(TreasurySettlement, SettlementAllocation.settlement_id == TreasurySettlement.id)
        .where(
            SettlementAllocation.bill_id == bill.id,
            TreasurySettlement.status == EntryStatus.POSTED,
        )
    ).scalar()
    paid = Decimal(paid) if paid else ZERO

    outstanding = net_payable - paid
    rate = Decimal(bill.exchange_rate) or ONE

    if outstanding <= ZERO:
        payment_status = "PAID"
    elif paid > ZERO:
        payment_status = "PARTIALLY_PAID"
    else:
        payment_status = "UNPAID"

    return {
        "expense_total": expense_total,
        "deductible_vat": deductible_vat,
        "withholding_tax": wht,
        "net_payable": net_payable,
        "paid": paid,
        "outstanding": outstanding,
        "outstanding_foreign": _q2(outstanding / rate),
        "payment_status": payment_status,
        "lines": lines,
    }


def list_open_bills(db: Session, third_party_id: int) -> list[dict]:
    bills = (
        db.query(SupplierBill)
        .filter(
            SupplierBill.third_party_id == third_party_id,
            SupplierBill.status == EntryStatus.POSTED,
        )
        .order_by(SupplierBill.due_date, SupplierBill.id)
        .all()
    )

    result = []
    for bill in bills:
        totals = get_bill_totals(db, bill)
        if totals["outstanding"] > ZERO:
            result.append({
                "id": bill.id,
                "reference": bill.reference,
                "bill_date": bill.bill_date.isoformat(),
                "due_date": bill.due_date.isoformat(),
                "currency_code": bill.currency_code,
                "exchange_rate": str(bill.exchange_rate),
                "outstanding_base": str(totals["outstanding"]),
                "outstanding_foreign": str(totals["outstanding_foreign"]),
                "payment_status": totals["payment_status"],
            })
    return result


# ------------------------------------------------------------------ BILLS


def create_supplier_bill(db: Session, user_id: int, data: SupplierBillCreateSchema) -> SupplierBill:
    settings = db.query(OrganizationSetting).first()

    third_party = db.get(ThirdParty, data.third_party_id)
    if not third_party:
        raise ValueError("Supplier (Third Party) not found.")

    control_account = db.get(Account, third_party.account_id)
    if not control_account or control_account.account_class != 4:
        raise ValueError("Supplier must be linked to a Class 4 control account.")

    if data.due_date < data.bill_date:
        raise ValueError("Due date cannot precede bill date.")
    if data.exchange_rate <= ZERO:
        raise ValueError("Exchange rate must be greater than zero.")
    if data.currency_code != "XAF" and not (settings and settings.multi_currency_enabled):
        raise ValueError("Multi-currency is not enabled in organization settings.")
    if data.withholding_tax_base > ZERO and not (settings and settings.tax_withholding_enabled):
        raise ValueError("Withholding tax is not enabled in organization settings.")
    if not data.lines:
        raise ValueError("At least one bill line is required.")

    resolve_open_period(db, data.bill_date)

    vat_account = None
    if data.vat_account_code:
        vat_account = db.query(Account).filter(Account.code == data.vat_account_code).first()
        if not vat_account or not vat_account.is_postable:
            raise ValueError("VAT account is invalid or not postable.")

    deductible_total = ZERO
    prepared: list[tuple[BillLineSchema, Account]] = []

    for line in data.lines:
        account = db.query(Account).filter(Account.code == line.account_code).first()
        if not account or not account.is_postable or not account.is_active:
            raise ValueError(f"Account {line.account_code} is invalid or not postable.")
        if line.base_amount <= ZERO:
            raise ValueError("Each bill line must have a positive net amount.")
        if line.vat_amount < ZERO:
            raise ValueError("VAT amount cannot be negative.")
        if line.vat_deductible and line.vat_amount > ZERO:
            if not vat_account:
                raise ValueError("Deductible VAT requires a VAT account.")
            deductible_total += line.vat_amount
        prepared.append((line, account))

    expense_total = sum(
        (l.base_amount + (ZERO if l.vat_deductible else l.vat_amount) for l, _ in prepared),
        ZERO,
    )
    if data.withholding_tax_base > expense_total + deductible_total:
        raise ValueError("Withholding tax cannot exceed total bill amount.")

    bill = SupplierBill(
        third_party_id=data.third_party_id,
        bill_date=data.bill_date,
        due_date=data.due_date,
        reference=data.reference.strip(),
        description=data.description.strip(),
        currency_code=data.currency_code,
        exchange_rate=data.exchange_rate,
        withholding_tax_base=_q0(data.withholding_tax_base),
        deductible_vat_base=_q0(deductible_total),
        vat_account_id=vat_account.id if vat_account else None,
        status=EntryStatus.DRAFT,
        created_by_id=user_id,
    )
    db.add(bill)
    db.flush()

    rate = data.exchange_rate or ONE
    for line, account in prepared:
        db.add(SupplierBillLine(
            bill_id=bill.id,
            account_id=account.id,
            project_id=line.project_id if settings and settings.project_cost_center_enabled else None,
            fund_id=line.fund_id if settings and settings.donor_fund_tracking_enabled else None,
            budget_line_id=line.budget_line_id if settings and settings.budget_control_enabled else None,
            description=line.description,
            base_amount=_q0(line.base_amount),
            vat_amount=_q0(line.vat_amount),
            vat_deductible=line.vat_deductible,
            is_vat_capitalized=(not line.vat_deductible and line.vat_amount > ZERO),
            foreign_amount=_q2(line.base_amount / rate),
        ))

    db.commit()
    db.refresh(bill)
    return bill


def build_bill_journal_lines(db: Session, bill: SupplierBill) -> list[JournalLineSchema]:
    totals = get_bill_totals(db, bill)
    third_party = db.get(ThirdParty, bill.third_party_id)
    control_account = db.get(Account, third_party.account_id)
    rate = Decimal(bill.exchange_rate) or ONE

    result: list[JournalLineSchema] = []

    for line in totals["lines"]:
        account = db.get(Account, line.account_id)
        amount = _line_expense_amount(line)
        result.append(JournalLineSchema(
            account_code=account.code,
            third_party_id=bill.third_party_id if account.account_class == 4 else None,
            fund_id=line.fund_id,
            project_id=line.project_id,
            budget_line_id=line.budget_line_id,
            currency_code=bill.currency_code,
            exchange_rate=rate,
            foreign_debit=_q2(amount / rate),
            base_debit=_q0(amount),
            description=line.description or bill.description,
        ))

    if totals["deductible_vat"] > ZERO:
        vat_account = db.get(Account, bill.vat_account_id)
        result.append(JournalLineSchema(
            account_code=vat_account.code,
            third_party_id=bill.third_party_id,
            currency_code="XAF",
            exchange_rate=ONE,
            foreign_debit=_q2(totals["deductible_vat"]),
            base_debit=_q0(totals["deductible_vat"]),
            description="TVA récupérable",
        ))

    result.append(JournalLineSchema(
        account_code=control_account.code,
        third_party_id=bill.third_party_id,
        currency_code=bill.currency_code,
        exchange_rate=rate,
        foreign_credit=_q2(totals["net_payable"] / rate),
        base_credit=_q0(totals["net_payable"]),
        description=f"Net payable — {third_party.name}",
    ))

    if totals["withholding_tax"] > ZERO:
        wht_account = db.query(Account).filter(Account.code == "447").first()
        if not wht_account:
            raise ValueError("Withholding tax account 447 is missing.")
        result.append(JournalLineSchema(
            account_code=wht_account.code,
            third_party_id=bill.third_party_id,
            currency_code="XAF",
            exchange_rate=ONE,
            foreign_credit=_q2(totals["withholding_tax"]),
            base_credit=_q0(totals["withholding_tax"]),
            description="Retenue à la source",
        ))

    return result


def post_supplier_bill(db: Session, bill_id: int, approver_id: int) -> SupplierBill:
    bill = db.query(SupplierBill).filter(SupplierBill.id == bill_id).with_for_update().first()
    if not bill:
        raise ValueError("Bill not found.")
    if bill.status != EntryStatus.DRAFT:
        raise ValueError("Bill must be in DRAFT status to post.")

    period = resolve_open_period(db, bill.bill_date)
    fiscal_year = db.get(FiscalYear, period.fiscal_year_id)
    journal = db.query(AccountingJournal).filter(AccountingJournal.code == "ACH").first()
    if not journal:
        raise ValueError("Purchase journal 'ACH' is missing. Run migrations.")

    entry_data = JournalEntryCreateSchema(
        journal_code=journal.code,
        fiscal_year_code=fiscal_year.code,
        period_id=period.id,
        entry_date=bill.bill_date,
        reference=bill.reference,
        description=f"Facture fournisseur — {bill.description}",
        lines=build_bill_journal_lines(db, bill),
    )

    entry = create_and_validate_entry(db, approver_id, entry_data)
    posted = post_journal_entry(db, entry.id, approver_id)

    bill.status = EntryStatus.POSTED
    bill.journal_entry_id = posted.id
    bill.period_id = period.id
    db.commit()
    db.refresh(bill)
    return bill


# ------------------------------------------------------------------ SETTLEMENTS


def create_settlement(db: Session, user_id: int, data: SettlementCreateSchema) -> TreasurySettlement:
    settings = db.query(OrganizationSetting).first()

    third_party = db.get(ThirdParty, data.third_party_id)
    if not third_party:
        raise ValueError("Supplier (Third Party) not found.")

    treasury = db.query(Account).filter(Account.code == data.treasury_account_code).first()
    if not treasury or treasury.account_class != 5 or not treasury.is_postable:
        raise ValueError("Treasury account must be a postable Class 5 account.")

    journal = db.query(AccountingJournal).filter(AccountingJournal.code == data.journal_code).first()
    if not journal:
        raise ValueError("Selected journal does not exist.")

    if data.exchange_rate <= ZERO:
        raise ValueError("Exchange rate must be greater than zero.")
    if data.currency_code != "XAF" and not (settings and settings.multi_currency_enabled):
        raise ValueError("Multi-currency is not enabled in organization settings.")
    if not data.allocations:
        raise ValueError("At least one bill allocation is required.")

    resolve_open_period(db, data.settlement_date)

    settlement = TreasurySettlement(
        settlement_date=data.settlement_date,
        journal_code=data.journal_code,
        reference=data.reference.strip(),
        description=data.description.strip(),
        third_party_id=data.third_party_id,
        treasury_account_id=treasury.id,
        currency_code=data.currency_code,
        exchange_rate=data.exchange_rate,
        status=EntryStatus.DRAFT,
        created_by_id=user_id,
    )
    db.add(settlement)
    db.flush()

    total_cash = ZERO
    total_fx = ZERO
    allocated_count = 0

    for alloc in data.allocations:
        if alloc.allocated_foreign_amount <= ZERO:
            continue

        bill = db.get(SupplierBill, alloc.bill_id)
        if not bill or bill.third_party_id != data.third_party_id:
            raise ValueError("Allocated bill does not belong to this supplier.")
        if bill.status != EntryStatus.POSTED:
            raise ValueError("Only POSTED bills can be settled.")
        if bill.currency_code != data.currency_code:
            raise ValueError("Settlement currency must match the currency of all allocated bills.")

        totals = get_bill_totals(db, bill)
        bill_rate = Decimal(bill.exchange_rate) or ONE

        liability_cleared = _q0(alloc.allocated_foreign_amount * bill_rate)
        cash_paid = _q0(alloc.allocated_foreign_amount * data.exchange_rate)

        if liability_cleared > totals["outstanding"]:
            raise ValueError(
                f"Allocation exceeds outstanding balance on bill {bill.reference}. "
                f"Outstanding: {totals['outstanding']}"
            )

        fx = liability_cleared - cash_paid

        db.add(SettlementAllocation(
            settlement_id=settlement.id,
            bill_id=bill.id,
            allocated_foreign_amount=_q2(alloc.allocated_foreign_amount),
            allocated_base_amount=liability_cleared,
            cash_base_amount=cash_paid,
            fx_gain_loss_base=fx,
        ))

        total_cash += cash_paid
        total_fx += fx
        allocated_count += 1

    if allocated_count == 0:
        raise ValueError("At least one non-zero bill allocation is required.")

    settlement.total_base_amount = total_cash
    settlement.fx_gain_loss_base = total_fx
    db.commit()
    db.refresh(settlement)
    return settlement


def post_settlement(db: Session, settlement_id: int, approver_id: int) -> TreasurySettlement:
    settlement = (
        db.query(TreasurySettlement)
        .filter(TreasurySettlement.id == settlement_id)
        .with_for_update()
        .first()
    )
    if not settlement:
        raise ValueError("Settlement not found.")
    if settlement.status != EntryStatus.DRAFT:
        raise ValueError("Settlement must be in DRAFT status to post.")

    period = resolve_open_period(db, settlement.settlement_date)
    fiscal_year = db.get(FiscalYear, period.fiscal_year_id)

    allocations = (
        db.query(SettlementAllocation)
        .filter(SettlementAllocation.settlement_id == settlement.id)
        .all()
    )
    if not allocations:
        raise ValueError("Settlement has no allocations.")

    third_party = db.get(ThirdParty, settlement.third_party_id)
    control_account = db.get(Account, third_party.account_id)
    treasury = db.get(Account, settlement.treasury_account_id)

    lines: list[JournalLineSchema] = []
    total_cash = ZERO
    total_foreign = Decimal("0.00")
    total_gain = ZERO
    total_loss = ZERO

    for alloc in allocations:
        bill = db.get(SupplierBill, alloc.bill_id)
        liability = Decimal(alloc.allocated_base_amount)
        cash = Decimal(alloc.cash_base_amount)
        fx = Decimal(alloc.fx_gain_loss_base)

        lines.append(JournalLineSchema(
            account_code=control_account.code,
            third_party_id=settlement.third_party_id,
            currency_code=bill.currency_code,
            exchange_rate=Decimal(bill.exchange_rate),
            foreign_debit=Decimal(alloc.allocated_foreign_amount),
            base_debit=liability,
            description=f"Règlement facture {bill.reference}",
        ))

        total_cash += cash
        total_foreign += Decimal(alloc.allocated_foreign_amount)
        if fx > ZERO:
            total_gain += fx
        elif fx < ZERO:
            total_loss += -fx

    lines.append(JournalLineSchema(
        account_code=treasury.code,
        currency_code=settlement.currency_code,
        exchange_rate=Decimal(settlement.exchange_rate),
        foreign_credit=_q2(total_foreign),
        base_credit=_q0(total_cash),
        description=settlement.description,
    ))

    if total_gain > ZERO:
        gain_account = db.query(Account).filter(Account.code == "776").first()
        if not gain_account:
            raise ValueError("FX gain account 776 is missing.")
        lines.append(JournalLineSchema(
            account_code=gain_account.code,
            currency_code="XAF",
            exchange_rate=ONE,
            foreign_credit=_q2(total_gain),
            base_credit=_q0(total_gain),
            description="Gain de change réalisé",
        ))

    if total_loss > ZERO:
        loss_account = db.query(Account).filter(Account.code == "676").first()
        if not loss_account:
            raise ValueError("FX loss account 676 is missing.")
        lines.append(JournalLineSchema(
            account_code=loss_account.code,
            currency_code="XAF",
            exchange_rate=ONE,
            foreign_debit=_q2(total_loss),
            base_debit=_q0(total_loss),
            description="Perte de change réalisée",
        ))

    entry_data = JournalEntryCreateSchema(
        journal_code=settlement.journal_code,
        fiscal_year_code=fiscal_year.code,
        period_id=period.id,
        entry_date=settlement.settlement_date,
        reference=settlement.reference,
        description=f"Règlement fournisseur — {settlement.description}",
        lines=lines,
    )

    entry = create_and_validate_entry(db, approver_id, entry_data)
    posted = post_journal_entry(db, entry.id, approver_id)

    settlement.status = EntryStatus.POSTED
    settlement.journal_entry_id = posted.id
    settlement.period_id = period.id
    db.commit()
    db.refresh(settlement)
    return settlement


def get_settlement_detail(db: Session, settlement_id: int) -> dict | None:
    settlement = db.get(TreasurySettlement, settlement_id)
    if not settlement:
        return None

    allocations = (
        db.query(SettlementAllocation, SupplierBill)
        .join(SupplierBill, SettlementAllocation.bill_id == SupplierBill.id)
        .filter(SettlementAllocation.settlement_id == settlement_id)
        .all()
    )

    return {
        "settlement": settlement,
        "allocations": allocations,
        "third_party": db.get(ThirdParty, settlement.third_party_id),
        "treasury_account": db.get(Account, settlement.treasury_account_id),
    }