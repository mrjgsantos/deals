from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_auth_service, get_current_user, get_google_identity_service, get_product_analytics_service
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.api import (
    AuthCredentialsRequest,
    AuthTokenResponse,
    AuthUserResponse,
    ForgotPasswordRequest,
    GoogleAuthRequest,
    ResetPasswordRequest,
)
from app.services.auth_service import AuthService
from app.services.email_service import send_password_reset_email, send_verification_email
from app.services.google_identity_service import GoogleIdentityService
from app.services.product_analytics_service import EVENT_USER_SIGNUP, ProductAnalyticsService

router = APIRouter(prefix="/auth")
_limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
@_limiter.limit("10/minute")
def register(
    request: Request,
    body: Annotated[AuthCredentialsRequest, Body()],
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
    analytics: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> AuthTokenResponse:
    try:
        result = service.register(db, email=body.email, password=body.password)
        analytics.record_event(db, user_id=result.user.id, event_type=EVENT_USER_SIGNUP)
        plain_token = service.create_email_verification_token(db, user_id=result.user.id)
        db.commit()
        db.refresh(result.user)
        verify_url = f"{settings.app_base_url}/verify-email?token={plain_token}"
        try:
            send_verification_email(to_email=result.user.email, verify_url=verify_url)
        except Exception:
            pass  # Don't fail registration if email sending fails
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
@_limiter.limit("20/minute")
def login(
    request: Request,
    body: Annotated[AuthCredentialsRequest, Body()],
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> AuthTokenResponse:
    try:
        result = service.login(db, email=body.email, password=body.password)
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
    request: Request,
    body: GoogleAuthRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
    google_service: GoogleIdentityService = Depends(get_google_identity_service),
    analytics: ProductAnalyticsService = Depends(get_product_analytics_service),
) -> AuthTokenResponse:
    try:
        identity = google_service.verify_id_token(body.id_token)
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


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
@_limiter.limit("5/minute")
def forgot_password(
    request: Request,
    body: Annotated[ForgotPasswordRequest, Body()],
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    plain_token = service.request_password_reset(db, email=body.email)
    if plain_token is not None:
        reset_url = f"{settings.app_base_url}/reset-password?token={plain_token}"
        try:
            send_password_reset_email(to_email=body.email, reset_url=reset_url)
            db.commit()
        except Exception:
            db.rollback()
    # Always return 204 — don't reveal whether the email exists.
    return Response(status_code=204)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
@_limiter.limit("10/minute")
def reset_password(
    request: Request,
    body: Annotated[ResetPasswordRequest, Body()],
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    try:
        service.reset_password(db, token=body.token, new_password=body.new_password)
        db.commit()
        return Response(status_code=204)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
@_limiter.limit("10/minute")
def verify_email(
    request: Request,
    body: Annotated[dict, Body()],
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    token = str(body.get("token", "")).strip()
    if not token:
        raise HTTPException(status_code=400, detail="token_required")
    try:
        service.verify_email(db, token=token)
        db.commit()
        return Response(status_code=204)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
@_limiter.limit("3/minute")
def resend_verification(
    request: Request,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    if current_user.email_verified_at is not None:
        return Response(status_code=204)
    plain_token = service.create_email_verification_token(db, user_id=current_user.id)
    db.commit()
    verify_url = f"{settings.app_base_url}/verify-email?token={plain_token}"
    try:
        send_verification_email(to_email=current_user.email, verify_url=verify_url)
    except Exception:
        pass
    return Response(status_code=204)


@router.get("/me", response_model=AuthUserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse.model_validate(current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    service.delete_user(db, user_id=current_user.id)
    db.commit()
    return Response(status_code=204)
