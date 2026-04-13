from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import User, UserCategorySignal, UserPreference

PREFERENCE_OPTIONS = ["Tech", "Gaming", "Home", "Fitness", "Lifestyle"]
PREFERENCE_CANONICAL = {option.lower(): option for option in PREFERENCE_OPTIONS}
PREFERENCE_CANONICAL.update(
    {
        "audio": "Tech",
        "pets": "Lifestyle",
        "kids": "Lifestyle",
    }
)
BUDGET_PREFERENCE_OPTIONS = {"low", "medium", "high"}
INTENT_OPTIONS = {"save_money", "discover_products", "upgrade_life", "practical"}


@dataclass(slots=True)
class UserPreferencesRecord:
    categories: list[str] = field(default_factory=list)
    budget_preference: str | None = None
    intent: list[str] = field(default_factory=list)
    has_pets: bool = False
    has_kids: bool = False
    context_flags: dict[str, bool] = field(default_factory=dict)
    category_affinity: dict[str, float] = field(default_factory=dict)
    saved_count_by_category: dict[str, int] = field(default_factory=dict)
    clicked_count_by_category: dict[str, int] = field(default_factory=dict)
    negative_affinity: dict[str, float] = field(default_factory=dict)
    is_profile_initialized: bool = False


class UserPreferencesService:
    def get_preferences(self, db: Session, *, user: User) -> UserPreferencesRecord:
        preferences = self._get_model(db, user=user)
        signal_models = self._get_signal_models(db, user=user)
        if preferences is None:
            return self._record_from_models(None, signal_models)
        return self._record_from_models(preferences, signal_models)

    def save_preferences(
        self,
        db: Session,
        *,
        user: User,
        categories: list[str],
        budget_preference: str | None = None,
        intent: list[str] | None = None,
        has_pets: bool = False,
        has_kids: bool = False,
        context_flags: dict[str, Any] | None = None,
    ) -> UserPreferencesRecord:
        normalized_categories = _normalize_categories(categories)
        normalized_budget = _normalize_budget_preference(budget_preference)
        normalized_intent = _normalize_intent(intent or [])
        normalized_context_flags = _normalize_context_flags(context_flags or {})

        preferences = self._get_model(db, user=user)
        if preferences is None:
            preferences = UserPreference(
                user_id=user.id,
                categories=normalized_categories,
                budget_preference=normalized_budget,
                intent=normalized_intent,
                has_pets=has_pets,
                has_kids=has_kids,
                context_flags=normalized_context_flags,
            )
            db.add(preferences)
        else:
            preferences.categories = normalized_categories
            preferences.budget_preference = normalized_budget
            preferences.intent = normalized_intent
            preferences.has_pets = has_pets
            preferences.has_kids = has_kids
            preferences.context_flags = normalized_context_flags
            db.add(preferences)
        db.flush()
        signal_models = self._get_signal_models(db, user=user)
        return self._record_from_models(preferences, signal_models)

    def _get_model(self, db: Session, *, user: User) -> UserPreference | None:
        if user.preferences is not None:
            return user.preferences
        return db.query(UserPreference).filter(UserPreference.user_id == user.id).one_or_none()

    def _get_signal_models(self, db: Session, *, user: User) -> list[UserCategorySignal]:
        if getattr(user, "category_signals", None):
            return sorted(user.category_signals, key=lambda signal: signal.category)
        return (
            db.query(UserCategorySignal)
            .filter(UserCategorySignal.user_id == user.id)
            .order_by(UserCategorySignal.category.asc())
            .all()
        )

    def _record_from_models(
        self,
        preferences: UserPreference | None,
        signal_models: list[UserCategorySignal],
    ) -> UserPreferencesRecord:
        category_affinity: dict[str, float] = {}
        saved_count_by_category: dict[str, int] = {}
        clicked_count_by_category: dict[str, int] = {}
        negative_affinity: dict[str, float] = {}

        for signal in signal_models:
            category_affinity[signal.category] = float(signal.affinity_score)
            saved_count_by_category[signal.category] = signal.saved_count
            clicked_count_by_category[signal.category] = signal.clicked_count
            negative_affinity[signal.category] = float(signal.negative_affinity)

        if preferences is None:
            return UserPreferencesRecord(
                category_affinity=category_affinity,
                saved_count_by_category=saved_count_by_category,
                clicked_count_by_category=clicked_count_by_category,
                negative_affinity=negative_affinity,
                is_profile_initialized=False,
            )

        return UserPreferencesRecord(
            categories=_normalize_categories(preferences.categories),
            budget_preference=_normalize_budget_preference(preferences.budget_preference),
            intent=_normalize_intent(preferences.intent),
            has_pets=bool(preferences.has_pets),
            has_kids=bool(preferences.has_kids),
            context_flags=_normalize_context_flags(preferences.context_flags),
            category_affinity=category_affinity,
            saved_count_by_category=saved_count_by_category,
            clicked_count_by_category=clicked_count_by_category,
            negative_affinity=negative_affinity,
            is_profile_initialized=True,
        )


def _normalize_categories(categories: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for category in categories:
        cleaned = PREFERENCE_CANONICAL.get(category.strip().lower())
        if cleaned is None or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return normalized


def _normalize_budget_preference(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if cleaned in BUDGET_PREFERENCE_OPTIONS:
        return cleaned
    return None


def _normalize_intent(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip().lower()
        if cleaned not in INTENT_OPTIONS or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return normalized


def _normalize_context_flags(values: dict[str, Any]) -> dict[str, bool]:
    normalized: dict[str, bool] = {}
    for key, value in values.items():
        cleaned_key = str(key).strip().lower().replace(" ", "_")
        if not cleaned_key:
            continue
        if len(cleaned_key) > 64:
            cleaned_key = cleaned_key[:64]
        normalized[cleaned_key] = bool(value)
    return normalized
