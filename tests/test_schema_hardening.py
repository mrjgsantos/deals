from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.db.models import TrackedProduct
from app.db.session import SessionLocal, engine


def test_tracked_products_table_exists_when_database_is_migrated() -> None:
    try:
        with engine.connect() as connection:
            has_table = inspect(connection).has_table("tracked_products")
    except OperationalError:
        pytest.skip("database unavailable")

    assert has_table is True


def test_tracked_products_rows_can_be_inserted_when_database_is_migrated() -> None:
    try:
        with SessionLocal() as db:
            tracked_product = TrackedProduct(
                asin=f"B0{uuid4().hex[:8].upper()}",
                domain_id=9,
            )
            db.add(tracked_product)
            db.flush()
            assert tracked_product.id is not None
            db.rollback()
    except OperationalError:
        pytest.skip("database unavailable")
