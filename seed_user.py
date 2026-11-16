from app.core.database import SessionLocal
from app.models.user import User
from app.models.enums import UserRole
from app.core.security import get_password_hash

db = SessionLocal()
admin = db.query(User).filter(User.email == "admin@local.com").first()
if not admin:
    admin = User(
        email="admin@local.com",
        password_hash=get_password_hash("admin123"),
        role=UserRole.SYSTEM_ADMIN,
        is_active=True,
        language="fr"
    )
    db.add(admin)
    db.commit()
    print("✅ Admin user created: admin@local.com / admin123")
else:
    print("ℹ️ Admin user already exists.")
db.close()