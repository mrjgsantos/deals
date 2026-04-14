from app.core.config import settings

print(
    "DB DEBUG",
    {
        "postgres_server": settings.postgres_server,
        "postgres_port": settings.postgres_port,
        "postgres_user": settings.postgres_user,
        "postgres_db": settings.postgres_db,
        "database_url": settings.database_url.replace(settings.postgres_password, "***"),
    },
)

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.jobs.background_keepa_scheduler import (
    maybe_start_background_keepa_scheduler,
    stop_background_keepa_scheduler,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = maybe_start_background_keepa_scheduler()
    if scheduler is not None:
        app.state.background_keepa_scheduler = scheduler
        logger.info("background_keepa_scheduler_attached_to_app")
    try:
        yield
    finally:
        stop_background_keepa_scheduler(scheduler)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
