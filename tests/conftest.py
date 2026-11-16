import pytest
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command
from app.core.config import settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(settings.DATABASE_URL)
    alembic_ini_path = os.path.join(BASE_DIR, "alembic.ini")
    alembic_dir = os.path.join(BASE_DIR, "app", "alembic")
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    alembic_cfg.set_main_option("script_location", alembic_dir)
    command.upgrade(alembic_cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    yield session

    session.close()
    # Prevent SAWarning by only rolling back if still active
    if transaction.is_active:
        transaction.rollback()
    connection.close()