from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_deal_query_service
from app.db.enums import DealStatus
from app.db.session import get_db
from app.schemas.api import PublishedDealFeedItemResponse, PublishedDealResponse
from app.services.deal_service import DealQueryService

router = APIRouter(prefix="/published-deals")


def _published_approved_deals(service: DealQueryService, db: Session):
    return [
        deal
        for deal in service.list_deals(db)
        if deal.status in {DealStatus.APPROVED.value, DealStatus.PUBLISHED.value}
        if deal.published_at is not None
    ]


@router.get("", response_model=list[PublishedDealResponse])
def list_published_deals(
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> list[PublishedDealResponse]:
    deals = _published_approved_deals(service, db)
    return [PublishedDealResponse.model_validate(deal) for deal in deals]


@router.get("/feed", response_model=list[PublishedDealFeedItemResponse])
def list_published_deals_feed(
    limit: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> list[PublishedDealFeedItemResponse]:
    deals = sorted(
        _published_approved_deals(service, db),
        key=lambda deal: deal.detected_at,
        reverse=True,
    )
    if limit is not None:
        deals = deals[:limit]
    return [PublishedDealFeedItemResponse.model_validate(deal) for deal in deals]


@router.get("/{deal_id}", response_model=PublishedDealResponse)
def get_published_deal(
    deal_id: UUID,
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
) -> PublishedDealResponse:
    deal = service.get_deal(db, deal_id)
    if (
        deal is None
        or deal.status not in {DealStatus.APPROVED.value, DealStatus.PUBLISHED.value}
        or deal.published_at is None
    ):
        raise HTTPException(status_code=404, detail="published_deal_not_found")
    return PublishedDealResponse.model_validate(deal)
