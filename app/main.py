import logging
import time
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
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

_INSECURE_SECRET = "change-me-in-production-auth-secret"


def _warn_insecure_config() -> None:
    if settings.auth_secret_key == _INSECURE_SECRET:
        warnings.warn(
            "AUTH_SECRET_KEY is using the default insecure value. "
            "Set a strong random secret in production.",
            stacklevel=2,
        )
        logger.warning("startup_insecure_auth_secret_key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warn_insecure_config()
    scheduler = maybe_start_background_keepa_scheduler()
    if scheduler is not None:
        app.state.background_keepa_scheduler = scheduler
        logger.info("background_keepa_scheduler_attached_to_app")
    try:
        yield
    finally:
        stop_background_keepa_scheduler(scheduler)


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def create_app() -> FastAPI:
    limiter = Limiter(key_func=get_remote_address)

    docs_url = "/docs" if settings.enable_api_docs else None
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=docs_url and "/redoc",
        openapi_url=docs_url and "/openapi.json",
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

    @app.middleware("http")
    async def log_request_timing(request: Request, call_next):
        t0 = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.warning(
            "perf_request endpoint=%s method=%s status=%s elapsed_ms=%.1f",
            request.url.path,
            request.method,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
