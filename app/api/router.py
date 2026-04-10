from fastapi import APIRouter

from app.api.routes.deals import router as deals_router
from app.api.routes.health import router as health_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.published_deals import router as published_deals_router
from app.api.routes.review import router as review_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(deals_router, tags=["deals"])
api_router.include_router(published_deals_router, tags=["published-deals"])
api_router.include_router(review_router, tags=["review"])
api_router.include_router(ingest_router, tags=["ingestion"])
api_router.include_router(metrics_router, tags=["metrics"])
