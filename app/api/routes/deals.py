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
from app.schemas.api import DealClickResponse, DealPublicationResponse, DealResponse, SavedDealMutationResponse
from app.services.deal_service import DealPublicationService, DealQueryService
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
