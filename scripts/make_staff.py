"""Promote a user to staff by email address.

Usage:
    docker compose run --rm app python scripts/make_staff.py user@example.com
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.db.models import User
from app.db.session import SessionLocal


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/make_staff.py <email>")
        return 1

    email = sys.argv[1].strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No user found with email: {email}")
            return 1
        user.is_staff = True
        db.commit()
        print(f"User {email} is now staff.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
