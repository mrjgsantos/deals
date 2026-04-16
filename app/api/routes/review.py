from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_staff_user, get_deal_query_service, get_review_service
from app.db.session import get_db
from app.schemas.api import (
    DealPriceHistoryResponse,
    ReviewDecisionResponse,
    ReviewQueueItemResponse,
    ReviewQueueListItemResponse,
    ReviewQueuePageResponse,
)
from app.services.deal_service import DealQueryService, ReviewQueueListItemRecord
from app.services.review_service import ReviewService

router = APIRouter(prefix="/review", dependencies=[Depends(get_staff_user)])


@router.get("/queue", response_model=ReviewQueuePageResponse)
def get_review_queue(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> ReviewQueuePageResponse:
    page = service.list_review_queue(db, limit=limit, offset=offset)
    return ReviewQueuePageResponse(
        items=[_to_list_item_response(item) for item in page.items],
        total=page.total,
        has_more=page.has_more,
    )


def _to_list_item_response(item: ReviewQueueListItemRecord) -> ReviewQueueListItemResponse:
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
    return ReviewQueueListItemResponse(
        id=item.id,
        priority=item.priority,
        created_at=item.created_at,
        deal_id=item.deal_id,
        title=item.title,
        currency=item.currency,
        current_price=item.current_price,
        previous_price=item.previous_price,
        savings_amount=item.savings_amount,
        savings_percent=item.savings_percent,
        deal_url=item.deal_url,
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


@router.get("/pending", response_model=list[ReviewQueueItemResponse])
def get_pending_review(
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> list[ReviewQueueItemResponse]:
    review_items = service.list_pending_review_items(db)
    return [ReviewQueueItemResponse.model_validate(item) for item in review_items]


@router.post("/{review_id}/approve", response_model=ReviewDecisionResponse)
def approve_deal(
    review_id: UUID,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
) -> ReviewDecisionResponse:
    try:
        decision = service.approve(db, review_id)
    except ValueError as exc:
        if str(exc) == "review_not_found":
            raise HTTPException(status_code=404, detail="review_not_found") from None
        if str(exc) == "deal_not_found":
            raise HTTPException(status_code=404, detail="deal_not_found") from None
        if str(exc) in {"review_already_resolved", "invalid_deal_state", "unsupported_review_type"}:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return ReviewDecisionResponse(
        review_id=decision.review_id,
        review_status=decision.review_status,
        deal_id=decision.deal_id,
        deal_status=decision.deal_status,
    )


@router.post("/{review_id}/reject", response_model=ReviewDecisionResponse)
def reject_deal(
    review_id: UUID,
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
) -> ReviewDecisionResponse:
    try:
        decision = service.reject(db, review_id)
    except ValueError as exc:
        if str(exc) == "review_not_found":
            raise HTTPException(status_code=404, detail="review_not_found") from None
        if str(exc) == "deal_not_found":
            raise HTTPException(status_code=404, detail="deal_not_found") from None
        if str(exc) in {"review_already_resolved", "invalid_deal_state", "unsupported_review_type"}:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return ReviewDecisionResponse(
        review_id=decision.review_id,
        review_status=decision.review_status,
        deal_id=decision.deal_id,
        deal_status=decision.deal_status,
    )
