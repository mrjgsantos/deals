from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_new_deals_service,
    get_product_analytics_service,
    get_recommendation_service,
    get_saved_deals_service,
)
from app.db.models import User
from app.db.session import get_db
from app.schemas.api import (
    DealImpressionRequest,
    DealImpressionResponse,
    NewDealsResponse,
    NewDealsSeenResponse,
    PublishedDealResponse,
    SavedDealItemResponse,
)
from app.services.new_deals_service import NewDealsService
from app.services.product_analytics_service import ProductAnalyticsService
from app.services.recommendation_service import RecommendationService
from app.services.saved_deals_service import SavedDealsService

router = APIRouter(prefix="/me", dependencies=[Depends(get_current_user)])


@router.get("/saved-deals", response_model=list[SavedDealItemResponse])
def get_saved_deals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: SavedDealsService = Depends(get_saved_deals_service),
) -> list[SavedDealItemResponse]:
    saved_deals = service.list_saved_deals(db, user=current_user)
    return [
        SavedDealItemResponse(
            saved_at=item.saved_at,
            deal=PublishedDealResponse.model_validate(item.deal),
        )
        for item in saved_deals
    ]


@router.get("/recommended-deals", response_model=list[PublishedDealResponse])
def get_recommended_deals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> list[PublishedDealResponse]:
    result = service.get_recommended_deals(db, user=current_user)
    return [PublishedDealResponse.model_validate(deal) for deal in result.deals]


@router.get("/new-deals", response_model=NewDealsResponse)
def get_new_deals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: NewDealsService = Depends(get_new_deals_service),
) -> NewDealsResponse:
    result = service.get_new_deals(db, user=current_user)
    return NewDealsResponse(
        new_count=result.new_count,
        fallback_used=result.fallback_used,
        last_seen_at=result.last_seen_at,
        deals=[PublishedDealResponse.model_validate(deal) for deal in result.deals],
    )


@router.post("/new-deals/mark-seen", response_model=NewDealsSeenResponse)
def mark_new_deals_seen(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: NewDealsService = Depends(get_new_deals_service),
) -> NewDealsSeenResponse:
    last_seen_at = service.mark_seen(db, user=current_user)
    db.commit()
    return NewDealsSeenResponse(last_seen_at=last_seen_at)


@router.post("/deal-impressions", response_model=DealImpressionResponse)
def track_deal_impressions(
    request: DealImpressionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> DealImpressionResponse:
    tracked = service.record_impressions(
        db,
        user_id=current_user.id,
        deal_ids=request.deal_ids,
        recommended=request.context == "recommended",
    )
    db.commit()
    return DealImpressionResponse(tracked=tracked, context=request.context)
