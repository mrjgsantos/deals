from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal


def setup_job_logger(job_name: str) -> logging.Logger:
    log_dir = Path(settings.jobs_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"jobs.{job_name}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        log_dir / f"{job_name}.log",
        maxBytes=1_000_000,
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


@contextmanager
def job_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_job(job_name: str, callback) -> int:
    logger = setup_job_logger(job_name)
    try:
        return callback(logger)
    except Exception:
        logger.exception("job_failed")
        return 1
