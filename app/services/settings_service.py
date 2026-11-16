from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.models.settings import OrganizationSetting
from app.models.ledger import JournalEntry, JournalLine
from app.models.enums import EntryStatus, BudgetEnforcementMode
from pydantic import BaseModel, Field


class SettingsUpdateSchema(BaseModel):
    multi_currency_enabled: bool
    donor_fund_tracking_enabled: bool
    project_cost_center_enabled: bool
    budget_control_enabled: bool
    budget_enforcement_mode: BudgetEnforcementMode
    maker_checker_approval_enabled: bool
    tax_withholding_enabled: bool


def get_settings(db: Session) -> OrganizationSetting:
    settings = db.query(OrganizationSetting).first()
    if not settings:
        # Fallback seed if somehow missing
        settings = OrganizationSetting()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def update_settings(db: Session, updates: SettingsUpdateSchema) -> OrganizationSetting:
    settings = get_settings(db)

    # SAFE TOGGLE LOCKING: Check for existing posted multi-currency or multi-fund transactions
    if settings.multi_currency_enabled and not updates.multi_currency_enabled:
        has_fx = db.query(JournalLine).join(JournalEntry).filter(
            JournalEntry.status == EntryStatus.POSTED,
            JournalLine.currency_code != 'XAF'
        ).first()
        if has_fx:
            raise ValueError("Cannot disable multi-currency: Posted foreign currency transactions exist.")

    if settings.donor_fund_tracking_enabled and not updates.donor_fund_tracking_enabled:
        has_funds = db.query(JournalLine).join(JournalEntry).filter(
            JournalEntry.status == EntryStatus.POSTED,
            JournalLine.fund_id.isnot(None)
        ).first()
        if has_funds:
            raise ValueError("Cannot disable donor tracking: Posted transactions with specific funds exist.")

    # Apply updates
    for field, value in updates.model_dump().items():
        setattr(settings, field, value)

    db.commit()
    db.refresh(settings)
    return settings