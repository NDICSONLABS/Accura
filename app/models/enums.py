import enum

class UserRole(str, enum.Enum):
    AUDITOR_VIEWER = "AUDITOR_VIEWER"
    ACCOUNTANT_PREPARER = "ACCOUNTANT_PREPARER"
    FINANCE_MANAGER_APPROVER = "FINANCE_MANAGER_APPROVER"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"

class PeriodStatus(str, enum.Enum):
    OPEN = "OPEN"
    SOFT_LOCKED = "SOFT_LOCKED"
    CLOSED = "CLOSED"

class FiscalYearStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"

class EntryStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    POSTED = "POSTED"

class NormalBalance(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"

class BudgetEnforcementMode(str, enum.Enum):
    NONE = "NONE"
    WARN = "WARN"
    STRICT = "STRICT"