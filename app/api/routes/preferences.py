from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_product_analytics_service, get_user_preferences_service
from app.db.models import User
from app.db.session import get_db
from app.schemas.api import UserPreferencesRequest, UserPreferencesResponse
from app.services.product_analytics_service import EVENT_ONBOARDING_COMPLETED, ProductAnalyticsService
from app.services.user_preferences_service import UserPreferencesService

router = APIRouter(prefix="/me/preferences", dependencies=[Depends(get_current_user)])


@router.get("", response_model=UserPreferencesResponse)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: UserPreferencesService = Depends(get_user_preferences_service),
) -> UserPreferencesResponse:
    result = service.get_preferences(db, user=current_user)
    return UserPreferencesResponse(
        categories=result.categories,
        budget_preference=result.budget_preference,
        intent=result.intent,
        has_pets=result.has_pets,
        has_kids=result.has_kids,
        context_flags=result.context_flags,
        category_affinity=result.category_affinity,
        saved_count_by_category=result.saved_count_by_category,
        clicked_count_by_category=result.clicked_count_by_category,
        negative_affinity=result.negative_affinity,
        is_profile_initialized=result.is_profile_initialized,
    )


@router.post("", response_model=UserPreferencesResponse)
def save_preferences(
    request: UserPreferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: UserPreferencesService = Depends(get_user_preferences_service),
    analytics: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> UserPreferencesResponse:
    existing = service.get_preferences(db, user=current_user)
    result = service.save_preferences(
        db,
        user=current_user,
        categories=request.categories,
        budget_preference=request.budget_preference,
        intent=request.intent,
        has_pets=request.has_pets,
        has_kids=request.has_kids,
        context_flags=request.context_flags,
    )
    if not existing.is_profile_initialized and result.is_profile_initialized:
        analytics.record_event(db, user_id=current_user.id, event_type=EVENT_ONBOARDING_COMPLETED)
    db.commit()
    return UserPreferencesResponse(
        categories=result.categories,
        budget_preference=result.budget_preference,
        intent=result.intent,
        has_pets=result.has_pets,
        has_kids=result.has_kids,
        context_flags=result.context_flags,
        category_affinity=result.category_affinity,
        saved_count_by_category=result.saved_count_by_category,
        clicked_count_by_category=result.clicked_count_by_category,
        negative_affinity=result.negative_affinity,
        is_profile_initialized=result.is_profile_initialized,
    )
