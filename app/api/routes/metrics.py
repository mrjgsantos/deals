from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_staff_user,
    get_metrics_service,
    get_product_analytics_service,
    get_tracked_product_operations_service,
)
from app.core.config import settings
from app.db.session import get_db
from app.jobs.background_keepa_scheduler import BACKGROUND_KEEPA_INTERVAL_SECONDS
from app.schemas.api import (
    MetricsOverviewResponse,
    ProductAnalyticsDealPerformanceResponse,
    ProductAnalyticsOverviewResponse,
    TrackedProductsResponse,
    TrackedProductsSchedulerStatusResponse,
)
from app.services.metrics_service import MetricsService
from app.services.product_analytics_service import ProductAnalyticsService
from app.services.tracked_product_service import TrackedProductOperationsService

router = APIRouter(prefix="/metrics", dependencies=[Depends(get_staff_user)])


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


@router.get("/product-analytics", response_model=ProductAnalyticsOverviewResponse)
def get_product_analytics(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    service: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> ProductAnalyticsOverviewResponse:
    overview = service.get_overview(db, days=days, limit=limit)
    return ProductAnalyticsOverviewResponse(
        days=overview.days,
        user_signups=overview.user_signups,
        onboarding_completed=overview.onboarding_completed,
        deal_impressions=overview.deal_impressions,
        deal_clicks=overview.deal_clicks,
        deal_saves=overview.deal_saves,
        deal_unsaves=overview.deal_unsaves,
        recommended_deal_impressions=overview.recommended_deal_impressions,
        recommended_deal_clicks=overview.recommended_deal_clicks,
        ctr=overview.ctr,
        save_rate=overview.save_rate,
        recommendation_ctr=overview.recommendation_ctr,
        top_deals=[
            ProductAnalyticsDealPerformanceResponse(
                deal_id=item.deal_id,
                title=item.title,
                category=item.category,
                impression_count=item.impression_count,
                click_count=item.click_count,
                save_count=item.save_count,
                unsave_count=item.unsave_count,
                recommended_impression_count=item.recommended_impression_count,
                recommended_click_count=item.recommended_click_count,
                ctr=item.ctr,
                save_rate=item.save_rate,
                recommended_ctr=item.recommended_ctr,
            )
            for item in overview.top_deals
        ],
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
