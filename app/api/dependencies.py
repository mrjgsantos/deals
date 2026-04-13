from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.matching.service import MatchingService
from app.ai.client import ModelClient, StubModelClient
from app.ai.service import AICopyGenerationService
from app.db.models import User
from app.db.session import get_db
from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.parsers.affiliate_feed import AffiliateFeedCSVParser
from app.ingestion.parsers.keepa import KeepaParser
from app.ingestion.service import IngestionService
from app.services.auth_service import AuthService
from app.services.deal_service import DealPublicationService, DealQueryService
from app.services.google_identity_service import GoogleIdentityService
from app.services.metrics_service import MetricsService
from app.services.new_deals_service import NewDealsService
from app.services.personalization import PersonalizationService
from app.services.product_analytics_service import ProductAnalyticsService
from app.services.review_service import ReviewService
from app.services.recommendation_service import RecommendationService
from app.services.saved_deals_service import SavedDealsService
from app.services.tracked_product_service import TrackedProductOperationsService
from app.services.user_preferences_service import UserPreferencesService

bearer_scheme = HTTPBearer(auto_error=False)


def get_deal_query_service() -> DealQueryService:
    return DealQueryService()


def get_auth_service() -> AuthService:
    return AuthService()


def get_google_identity_service() -> GoogleIdentityService:
    return GoogleIdentityService()


def get_deal_publication_service() -> DealPublicationService:
    return DealPublicationService()


def get_metrics_service() -> MetricsService:
    return MetricsService()


def get_personalization_service() -> PersonalizationService:
    return PersonalizationService()


def get_review_service() -> ReviewService:
    return ReviewService()


def get_tracked_product_operations_service() -> TrackedProductOperationsService:
    return TrackedProductOperationsService()


def get_saved_deals_service() -> SavedDealsService:
    return SavedDealsService()


def get_recommendation_service() -> RecommendationService:
    return RecommendationService()


def get_new_deals_service() -> NewDealsService:
    return NewDealsService()


def get_user_preferences_service() -> UserPreferencesService:
    return UserPreferencesService()


def get_product_analytics_service() -> ProductAnalyticsService:
    return ProductAnalyticsService()


def get_model_client() -> ModelClient:
    return StubModelClient(
        '{"title":"Draft unavailable","summary":"No model client configured.","verdict":"not_supported","tags":["review-needed"]}'
    )


def get_ai_copy_service() -> AICopyGenerationService:
    return AICopyGenerationService(client=get_model_client())


def get_ingestion_service(parser_name: str) -> IngestionService:
    parsers = {
        "keepa": KeepaParser(),
        "affiliate_csv": AffiliateFeedCSVParser(),
    }
    parser = parsers[parser_name]
    return IngestionService(
        parser=parser,
        normalizer=DefaultRecordNormalizer(),
        matcher=MatchingService(),
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return service.get_user_by_token(db, credentials.credentials)
    except ValueError as exc:
        detail = str(exc)
        if detail not in {"invalid_token", "token_expired"}:
            detail = "invalid_token"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> User | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        return service.get_user_by_token(db, credentials.credentials)
    except ValueError:
        return None
