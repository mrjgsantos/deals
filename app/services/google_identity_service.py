from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass(slots=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str | None = None
    picture: str | None = None


class GoogleIdentityService:
    def verify_id_token(self, id_token: str) -> GoogleIdentity:
        if settings.google_client_id is None or not settings.google_client_id.strip():
            raise ValueError("google_auth_not_configured")

        token = id_token.strip()
        if not token:
            raise ValueError("invalid_google_token")

        claims = self._fetch_tokeninfo(token)

        audience = str(claims.get("aud") or "").strip()
        if audience != settings.google_client_id:
            raise ValueError("invalid_google_token")

        email = str(claims.get("email") or "").strip().lower()
        if not email:
            raise ValueError("google_email_missing")

        email_verified = _to_bool(claims.get("email_verified"))
        if not email_verified:
            raise ValueError("google_email_not_verified")

        sub = str(claims.get("sub") or "").strip()
        if not sub:
            raise ValueError("invalid_google_token")

        name = _clean_optional_string(claims.get("name"))
        picture = _clean_optional_string(claims.get("picture"))

        return GoogleIdentity(
            sub=sub,
            email=email,
            email_verified=True,
            name=name,
            picture=picture,
        )

    def _fetch_tokeninfo(self, id_token: str) -> dict[str, object]:
        try:
            response = httpx.get(
                settings.google_tokeninfo_url,
                params={"id_token": id_token},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise ValueError("invalid_google_token") from exc

        if response.status_code != 200:
            raise ValueError("invalid_google_token")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("invalid_google_token") from exc

        if not isinstance(payload, dict):
            raise ValueError("invalid_google_token")

        return payload


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _clean_optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
