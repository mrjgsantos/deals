from __future__ import annotations

import base64
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_deal_query_service, get_optional_current_user, get_personalization_service
from app.db.enums import DealStatus
from app.db.models import User
from app.db.session import get_db
from app.schemas.api import PublishedDealFeedItemResponse, PublishedDealResponse, PublishedDealsPageResponse
from app.services.deal_service import DealQueryService, PublishedDealsPage
from app.services.personalization import PersonalizationService

router = APIRouter(prefix="/published-deals")
DEFAULT_PUBLISHED_DEALS_PAGE_SIZE = 12
MAX_PUBLISHED_DEALS_PAGE_SIZE = 50


def _published_approved_deals(service: DealQueryService, db: Session):
    return [
        deal
        for deal in service.list_deals(db)
        if deal.status in {DealStatus.APPROVED.value, DealStatus.PUBLISHED.value}
        if deal.published_at is not None
    ]


def _encode_published_deals_cursor(*, published_at: str, deal_id: UUID) -> str:
    payload = {"published_at": published_at, "id": str(deal_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def _decode_published_deals_cursor(cursor: str) -> tuple[str, UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid_cursor") from exc
    published_at = payload.get("published_at")
    deal_id = payload.get("id")
    if not isinstance(published_at, str) or not published_at:
        raise HTTPException(status_code=400, detail="invalid_cursor")
    try:
        parsed_deal_id = UUID(str(deal_id))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid_cursor") from exc
    return published_at, parsed_deal_id


@router.get("", response_model=list[PublishedDealResponse])
def list_published_deals(
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
    current_user: User | None = Depends(get_optional_current_user),
    personalization_service: PersonalizationService = Depends(get_personalization_service),
) -> list[PublishedDealResponse]:
    deals = _published_approved_deals(service, db)
    if current_user is not None:
        profile = personalization_service.load_profile(db, user=current_user)
        deals = personalization_service.rank_deals_for_user(deals, profile=profile)
    else:
        deals = personalization_service.rank_default_feed(deals)
    return [PublishedDealResponse.model_validate(deal) for deal in deals]


@router.get("/page", response_model=PublishedDealsPageResponse)
def list_published_deals_page(
    limit: int = Query(default=DEFAULT_PUBLISHED_DEALS_PAGE_SIZE, ge=1, le=MAX_PUBLISHED_DEALS_PAGE_SIZE),
    cursor: str | None = Query(default=None),
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
    current_user: User | None = Depends(get_optional_current_user),
    personalization_service: PersonalizationService = Depends(get_personalization_service),
) -> PublishedDealsPageResponse:
    cursor_published_at = None
    cursor_id = None
    if cursor:
        published_at_raw, cursor_id = _decode_published_deals_cursor(cursor)
        from datetime import datetime

        try:
            cursor_published_at = datetime.fromisoformat(published_at_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid_cursor") from exc

    page = service.list_published_deals_page(
        db,
        limit=limit,
        cursor_published_at=cursor_published_at,
        cursor_id=cursor_id,
    )
    deals = _rank_published_page(page, current_user=current_user, db=db, personalization_service=personalization_service)
    next_cursor = None
    if page.has_more and page.next_published_at is not None and page.next_id is not None:
        next_cursor = _encode_published_deals_cursor(
            published_at=page.next_published_at.isoformat(),
            deal_id=page.next_id,
        )
    return PublishedDealsPageResponse(
        items=[PublishedDealResponse.model_validate(deal) for deal in deals],
        next_cursor=next_cursor,
        has_more=page.has_more,
    )


@router.get("/feed", response_model=list[PublishedDealFeedItemResponse])
def list_published_deals_feed(
    limit: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db),
    service: DealQueryService = Depends(get_deal_query_service),
    personalization_service: PersonalizationService = Depends(get_personalization_service),
) -> list[PublishedDealFeedItemResponse]:
    deals = personalization_service.rank_default_feed(_published_approved_deals(service, db))
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


def _rank_published_page(
    page: PublishedDealsPage,
    *,
    current_user: User | None,
    db: Session,
    personalization_service: PersonalizationService,
):
    if current_user is not None:
        profile = personalization_service.load_profile(db, user=current_user)
        return personalization_service.rank_deals_for_user(page.deals, profile=profile)
    return personalization_service.rank_default_feed(page.deals)
