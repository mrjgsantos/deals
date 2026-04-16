from sqlalchemy.engine import make_url
from app.core.config import settings

try:
    parsed = make_url(settings.database_url)
    print(
        "DB DEBUG PARSED",
        {
            "drivername": parsed.drivername,
            "username": parsed.username,
            "host": parsed.host,
            "port": parsed.port,
            "database": parsed.database,
            "query": dict(parsed.query),
        },
    )
except Exception as exc:
    print("DB DEBUG PARSE ERROR", repr(exc))

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

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
    limiter = Limiter(key_func=get_remote_address)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Explicit origins from env (e.g. custom domains).
    # Vercel deployments (*.vercel.app) are always allowed via regex so no
    # Render env var is required for standard Vercel deployments.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()