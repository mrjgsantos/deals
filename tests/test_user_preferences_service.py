from __future__ import annotations

from app.db.models import User, UserCategorySignal, UserPreference
from app.services.user_preferences_service import UserPreferencesService


def test_user_preferences_service_round_trips_rich_profile(db_session) -> None:
    user = User(email="prefs@example.com", password_hash="hash")
    db_session.add(user)
    db_session.flush()

    db_session.add(
        UserCategorySignal(
            user_id=user.id,
            category="Tech",
            affinity_score=1.75,
            saved_count=2,
            clicked_count=4,
            negative_affinity=0.25,
        )
    )
    db_session.flush()

    service = UserPreferencesService()

    result = service.save_preferences(
        db_session,
        user=user,
        categories=["tech", "Gaming", "Tech"],
        budget_preference="medium",
        intent=["save_money", "practical", "save_money"],
        has_pets=True,
        has_kids=False,
        context_flags={"Weekend shopper": True},
    )

    assert result.categories == ["Tech", "Gaming"]
    assert result.budget_preference == "medium"
    assert result.intent == ["save_money", "practical"]
    assert result.has_pets is True
    assert result.has_kids is False
    assert result.context_flags == {"weekend_shopper": True}
    assert result.category_affinity == {"Tech": 1.75}
    assert result.saved_count_by_category == {"Tech": 2}
    assert result.clicked_count_by_category == {"Tech": 4}
    assert result.negative_affinity == {"Tech": 0.25}
    assert result.is_profile_initialized is True


def test_user_preferences_service_returns_uninitialized_profile_when_missing(db_session) -> None:
    user = User(email="empty@example.com", password_hash="hash")
    db_session.add(user)
    db_session.flush()

    result = UserPreferencesService().get_preferences(db_session, user=user)

    assert result.categories == []
    assert result.intent == []
    assert result.budget_preference is None
    assert result.is_profile_initialized is False
    assert result.category_affinity == {}
    assert result.saved_count_by_category == {}
    assert result.clicked_count_by_category == {}
    assert result.negative_affinity == {}
