from __future__ import annotations

from dataclasses import dataclass
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthTokenError, create_access_token, decode_access_token, hash_password, verify_password
from app.db.models import User
from app.services.google_identity_service import GoogleIdentity


@dataclass(slots=True)
class AuthResult:
    access_token: str
    token_type: str
    user: User
    is_new_user: bool = False


class AuthService:
    def register(self, db: Session, *, email: str, password: str) -> AuthResult:
        normalized_email = _normalize_email(email)
        existing_user = db.scalar(select(User).where(User.email == normalized_email))
        if existing_user is not None:
            raise ValueError("email_already_registered")

        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
        return self._result_for_user(user)

    def login(self, db: Session, *, email: str, password: str) -> AuthResult:
        normalized_email = _normalize_email(email)
        user = db.scalar(select(User).where(User.email == normalized_email))
        if user is None or not verify_password(password, user.password_hash):
            raise ValueError("invalid_credentials")
        return self._result_for_user(user)

    def get_user_by_id(self, db: Session, user_id: UUID) -> User | None:
        return db.get(User, user_id)

    def login_with_google(self, db: Session, *, identity: GoogleIdentity) -> AuthResult:
        existing_user = db.scalar(select(User).where(User.email == identity.email))

        if existing_user is not None:
            if existing_user.google_sub is not None and existing_user.google_sub != identity.sub:
                raise ValueError("google_account_mismatch")
            existing_user.google_sub = identity.sub
            if identity.name:
                existing_user.display_name = identity.name
            if identity.picture:
                existing_user.avatar_url = identity.picture
            db.flush()
            return self._result_for_user(existing_user)

        user = User(
            email=identity.email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            google_sub=identity.sub,
            display_name=identity.name,
            avatar_url=identity.picture,
        )
        db.add(user)
        db.flush()
        return self._result_for_user(user, is_new_user=True)

    def get_user_by_token(self, db: Session, token: str) -> User:
        try:
            payload = decode_access_token(token)
        except AuthTokenError as exc:
            raise ValueError(str(exc)) from exc

        try:
            user_id = UUID(str(payload["sub"]))
        except ValueError as exc:
            raise ValueError("invalid_token") from exc

        user = self.get_user_by_id(db, user_id)
        if user is None:
            raise ValueError("invalid_token")
        return user

    def _result_for_user(self, user: User, *, is_new_user: bool = False) -> AuthResult:
        return AuthResult(
            access_token=create_access_token(user_id=user.id, email=user.email),
            token_type="bearer",
            user=user,
            is_new_user=is_new_user,
        )


def _normalize_email(email: str) -> str:
    return email.strip().lower()
