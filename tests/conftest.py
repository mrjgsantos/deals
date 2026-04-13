from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import engine


@pytest.fixture
def db_session() -> Session:
    try:
        connection = engine.connect()
        transaction = connection.begin()
        session = Session(bind=connection, autoflush=False, autocommit=False)
        table_names = [table.name for table in reversed(Base.metadata.sorted_tables)]
        if table_names:
            quoted_names = ", ".join(f'"{name}"' for name in table_names)
            connection.exec_driver_sql(f"TRUNCATE {quoted_names} RESTART IDENTITY CASCADE")
    except OperationalError as exc:
        pytest.skip(f"database unavailable: {exc}")

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
