import logging
import time

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn: Connection, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_times", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn: Connection, cursor, statement, parameters, context, executemany):
    elapsed_ms = (time.perf_counter() - conn.info["query_start_times"].pop()) * 1000
    # Log slow queries (>50ms) always; log all queries at DEBUG level
    snippet = statement.replace("\n", " ")[:120]
    if elapsed_ms > 50:
        logger.warning("perf_slow_query elapsed_ms=%.1f sql=%s", elapsed_ms, snippet)
    else:
        logger.debug("perf_query elapsed_ms=%.1f sql=%s", elapsed_ms, snippet)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
