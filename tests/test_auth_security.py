from uuid import uuid4

import pytest

from app.core.security import AuthTokenError, create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_round_trip() -> None:
    password_hash = hash_password("correct-password")

    assert password_hash != "correct-password"
    assert verify_password("correct-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_access_token_round_trip() -> None:
    user_id = uuid4()

    token = create_access_token(user_id=user_id, email="reviewer@example.com")
    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["email"] == "reviewer@example.com"


def test_invalid_signature_token_is_rejected() -> None:
    token = create_access_token(user_id=uuid4(), email="reviewer@example.com")
    header, payload, signature = token.split(".")
    tampered_token = ".".join([header, f"{payload}A", signature])

    with pytest.raises(AuthTokenError, match="invalid_token"):
        decode_access_token(tampered_token)
