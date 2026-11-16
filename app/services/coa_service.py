from sqlalchemy.orm import Session
from app.models.account import Account
from pydantic import BaseModel
from app.models.enums import NormalBalance

class AccountCreateSchema(BaseModel):
    code: str
    label: str
    account_class: int
    parent_id: int | None = None
    normal_balance: NormalBalance
    is_postable: bool = True
    requires_third_party: bool = False

def get_coa_tree(db: Session, search: str = "") -> list[Account]:
    query = db.query(Account).filter(Account.is_active == True)
    if search:
        query = query.filter(
            (Account.code.ilike(f"%{search}%")) | (Account.label.ilike(f"%{search}%"))
        )
    return query.order_by(Account.code).all()

def create_account(db: Session, account_data: AccountCreateSchema) -> Account:
    new_account = Account(**account_data.model_dump(), default_currency_code="XAF")
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account

def toggle_account_active(db: Session, account_id: int) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if account:
        account.is_active = not account.is_active
        db.commit()
        db.refresh(account)
    return account