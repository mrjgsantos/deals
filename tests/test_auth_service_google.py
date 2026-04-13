from __future__ import annotations

from app.db.models import User
from app.services.auth_service import AuthService
from app.services.google_identity_service import GoogleIdentity


def test_login_with_google_logs_in_existing_same_email_user(db_session) -> None:
    service = AuthService()
    user = User(
        email="reviewer@example.com",
        password_hash="pbkdf2_sha256$390000$testsalt$testdigest",
    )
    db_session.add(user)
    db_session.flush()

    result = service.login_with_google(
        db_session,
        identity=GoogleIdentity(
            sub="google-sub-123",
            email="reviewer@example.com",
            email_verified=True,
            name="Reviewer",
            picture="https://example.com/avatar.png",
        ),
    )

    assert result.user.id == user.id
    assert result.user.google_sub == "google-sub-123"
    assert result.user.display_name == "Reviewer"
    assert result.is_new_user is False


def test_login_with_google_creates_new_user_when_email_missing(db_session) -> None:
    service = AuthService()

    result = service.login_with_google(
        db_session,
        identity=GoogleIdentity(
            sub="google-sub-456",
            email="new@example.com",
            email_verified=True,
            name="New User",
            picture="https://example.com/new-avatar.png",
        ),
    )

    assert result.user.email == "new@example.com"
    assert result.user.google_sub == "google-sub-456"
    assert result.user.display_name == "New User"
    assert result.user.avatar_url == "https://example.com/new-avatar.png"
    assert result.is_new_user is True
