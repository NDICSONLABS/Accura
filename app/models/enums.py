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


class DepreciationMethod(str, enum.Enum):
    STRAIGHT_LINE = "STRAIGHT_LINE"
    DECLINING_BALANCE = "DECLINING_BALANCE"


class AssetStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    FULLY_DEPRECIATED = "FULLY_DEPRECIATED"
    DISPOSED = "DISPOSED"


class DepreciationStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    POSTED = "POSTED"
    SKIPPED = "SKIPPED"


class GrantStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class TrancheStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    CALLED = "CALLED"
    RECEIVED = "RECEIVED"


class FxDirection(str, enum.Enum):
    LOSS = "LOSS"
    GAIN = "GAIN"