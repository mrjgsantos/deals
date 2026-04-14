from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_deal_publication_service,
    get_deal_query_service,
    get_personalization_service,
    get_product_analytics_service,
    get_saved_deals_service,
)
from app.db.models import User
from app.db.enums import DealStatus
from app.db.session import get_db
from app.schemas.api import (
    DealsListItemResponse,
    DealsListPageResponse,
    DealClickResponse,
    DealPriceHistoryResponse,
    DealPublicationResponse,
    DealResponse,
    SavedDealMutationResponse,
)
from app.services.deal_service import DealsListItemRecord, DealPublicationService, DealQueryService
from app.services.personalization import PersonalizationService
from app.services.product_analytics_service import (
    EVENT_DEAL_CLICK,
    EVENT_DEAL_SAVED,
    EVENT_DEAL_UNSAVED,
    EVENT_RECOMMENDED_DEAL_CLICK,
    ProductAnalyticsService,
)
from app.services.saved_deals_service import SavedDealsService

router = APIRouter(prefix="/deals", dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[DealResponse])
def list_deals(
    status: DealStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> list[DealResponse]:
    deals = service.list_deals(db, status=status)
    return [DealResponse.model_validate(deal) for deal in deals]


@router.get("/list", response_model=DealsListPageResponse)
def list_deals_page(
    status: DealStatus | None = Query(default=None),
    source: str | None = Query(default=None, pattern="^(amazon|google)$"),
    min_score: int | None = Query(default=None, ge=0, le=100),
    min_savings: float | None = Query(default=None, ge=0, le=100),
    since_days: int | None = Query(default=None, ge=1, le=365),
    fake_discount_only: bool = Query(default=False),
    sort_by: str = Query(default="newest", pattern="^(newest|score|savings)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> DealsListPageResponse:
    page = service.list_deals_page(
        db,
        status=status,
        source=source,
        min_score=min_score,
        min_savings=min_savings,
        since_days=since_days,
        fake_discount_only=fake_discount_only,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )
    return DealsListPageResponse(
        items=[_to_deals_list_item_response(item) for item in page.items],
        total=page.total,
        has_more=page.has_more,
    )


def _to_deals_list_item_response(item: DealsListItemRecord) -> DealsListItemResponse:
    ph = item.price_history
    price_history_resp: DealPriceHistoryResponse | None = None
    if ph and isinstance(ph, dict):
        price_history_resp = DealPriceHistoryResponse(
            avg_30d=_to_decimal(ph.get("avg_30d")),
            avg_90d=_to_decimal(ph.get("avg_90d")),
            min_90d=_to_decimal(ph.get("min_90d")),
            max_90d=_to_decimal(ph.get("max_90d")),
            all_time_min=_to_decimal(ph.get("all_time_min")),
            days_at_current_price=ph.get("days_at_current_price"),
            observation_count_30d=int(ph.get("observation_count_30d") or 0),
            observation_count_90d=int(ph.get("observation_count_90d") or 0),
            observation_count_all_time=int(ph.get("observation_count_all_time") or 0),
        )
    return DealsListItemResponse(
        id=item.id,
        title=item.title,
        status=item.status,
        currency=item.currency,
        current_price=item.current_price,
        previous_price=item.previous_price,
        savings_amount=item.savings_amount,
        savings_percent=item.savings_percent,
        deal_url=item.deal_url,
        detected_at=item.detected_at,
        source_id=item.source_id,
        source_category=item.source_category,
        image_url=item.image_url,
        quality_score=item.quality_score,
        business_score=item.business_score,
        promotable=item.promotable,
        fake_discount=item.fake_discount,
        confidence_level=item.confidence_level,
        quality_reasons=item.quality_reasons,
        price_history=price_history_resp,
        asin=item.asin,
    )


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


@router.get("/{deal_id}", response_model=DealResponse)
def get_deal(
    deal_id: UUID,
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> DealResponse:
    deal = service.get_deal(db, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="deal_not_found")
    return DealResponse.model_validate(deal)


@router.post("/{deal_id}/publish", response_model=DealPublicationResponse)
def publish_deal(
    deal_id: UUID,
    db: Session = Depends(get_db),
    service: DealPublicationService = Depends(get_deal_publication_service),
) -> DealPublicationResponse:
    try:
        result = service.mark_published(db, deal_id)
    except ValueError as exc:
        detail = str(exc)
        if detail == "deal_not_found":
            raise HTTPException(status_code=404, detail=detail) from exc
        if detail == "invalid_deal_state":
            raise HTTPException(status_code=409, detail=detail) from exc
        raise
    return DealPublicationResponse(
        deal_id=result.deal_id,
        deal_status=result.deal_status,
        published_at=result.published_at,
    )


@router.post("/{deal_id}/save", response_model=SavedDealMutationResponse)
def save_deal(
    deal_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: SavedDealsService = Depends(get_saved_deals_service),
    analytics: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> SavedDealMutationResponse:
    try:
        result = service.save_deal(db, user=current_user, deal_id=deal_id)
        analytics.record_event(db, user_id=current_user.id, event_type=EVENT_DEAL_SAVED, deal_id=deal_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        if str(exc) == "deal_not_found":
            raise HTTPException(status_code=404, detail="deal_not_found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        result = service.save_deal(db, user=current_user, deal_id=deal_id)

    return SavedDealMutationResponse(deal_id=result.deal_id, saved=result.saved)


@router.delete("/{deal_id}/save", response_model=SavedDealMutationResponse)
def unsave_deal(
    deal_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: SavedDealsService = Depends(get_saved_deals_service),
    analytics: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> SavedDealMutationResponse:
    result = service.unsave_deal(db, user=current_user, deal_id=deal_id)
    analytics.record_event(db, user_id=current_user.id, event_type=EVENT_DEAL_UNSAVED, deal_id=deal_id)
    db.commit()
    return SavedDealMutationResponse(deal_id=result.deal_id, saved=result.saved)


@router.post("/{deal_id}/click", response_model=DealClickResponse)
def track_deal_click(
    deal_id: UUID,
    context: str = Query(default="feed", pattern="^(feed|recommended)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: PersonalizationService = Depends(get_personalization_service),
    analytics: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> DealClickResponse:
    try:
        service.record_click(db, user=current_user, deal_id=deal_id)
        analytics.record_event(
            db,
            user_id=current_user.id,
            event_type=EVENT_RECOMMENDED_DEAL_CLICK if context == "recommended" else EVENT_DEAL_CLICK,
            deal_id=deal_id,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        if str(exc) == "deal_not_found":
            raise HTTPException(status_code=404, detail="deal_not_found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DealClickResponse(deal_id=deal_id, clicked=True)
