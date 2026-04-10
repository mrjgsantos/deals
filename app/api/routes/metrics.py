from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_metrics_service, get_tracked_product_operations_service
from app.core.config import settings
from app.db.session import get_db
from app.jobs.background_keepa_scheduler import BACKGROUND_KEEPA_INTERVAL_SECONDS
from app.schemas.api import MetricsOverviewResponse, TrackedProductsResponse, TrackedProductsSchedulerStatusResponse
from app.services.metrics_service import MetricsService
from app.services.tracked_product_service import TrackedProductOperationsService

router = APIRouter(prefix="/metrics")


@router.get("/overview", response_model=MetricsOverviewResponse)
def get_metrics_overview(
    db: Session = Depends(get_db),
    service: MetricsService = Depends(get_metrics_service),
) -> MetricsOverviewResponse:
    overview = service.get_overview(db)
    return MetricsOverviewResponse.model_validate(overview)


@router.get("/tracked-products", response_model=TrackedProductsResponse)
def get_tracked_products(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    service: TrackedProductOperationsService = Depends(get_tracked_product_operations_service),
) -> TrackedProductsResponse:
    scheduler = _tracked_products_scheduler_status(request)
    tracked_products = service.list_operations(
        db,
        limit=limit,
        refresh_interval_seconds=scheduler.interval_seconds if scheduler.enabled else None,
    )
    summary = service.get_summary(db)
    return TrackedProductsResponse(
        scheduler=scheduler,
        summary=summary,
        items=tracked_products,
    )


def _tracked_products_scheduler_status(request: Request) -> TrackedProductsSchedulerStatusResponse:
    scheduler = getattr(request.app.state, "background_keepa_scheduler", None)
    if scheduler is None:
        enabled = settings.enable_background_jobs
        return TrackedProductsSchedulerStatusResponse(
            enabled=enabled,
            is_running=False,
            interval_seconds=BACKGROUND_KEEPA_INTERVAL_SECONDS if enabled else None,
            last_status="unavailable" if enabled else "disabled",
        )

    snapshot = scheduler.get_runtime_snapshot()
    summary = snapshot.last_summary
    return TrackedProductsSchedulerStatusResponse(
        enabled=True,
        is_running=snapshot.is_running,
        interval_seconds=snapshot.interval_seconds,
        last_started_at=snapshot.last_started_at,
        last_completed_at=snapshot.last_completed_at,
        last_status=snapshot.last_status,
        last_error_reason=snapshot.last_error_reason,
        tracked_asins=summary.tracked_asins if summary is not None else None,
        eligible_asins=summary.eligible_asins if summary is not None else None,
        fetched_products=summary.fetched_products if summary is not None else None,
        accepted=summary.accepted if summary is not None else None,
        rejected=summary.rejected if summary is not None else None,
        failed_batches=summary.failed_batches if summary is not None else None,
        skipped_reason=summary.skipped_reason if summary is not None else None,
    )
