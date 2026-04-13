from __future__ import annotations

import pytest

from app.services.google_identity_service import GoogleIdentityService


def test_verify_id_token_rejects_invalid_token(monkeypatch) -> None:
    service = GoogleIdentityService()
    monkeypatch.setattr("app.services.google_identity_service.settings.google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(service, "_fetch_tokeninfo", lambda id_token: (_ for _ in ()).throw(ValueError("invalid_google_token")))

    with pytest.raises(ValueError, match="invalid_google_token"):
        service.verify_id_token("bad-token")


def test_verify_id_token_rejects_unverified_email(monkeypatch) -> None:
    service = GoogleIdentityService()
    monkeypatch.setattr("app.services.google_identity_service.settings.google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(
        service,
        "_fetch_tokeninfo",
        lambda id_token: {
            "aud": "client-id.apps.googleusercontent.com",
            "sub": "google-sub",
            "email": "reviewer@example.com",
            "email_verified": "false",
        },
    )

    with pytest.raises(ValueError, match="google_email_not_verified"):
        service.verify_id_token("token")


def test_verify_id_token_rejects_missing_email(monkeypatch) -> None:
    service = GoogleIdentityService()
    monkeypatch.setattr("app.services.google_identity_service.settings.google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(
        service,
        "_fetch_tokeninfo",
        lambda id_token: {
            "aud": "client-id.apps.googleusercontent.com",
            "sub": "google-sub",
            "email_verified": "true",
        },
    )

    with pytest.raises(ValueError, match="google_email_missing"):
        service.verify_id_token("token")
