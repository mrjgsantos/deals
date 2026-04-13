from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import settings

PBKDF2_NAME = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390_000


class AuthTokenError(ValueError):
    pass


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_NAME}${PBKDF2_ITERATIONS}${_urlsafe_b64encode(salt)}${_urlsafe_b64encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        name, iterations_value, salt_value, digest_value = password_hash.split("$", maxsplit=3)
    except ValueError:
        return False

    if name != PBKDF2_NAME:
        return False

    try:
        iterations = int(iterations_value)
        salt = _urlsafe_b64decode(salt_value)
        expected_digest = _urlsafe_b64decode(digest_value)
    except (TypeError, ValueError):
        return False

    candidate_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate_digest, expected_digest)


def create_access_token(*, user_id: UUID, email: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.auth_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": int(expires_at.timestamp()),
    }
    signing_input = ".".join(
        [
            _urlsafe_b64encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
            _urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        ]
    )
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_urlsafe_b64encode(signature)}"


def decode_access_token(token: str) -> dict[str, str | int]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthTokenError("invalid_token")

    header_segment, payload_segment, signature_segment = parts
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    actual_signature = _urlsafe_b64decode(signature_segment)
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise AuthTokenError("invalid_token")

    try:
        payload = json.loads(_urlsafe_b64decode(payload_segment))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AuthTokenError("invalid_token") from exc

    if not isinstance(payload, dict):
        raise AuthTokenError("invalid_token")

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise AuthTokenError("invalid_token")
    if datetime.now(UTC).timestamp() >= exp:
        raise AuthTokenError("token_expired")

    sub = payload.get("sub")
    email = payload.get("email")
    if not isinstance(sub, str) or not sub.strip():
        raise AuthTokenError("invalid_token")
    if not isinstance(email, str) or not email.strip():
        raise AuthTokenError("invalid_token")

    return {"sub": sub, "email": email, "exp": exp}
