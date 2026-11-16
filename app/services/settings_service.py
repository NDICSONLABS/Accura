from sqlalchemy.orm import Session
from app.models.settings import OrganizationSetting
from app.models.ledger import JournalEntry, JournalLine
from app.models.enums import EntryStatus, BudgetEnforcementMode
from pydantic import BaseModel


class SettingsUpdateSchema(BaseModel):
    multi_currency_enabled: bool
    donor_fund_tracking_enabled: bool
    project_cost_center_enabled: bool
    budget_control_enabled: bool
    budget_enforcement_mode: BudgetEnforcementMode
    maker_checker_approval_enabled: bool
    tax_withholding_enabled: bool


# Canonical keys + safe defaults for a JSON-safe settings representation.
_SETTINGS_KEYS = {
    "multi_currency_enabled": False,
    "donor_fund_tracking_enabled": False,
    "project_cost_center_enabled": False,
    "budget_control_enabled": False,
    "budget_enforcement_mode": "NONE",
    "maker_checker_approval_enabled": False,
    "tax_withholding_enabled": False,
}


def settings_to_dict(settings) -> dict:
    """
    Convert an OrganizationSetting (SQLAlchemy object), a dict, or None into a
    consistent, JSON-safe plain dict. This is the SINGLE source of truth for
    serializing feature flags to templates and Alpine.js.
    """
    if settings is None:
        return dict(_SETTINGS_KEYS)

    if isinstance(settings, dict):
        merged = dict(_SETTINGS_KEYS)
        for key in _SETTINGS_KEYS:
            if key in settings and settings[key] is not None:
                merged[key] = settings[key]
        return merged

    # SQLAlchemy ORM object
    mode = getattr(settings, "budget_enforcement_mode", None)
    mode_value = mode.value if hasattr(mode, "value") else (mode or "NONE")

    return {
        "multi_currency_enabled": bool(getattr(settings, "multi_currency_enabled", False)),
        "donor_fund_tracking_enabled": bool(getattr(settings, "donor_fund_tracking_enabled", False)),
        "project_cost_center_enabled": bool(getattr(settings, "project_cost_center_enabled", False)),
        "budget_control_enabled": bool(getattr(settings, "budget_control_enabled", False)),
        "budget_enforcement_mode": mode_value,
        "maker_checker_approval_enabled": bool(getattr(settings, "maker_checker_approval_enabled", False)),
        "tax_withholding_enabled": bool(getattr(settings, "tax_withholding_enabled", False)),
    }


def get_settings(db: Session) -> OrganizationSetting:
    settings = db.query(OrganizationSetting).first()
    if not settings:
        settings = OrganizationSetting()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def update_settings(db: Session, updates: SettingsUpdateSchema) -> OrganizationSetting:
    settings = get_settings(db)

    # SAFE TOGGLE LOCKING: Block disabling features that already have posted transactions.
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

    for field, value in updates.model_dump().items():
        setattr(settings, field, value)

    db.commit()
    db.refresh(settings)
    return settings