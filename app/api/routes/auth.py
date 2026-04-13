from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_auth_service, get_current_user, get_google_identity_service, get_product_analytics_service
from app.db.models import User
from app.db.session import get_db
from app.schemas.api import AuthCredentialsRequest, AuthTokenResponse, AuthUserResponse, GoogleAuthRequest
from app.services.auth_service import AuthService
from app.services.google_identity_service import GoogleIdentityService
from app.services.product_analytics_service import EVENT_USER_SIGNUP, ProductAnalyticsService

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: AuthCredentialsRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
    analytics: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> AuthTokenResponse:
    try:
        result = service.register(db, email=request.email, password=request.password)
        analytics.record_event(db, user_id=result.user.id, event_type=EVENT_USER_SIGNUP)
        db.commit()
        db.refresh(result.user)
    except ValueError as exc:
        db.rollback()
        if str(exc) == "email_already_registered":
            raise HTTPException(status_code=409, detail="email_already_registered") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="email_already_registered") from exc

    return AuthTokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        user=AuthUserResponse.model_validate(result.user),
        is_new_user=result.is_new_user,
    )


@router.post("/login", response_model=AuthTokenResponse)
def login(
    request: AuthCredentialsRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> AuthTokenResponse:
    try:
        result = service.login(db, email=request.email, password=request.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return AuthTokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        user=AuthUserResponse.model_validate(result.user),
        is_new_user=result.is_new_user,
    )


@router.post("/google", response_model=AuthTokenResponse)
def google_login(
    request: GoogleAuthRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
    google_service: GoogleIdentityService = Depends(get_google_identity_service),
    analytics: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> AuthTokenResponse:
    try:
        identity = google_service.verify_id_token(request.id_token)
        result = service.login_with_google(db, identity=identity)
        if result.is_new_user:
            analytics.record_event(db, user_id=result.user.id, event_type=EVENT_USER_SIGNUP)
        db.commit()
        db.refresh(result.user)
    except ValueError as exc:
        db.rollback()
        detail = str(exc)
        if detail == "google_auth_not_configured":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail) from exc
        if detail in {"invalid_google_token", "google_email_not_verified", "google_email_missing"}:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail) from exc
        if detail == "google_account_mismatch":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="google_account_mismatch") from exc

    return AuthTokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        user=AuthUserResponse.model_validate(result.user),
        is_new_user=result.is_new_user,
    )


@router.get("/me", response_model=AuthUserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse.model_validate(current_user)
