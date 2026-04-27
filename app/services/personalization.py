from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
from typing import Iterable

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Deal, SavedDeal, User, UserCategorySignal, UserEvent
from app.services.deal_service import DealQueryService, DealRecord
from app.services.product_analytics_service import (
    EVENT_DEAL_CLICK,
    EVENT_DEAL_IMPRESSION,
    EVENT_RECOMMENDED_DEAL_CLICK,
    EVENT_RECOMMENDED_DEAL_IMPRESSION,
)
from app.services.user_preferences_service import UserPreferencesService

CATEGORY_PRIORITY = ["Tech", "Gaming", "Home", "Fitness", "Lifestyle"]
LEGACY_CATEGORY_ALIASES = {
    "audio": "Tech",
    "pets": "Lifestyle",
    "kids": "Lifestyle",
}

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Tech": (
        "tech",
        "electronics",
        "electrónica",
        "audio",
        "headphone",
        "headphones",
        "earbuds",
        "auriculares",
        "speaker",
        "speakers",
        "altavoz",
        "soundbar",
        "microphone",
        "phone",
        "phones",
        "iphone",
        "smartphone",
        "tablet",
        "laptop",
        "ordenador",
        "computer",
        "monitor",
        "router",
        "network",
        "usb",
        "ssd",
        "storage",
        "wearable",
        "smart home",
        "camera",
        "security camera",
        "xiaomi",
        "anker",
        "logitech",
        "sony",
        "apple",
        "samsung",
    ),
    "Gaming": (
        "gaming",
        "game",
        "xbox",
        "playstation",
        "ps5",
        "nintendo",
        "switch",
        "controller",
        "console",
        "videojuego",
        "videojuegos",
        "steam",
        "gaming mouse",
        "gaming keyboard",
        "gaming headset",
    ),
    "Home": (
        "home",
        "hogar",
        "household",
        "kitchen",
        "cocina",
        "vacuum",
        "cleaning",
        "appliance",
        "furniture",
        "lighting",
        "garden",
        "jardín",
        "tool",
        "hardware",
        "cafetera",
        "freidora",
        "robot aspirador",
        "air fryer",
        "smart home",
        "thermostat",
    ),
    "Fitness": (
        "fitness",
        "gym",
        "exercise",
        "running",
        "training",
        "deporte",
        "sports",
        "workout",
        "yoga",
        "cycling",
        "bicicleta",
        "dumbbell",
        "treadmill",
        "protein shaker",
    ),
    "Lifestyle": (
        "lifestyle",
        "beauty",
        "travel",
        "fashion",
        "pet",
        "pets",
        "dog",
        "cat",
        "mascota",
        "mascotas",
        "perro",
        "gato",
        "pet food",
        "litter",
        "baby",
        "kids",
        "kid",
        "child",
        "children",
        "toddler",
        "niño",
        "niña",
        "bebé",
        "toy",
        "toys",
        "juguete",
        "lego",
        "stroller",
        "school",
    ),
}

SUBCATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "headphones": ("headphone", "headphones", "earbuds", "auriculares", "headset"),
    "smart_home": ("smart home", "security camera", "camera", "router", "alexa", "thermostat"),
    "storage": ("ssd", "storage", "usb", "micro sd", "external drive"),
    "speakers": ("speaker", "speakers", "altavoz", "soundbar"),
    "gaming_accessories": ("controller", "gaming mouse", "gaming keyboard", "gaming headset"),
    "consoles": ("xbox", "playstation", "ps5", "nintendo switch", "console"),
    "kitchen": ("kitchen", "cocina", "cafetera", "freidora", "air fryer"),
    "cleaning": ("vacuum", "cleaning", "robot aspirador", "air purifier"),
    "home_improvement": ("lighting", "tool", "hardware", "drill", "screwdriver"),
    "wearables": ("wearable", "smartwatch", "watch", "tracker"),
    "sports_equipment": ("dumbbell", "treadmill", "exercise bike", "yoga mat"),
    "pet_care": ("pet", "mascota", "dog", "cat", "litter", "pet food"),
    "baby_kids": ("baby", "kids", "kid", "child", "children", "toddler", "stroller", "toy", "lego"),
    "beauty_personal_care": ("beauty", "skincare", "makeup", "grooming", "perfume"),
    "travel_accessories": ("travel", "backpack", "luggage", "suitcase"),
}

BRAND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Tech": ("apple", "samsung", "xiaomi", "anker", "logitech", "sony", "tp-link", "philips hue"),
    "Gaming": ("playstation", "xbox", "nintendo", "razer", "logitech g", "steelseries"),
    "Home": ("dyson", "roborock", "cecotec", "philips", "tefal", "de'longhi"),
    "Fitness": ("garmin", "fitbit", "polar", "under armour", "adidas", "nike"),
    "Lifestyle": ("lego", "fisher-price", "chicco", "purina", "royal canin", "nivea"),
}

CONTEXT_CATEGORY_MAP = {
    "has_pets": {"Lifestyle"},
    "has_kids": {"Lifestyle"},
}

INTENT_CATEGORY_MAP = {
    "discover_products": {"Tech", "Gaming"},
    "upgrade_life": {"Tech", "Home", "Fitness", "Lifestyle"},
    "practical": {"Home", "Lifestyle"},
}

MAX_AFFINITY_SCORE = Decimal("5.0000")
MIN_AFFINITY_SCORE = Decimal("-2.0000")
MAX_NEGATIVE_AFFINITY = Decimal("3.0000")
CLICK_AFFINITY_DELTA = Decimal("0.4500")
SAVE_AFFINITY_DELTA = Decimal("1.1500")
NEGATIVE_AFFINITY_DELTA = Decimal("0.1500")
TITLE_STOPWORDS = {
    "and",
    "con",
    "de",
    "del",
    "el",
    "en",
    "for",
    "la",
    "los",
    "para",
    "the",
    "un",
    "una",
    "y",
}
RECENT_SEEN_WINDOW = timedelta(hours=24)
RECENT_SAVED_WINDOW = timedelta(days=45)
RECENT_MEMORY_MAX_ITEMS = 40


@dataclass(frozen=True, slots=True)
class PersonalizationWeights:
    # Explicit choices are the clearest signal during cold start.
    explicit_category_match: float = 24.0
    # Saved-deal categories matter, but less than direct profile choices.
    saved_category_match: float = 12.0
    # Learned behavior should matter most once it exists.
    behavioral_affinity_unit: float = 10.0
    # Negative behavior should down-rank, not completely hide.
    negative_affinity_penalty: float = 6.0
    # Life context is a targeted but secondary boost.
    life_context_match: float = 10.0
    # Budget helps steer choices without dominating the feed.
    budget_alignment: float = 8.0
    # Discounts remain core to the product.
    savings_strength: float = 14.0
    # Quality score gives the default feed a strong “trending” signal.
    quality_score: float = 8.0
    # Recency keeps fresh opportunities near the top.
    recency_boost: float = 6.0
    # Intent nudges tie-breaks without acting like a separate model.
    intent_match: float = 6.0
    # Freshly published deals should briefly stand out in the comeback loop.
    new_deal_boost: float = 9.0
    # Stale categories cool down if the user stops interacting with them.
    implicit_ignore_penalty: float = 7.0
    # Diversity penalties reduce “samey” streaks without hiding the strongest deals.
    same_category_penalty: float = 12.0
    repeated_subcategory_penalty: float = 3.5
    similar_title_penalty: float = 4.0
    # Exploration should be noticeable but still weaker than a true match.
    exploration_bonus: float = 6.0
    # Small stable jitter keeps the feed from feeling frozen.
    randomness_jitter: float = 0.45
    recent_seen_asin_penalty: float = 80.0
    recent_seen_category_penalty: float = 8.0
    recent_seen_subcategory_penalty: float = 3.0
    saved_similarity_boost: float = 7.0
    saved_subcategory_boost: float = 2.5


DEFAULT_PERSONALIZATION_WEIGHTS = PersonalizationWeights()


@dataclass(frozen=True, slots=True)
class DealAttributes:
    category: str | None
    subcategories: tuple[str, ...]
    intent_tags: tuple[str, ...]
    asin: str | None


@dataclass(frozen=True, slots=True)
class PersonalizationProfile:
    categories: tuple[str, ...]
    seed_categories: tuple[str, ...]
    budget_preference: str | None
    intent: tuple[str, ...]
    has_pets: bool
    has_kids: bool
    context_flags: dict[str, bool]
    category_affinity: dict[str, float]
    saved_count_by_category: dict[str, int]
    clicked_count_by_category: dict[str, int]
    negative_affinity: dict[str, float]
    last_interacted_at_by_category: dict[str, datetime | None]
    recent_seen_asins: tuple[str, ...] = ()
    recent_seen_category_counts: dict[str, int] = field(default_factory=dict)
    recent_seen_subcategory_counts: dict[str, int] = field(default_factory=dict)
    recent_saved_asins: tuple[str, ...] = ()
    recent_saved_categories: dict[str, int] = field(default_factory=dict)
    recent_saved_subcategory_counts: dict[str, int] = field(default_factory=dict)

    @property
    def has_personalization(self) -> bool:
        return bool(
            self.categories
            or self.seed_categories
            or self.intent
            or self.has_pets
            or self.has_kids
            or any(abs(score) > 0 for score in self.category_affinity.values())
        )


@dataclass(frozen=True, slots=True)
class DealPersonalizationScore:
    total_score: float
    explicit_match: float
    behavior_match: float
    life_context_match: float
    budget_alignment: float
    savings_strength: float
    recency_boost: float
    quality_score: float
    intent_match: float
    negative_penalty: float
    diversity_penalty: float = 0.0
    exploration_bonus: float = 0.0
    randomness_jitter: float = 0.0


@dataclass(frozen=True, slots=True)
class RankedDealCandidate:
    deal: DealRecord
    score: DealPersonalizationScore
    attributes: DealAttributes


class PersonalizationService:
    def __init__(self) -> None:
        self.user_preferences_service = UserPreferencesService()
        self.deal_query_service = DealQueryService()

    def load_profile(
        self,
        db: Session,
        *,
        user: User,
        seed_categories: Iterable[str] = (),
    ) -> PersonalizationProfile:
        t0 = time.perf_counter()

        t1 = time.perf_counter()
        preferences = self.user_preferences_service.get_preferences(db, user=user)
        logger.warning("perf_load_profile preferences=%.1fms", (time.perf_counter() - t1) * 1000)

        t1 = time.perf_counter()
        signal_models = db.scalars(
            select(UserCategorySignal).where(UserCategorySignal.user_id == user.id)
        ).all()
        logger.warning("perf_load_profile signals=%.1fms count=%d", (time.perf_counter() - t1) * 1000, len(signal_models))
        last_interacted_at_by_category = {
            signal.category: signal.last_interacted_at for signal in signal_models
        }

        t1 = time.perf_counter()
        recent_seen_asins, recent_seen_category_counts, recent_seen_subcategory_counts = self._load_recent_seen_memory(
            db,
            user=user,
        )
        logger.warning("perf_load_profile seen_memory=%.1fms asins=%d", (time.perf_counter() - t1) * 1000, len(recent_seen_asins))

        t1 = time.perf_counter()
        recent_saved_asins, recent_saved_categories, recent_saved_subcategory_counts = self._load_recent_saved_memory(
            db,
            user=user,
        )
        logger.warning("perf_load_profile saved_memory=%.1fms asins=%d", (time.perf_counter() - t1) * 1000, len(recent_saved_asins))

        logger.warning("perf_load_profile total=%.1fms", (time.perf_counter() - t0) * 1000)
        return PersonalizationProfile(
            categories=tuple(preferences.categories),
            seed_categories=tuple(sorted({category for category in seed_categories if category in CATEGORY_KEYWORDS})),
            budget_preference=preferences.budget_preference,
            intent=tuple(preferences.intent),
            has_pets=preferences.has_pets,
            has_kids=preferences.has_kids,
            context_flags=preferences.context_flags,
            category_affinity=preferences.category_affinity,
            saved_count_by_category=preferences.saved_count_by_category,
            clicked_count_by_category=preferences.clicked_count_by_category,
            negative_affinity=preferences.negative_affinity,
            last_interacted_at_by_category=last_interacted_at_by_category,
            recent_seen_asins=recent_seen_asins,
            recent_seen_category_counts=recent_seen_category_counts,
            recent_seen_subcategory_counts=recent_seen_subcategory_counts,
            recent_saved_asins=recent_saved_asins,
            recent_saved_categories=recent_saved_categories,
            recent_saved_subcategory_counts=recent_saved_subcategory_counts,
        )

    def rank_deals_for_user(
        self,
        deals: list[DealRecord],
        *,
        profile: PersonalizationProfile,
        now: datetime | None = None,
    ) -> list[DealRecord]:
        current_time = now or datetime.now(UTC)
        if not profile.has_personalization:
            return self.rank_default_feed(deals, now=current_time)

        scored: list[RankedDealCandidate] = []
        recent_seen_asins = set(profile.recent_seen_asins)
        for deal in deals:
            attributes = self.enrich_deal(deal)
            if attributes.asin and attributes.asin in recent_seen_asins:
                continue
            score = self.score_deal(profile=profile, deal=deal, attributes=attributes, now=current_time)
            applied_deal = self._apply_attributes(deal, attributes, score.total_score)
            scored.append(RankedDealCandidate(deal=applied_deal, score=score, attributes=attributes))
        return self._assemble_feed(
            scored,
            now=current_time,
            preferred_categories=set(profile.categories).union(profile.seed_categories),
            exploration_enabled=True,
        )

    def rank_default_feed(self, deals: list[DealRecord], *, now: datetime | None = None) -> list[DealRecord]:
        current_time = now or datetime.now(UTC)
        scored: list[RankedDealCandidate] = []
        for deal in deals:
            attributes = self.enrich_deal(deal)
            score = self._default_score(deal, now=current_time)
            applied_deal = self._apply_attributes(deal, attributes, score.total_score)
            scored.append(RankedDealCandidate(deal=applied_deal, score=score, attributes=attributes))
        return self._assemble_feed(scored, now=current_time)

    def rank_new_deals_for_user(
        self,
        deals: list[DealRecord],
        *,
        profile: PersonalizationProfile,
        now: datetime | None = None,
    ) -> list[DealRecord]:
        current_time = now or datetime.now(UTC)
        if not profile.has_personalization:
            return self.rank_default_new_feed(deals, now=current_time)

        scored: list[RankedDealCandidate] = []
        for deal in deals:
            attributes = self.enrich_deal(deal)
            base_score = self.score_deal(profile=profile, deal=deal, attributes=attributes, now=current_time)
            boosted_score = self._apply_new_deal_boost(base_score, deal=deal, now=current_time)
            applied_deal = self._apply_attributes(deal, attributes, boosted_score.total_score)
            scored.append(RankedDealCandidate(deal=applied_deal, score=boosted_score, attributes=attributes))
        return self._assemble_feed(
            scored,
            now=current_time,
            preferred_categories=set(profile.categories).union(profile.seed_categories),
            exploration_enabled=True,
        )

    def rank_default_new_feed(self, deals: list[DealRecord], *, now: datetime | None = None) -> list[DealRecord]:
        current_time = now or datetime.now(UTC)
        scored: list[RankedDealCandidate] = []
        for deal in deals:
            attributes = self.enrich_deal(deal)
            base_score = self._default_score(deal, now=current_time)
            boosted_score = self._apply_new_deal_boost(base_score, deal=deal, now=current_time)
            applied_deal = self._apply_attributes(deal, attributes, boosted_score.total_score)
            scored.append(RankedDealCandidate(deal=applied_deal, score=boosted_score, attributes=attributes))
        return self._assemble_feed(scored, now=current_time)

    def enrich_deal(self, deal: DealRecord) -> DealAttributes:
        text = self._build_deal_text(deal)
        category = self._infer_category(deal, text)
        subcategories = self._infer_subcategories(text)
        intent_tags = self._infer_intent_tags(deal, category, subcategories)
        return DealAttributes(
            category=category,
            subcategories=subcategories,
            intent_tags=intent_tags,
            asin=deal.asin,
        )

    def score_deal(
        self,
        *,
        profile: PersonalizationProfile,
        deal: DealRecord,
        attributes: DealAttributes,
        now: datetime,
        weights: PersonalizationWeights = DEFAULT_PERSONALIZATION_WEIGHTS,
    ) -> DealPersonalizationScore:
        category = attributes.category
        recent_saved_asins = set(profile.recent_saved_asins)
        explicit_match = 0.0
        behavior_match = 0.0
        life_context_match = 0.0
        budget_alignment = self._budget_alignment_score(profile.budget_preference, deal) * weights.budget_alignment
        savings_strength = self._discount_strength_score(deal) * weights.savings_strength
        recency_boost = self._recency_score(deal, now) * weights.recency_boost
        quality_score = self._quality_score(deal) * weights.quality_score
        intent_match = 0.0
        negative_penalty = 0.0
        similarity_boost = 0.0

        if category is not None:
            if category in profile.categories:
                explicit_match += weights.explicit_category_match
            elif category in profile.seed_categories:
                explicit_match += weights.saved_category_match

            affinity = self._decayed_signal(
                profile.category_affinity.get(category, 0.0),
                profile.last_interacted_at_by_category.get(category),
                now,
            )
            behavior_match += max(0.0, affinity) * weights.behavioral_affinity_unit
            negative_penalty += self._decayed_signal(
                profile.negative_affinity.get(category, 0.0),
                profile.last_interacted_at_by_category.get(category),
                now,
            ) * weights.negative_affinity_penalty
            negative_penalty += (
                self._implicit_ignore_penalty(profile=profile, category=category, now=now)
                * weights.implicit_ignore_penalty
            )

            recent_seen_count = profile.recent_seen_category_counts.get(category, 0)
            if recent_seen_count > 0:
                negative_penalty += min(recent_seen_count, 3) * weights.recent_seen_category_penalty

            if category in profile.recent_saved_categories and attributes.asin not in recent_saved_asins:
                similarity_boost += min(profile.recent_saved_categories.get(category, 0), 2) * weights.saved_similarity_boost

            if profile.has_pets and category in CONTEXT_CATEGORY_MAP["has_pets"]:
                life_context_match += weights.life_context_match
            if profile.has_kids and category in CONTEXT_CATEGORY_MAP["has_kids"]:
                life_context_match += weights.life_context_match

            for intent_value in profile.intent:
                if intent_value == "save_money":
                    if self._discount_strength_score(deal) >= 0.5:
                        intent_match += weights.intent_match
                elif category in INTENT_CATEGORY_MAP.get(intent_value, set()):
                    intent_match += weights.intent_match

        if attributes.asin and attributes.asin in set(profile.recent_seen_asins):
            negative_penalty += weights.recent_seen_asin_penalty

        repeated_recent_subcategories = sum(
            profile.recent_seen_subcategory_counts.get(subcategory, 0) for subcategory in attributes.subcategories
        )
        if repeated_recent_subcategories > 0:
            negative_penalty += min(repeated_recent_subcategories, 3) * weights.recent_seen_subcategory_penalty

        saved_subcategory_matches = sum(
            profile.recent_saved_subcategory_counts.get(subcategory, 0) for subcategory in attributes.subcategories
        )
        if saved_subcategory_matches > 0 and attributes.asin not in recent_saved_asins:
            similarity_boost += min(saved_subcategory_matches, 2) * weights.saved_subcategory_boost

        total = (
            explicit_match
            + behavior_match
            + life_context_match
            + budget_alignment
            + savings_strength
            + recency_boost
            + quality_score
            + intent_match
            + similarity_boost
            - negative_penalty
        )

        return DealPersonalizationScore(
            total_score=round(total, 4),
            explicit_match=round(explicit_match, 4),
            behavior_match=round(behavior_match, 4),
            life_context_match=round(life_context_match, 4),
            budget_alignment=round(budget_alignment, 4),
            savings_strength=round(savings_strength, 4),
            recency_boost=round(recency_boost, 4),
            quality_score=round(quality_score + similarity_boost, 4),
            intent_match=round(intent_match, 4),
            negative_penalty=round(negative_penalty, 4),
        )

    def record_click(self, db: Session, *, user: User, deal_id: object | Deal) -> None:
        deal = self._resolve_deal(db, deal_id)
        if deal is None:
            raise ValueError("deal_not_found")
        attributes = self.enrich_deal(deal)
        if attributes.category is None:
            return
        self._update_signal(
            db,
            user=user,
            category=attributes.category,
            affinity_delta=CLICK_AFFINITY_DELTA,
            clicked_delta=1,
        )

    def record_save(self, db: Session, *, user: User, deal_id: object | Deal) -> None:
        deal = self._resolve_deal(db, deal_id)
        if deal is None:
            raise ValueError("deal_not_found")
        attributes = self.enrich_deal(deal)
        if attributes.category is None:
            return
        self._update_signal(
            db,
            user=user,
            category=attributes.category,
            affinity_delta=SAVE_AFFINITY_DELTA,
            saved_delta=1,
        )

    def _resolve_deal(self, db: Session, deal_id: object | Deal) -> DealRecord | None:
        if isinstance(deal_id, Deal):
            return self.deal_query_service._to_record(deal_id)
        return self.deal_query_service.get_deal(db, deal_id)

    def _update_signal(
        self,
        db: Session,
        *,
        user: User,
        category: str,
        affinity_delta: Decimal = Decimal("0"),
        negative_delta: Decimal = Decimal("0"),
        saved_delta: int = 0,
        clicked_delta: int = 0,
    ) -> None:
        signal = db.scalar(
            select(UserCategorySignal).where(
                UserCategorySignal.user_id == user.id,
                UserCategorySignal.category == category,
            )
        )
        now = datetime.now(UTC)
        if signal is None:
            signal = UserCategorySignal(user_id=user.id, category=category)
            db.add(signal)
            db.flush()

        current_affinity = Decimal(signal.affinity_score)
        current_negative = Decimal(signal.negative_affinity)
        if signal.last_interacted_at is not None:
            decay_factor = Decimal(str(self._time_decay_factor(signal.last_interacted_at, now)))
            current_affinity *= decay_factor
            current_negative *= decay_factor

        signal.affinity_score = min(MAX_AFFINITY_SCORE, max(MIN_AFFINITY_SCORE, current_affinity + affinity_delta))
        signal.negative_affinity = min(MAX_NEGATIVE_AFFINITY, max(Decimal("0"), current_negative + negative_delta))
        signal.saved_count = max(0, signal.saved_count + saved_delta)
        signal.clicked_count = max(0, signal.clicked_count + clicked_delta)
        signal.last_interacted_at = now
        db.add(signal)
        db.flush()

    def _assemble_feed(
        self,
        scored: list[RankedDealCandidate],
        *,
        now: datetime,
        preferred_categories: set[str] | None = None,
        exploration_enabled: bool = False,
    ) -> list[DealRecord]:
        deduped: dict[str, RankedDealCandidate] = {}
        for candidate in scored:
            key = self._dedupe_key(candidate.deal)
            existing = deduped.get(key)
            if existing is None or self._rank_key(candidate.deal, candidate.score, now) > self._rank_key(
                existing.deal, existing.score, now
            ):
                deduped[key] = candidate

        ordered = sorted(
            deduped.values(),
            key=lambda candidate: self._rank_key(candidate.deal, candidate.score, now),
            reverse=True,
        )
        return self._apply_diversity_and_exploration(
            ordered,
            now=now,
            preferred_categories=preferred_categories or set(),
            exploration_enabled=exploration_enabled,
        )

    def _load_recent_seen_memory(
        self,
        db: Session,
        *,
        user: User,
    ) -> tuple[tuple[str, ...], dict[str, int], dict[str, int]]:
        since = datetime.now(UTC) - RECENT_SEEN_WINDOW
        event_types = (
            EVENT_DEAL_IMPRESSION,
            EVENT_RECOMMENDED_DEAL_IMPRESSION,
            EVENT_DEAL_CLICK,
            EVENT_RECOMMENDED_DEAL_CLICK,
        )
        event_rows = db.execute(
            select(UserEvent.deal_id)
            .where(
                UserEvent.user_id == user.id,
                UserEvent.event_type.in_(event_types),
                UserEvent.deal_id.is_not(None),
                UserEvent.created_at >= since,
            )
            .order_by(UserEvent.created_at.desc())
            .limit(RECENT_MEMORY_MAX_ITEMS)
        ).all()
        deal_ids = [row[0] for row in event_rows if row[0] is not None]
        return self._memory_from_deal_ids(db, deal_ids=deal_ids)

    def _load_recent_saved_memory(
        self,
        db: Session,
        *,
        user: User,
    ) -> tuple[tuple[str, ...], dict[str, int], dict[str, int]]:
        since = datetime.now(UTC) - RECENT_SAVED_WINDOW
        rows = db.execute(
            select(SavedDeal.deal_id)
            .where(
                SavedDeal.user_id == user.id,
                SavedDeal.created_at >= since,
            )
            .order_by(SavedDeal.created_at.desc())
            .limit(RECENT_MEMORY_MAX_ITEMS)
        ).all()
        deal_ids = [row[0] for row in rows if row[0] is not None]
        return self._memory_from_deal_ids(db, deal_ids=deal_ids)

    def _memory_from_deal_ids(
        self,
        db: Session,
        *,
        deal_ids: list[object],
    ) -> tuple[tuple[str, ...], dict[str, int], dict[str, int]]:
        seen_asins: list[str] = []
        category_counts: dict[str, int] = {}
        subcategory_counts: dict[str, int] = {}
        seen_asin_set: set[str] = set()

        if not deal_ids:
            return tuple(seen_asins), category_counts, subcategory_counts

        # Batch fetch — one query instead of one per deal_id
        deal_map = {deal.id: deal for deal in self.deal_query_service.get_deals_by_ids(db, deal_ids)}

        for deal_id in deal_ids:
            deal = deal_map.get(deal_id)
            if deal is None:
                continue
            attributes = self.enrich_deal(deal)
            if attributes.asin and attributes.asin not in seen_asin_set:
                seen_asins.append(attributes.asin)
                seen_asin_set.add(attributes.asin)
            if attributes.category:
                category_counts[attributes.category] = category_counts.get(attributes.category, 0) + 1
            for subcategory in attributes.subcategories:
                subcategory_counts[subcategory] = subcategory_counts.get(subcategory, 0) + 1

        return tuple(seen_asins), category_counts, subcategory_counts

    def _apply_diversity_and_exploration(
        self,
        ordered: list[RankedDealCandidate],
        *,
        now: datetime,
        preferred_categories: set[str],
        exploration_enabled: bool,
        weights: PersonalizationWeights = DEFAULT_PERSONALIZATION_WEIGHTS,
    ) -> list[DealRecord]:
        if not ordered:
            return []

        selected: list[RankedDealCandidate] = []
        remaining = list(ordered)
        exploration_target = 0
        if exploration_enabled and preferred_categories:
            exploration_candidates = [candidate for candidate in remaining if self._is_exploration_candidate(candidate, preferred_categories)]
            if exploration_candidates:
                exploration_target = max(1, min(len(exploration_candidates), round(len(ordered) * 0.15)))

        while remaining:
            remaining_slots = len(remaining)
            must_explore = (
                exploration_enabled
                and preferred_categories
                and exploration_target > self._selected_exploration_count(selected, preferred_categories)
                and (len(selected) + (exploration_target - self._selected_exploration_count(selected, preferred_categories)) >= len(ordered) - remaining_slots + exploration_target)
            )

            best_index = 0
            best_adjusted_score = float("-inf")
            for index, candidate in enumerate(remaining):
                adjusted = self._adjusted_feed_score(
                    candidate,
                    selected=selected,
                    remaining=remaining,
                    now=now,
                    preferred_categories=preferred_categories,
                    exploration_enabled=exploration_enabled,
                    exploration_target=exploration_target,
                    must_explore=must_explore,
                    weights=weights,
                )
                if adjusted > best_adjusted_score:
                    best_adjusted_score = adjusted
                    best_index = index

            chosen = remaining.pop(best_index)
            chosen_adjusted = self._adjusted_feed_score(
                chosen,
                selected=selected,
                remaining=remaining,
                now=now,
                preferred_categories=preferred_categories,
                exploration_enabled=exploration_enabled,
                exploration_target=exploration_target,
                must_explore=must_explore,
                weights=weights,
            )
            selected.append(
                RankedDealCandidate(
                    deal=replace(chosen.deal, personalization_score=round(chosen_adjusted, 4)),
                    score=replace(chosen.score, total_score=round(chosen_adjusted, 4)),
                    attributes=chosen.attributes,
                )
            )

        return [candidate.deal for candidate in selected]

    def _adjusted_feed_score(
        self,
        candidate: RankedDealCandidate,
        *,
        selected: list[RankedDealCandidate],
        remaining: list[RankedDealCandidate],
        now: datetime,
        preferred_categories: set[str],
        exploration_enabled: bool,
        exploration_target: int,
        must_explore: bool,
        weights: PersonalizationWeights,
    ) -> float:
        base_total = candidate.score.total_score
        diversity_penalty = self._diversity_penalty(
            candidate,
            selected=selected,
            remaining=remaining,
            weights=weights,
        )
        exploration_bonus = 0.0
        if (
            exploration_enabled
            and preferred_categories
            and exploration_target > self._selected_exploration_count(selected, preferred_categories)
            and self._is_exploration_candidate(candidate, preferred_categories)
        ):
            exploration_bonus = self._exploration_bonus(candidate, selected=selected, weights=weights)
            if must_explore:
                exploration_bonus += weights.exploration_bonus
        randomness_jitter = self._controlled_randomness(candidate.deal, now) * weights.randomness_jitter
        return round(base_total - diversity_penalty + exploration_bonus + randomness_jitter, 4)

    def _diversity_penalty(
        self,
        candidate: RankedDealCandidate,
        *,
        selected: list[RankedDealCandidate],
        remaining: list[RankedDealCandidate],
        weights: PersonalizationWeights,
    ) -> float:
        if not selected:
            return 0.0

        penalty = 0.0
        consecutive_category_count = 0
        for previous in reversed(selected):
            if previous.attributes.category and previous.attributes.category == candidate.attributes.category:
                consecutive_category_count += 1
            else:
                break

        if consecutive_category_count >= 1:
            penalty += weights.same_category_penalty * consecutive_category_count
            if self._has_alternative_category(candidate, remaining=remaining):
                penalty += weights.same_category_penalty

        recent_subcategories = [subcategory for previous in selected[-3:] for subcategory in previous.attributes.subcategories]
        repeated_subcategories = sum(1 for subcategory in candidate.attributes.subcategories if subcategory in recent_subcategories)
        penalty += repeated_subcategories * weights.repeated_subcategory_penalty

        if self._titles_are_similar(candidate.deal.title, selected[-1].deal.title):
            penalty += weights.similar_title_penalty

        return penalty

    def _has_alternative_category(
        self,
        candidate: RankedDealCandidate,
        *,
        remaining: list[RankedDealCandidate],
    ) -> bool:
        current_category = candidate.attributes.category
        for alternative in remaining:
            if alternative.deal.id == candidate.deal.id:
                continue
            if alternative.attributes.category != current_category:
                return True
        return False

    def _exploration_bonus(
        self,
        candidate: RankedDealCandidate,
        *,
        selected: list[RankedDealCandidate],
        weights: PersonalizationWeights,
    ) -> float:
        bonus = weights.exploration_bonus
        if candidate.attributes.category and candidate.attributes.category not in {
            previous.attributes.category for previous in selected if previous.attributes.category
        }:
            bonus += 2.0
        bonus += self._discount_strength_score(candidate.deal) * 2.0
        bonus += self._quality_score(candidate.deal) * 1.5
        return bonus

    def _is_exploration_candidate(self, candidate: RankedDealCandidate, preferred_categories: set[str]) -> bool:
        category = candidate.attributes.category
        if category is None or category in preferred_categories:
            return False
        return self._discount_strength_score(candidate.deal) >= 0.35 or self._quality_score(candidate.deal) >= 0.7

    def _selected_exploration_count(
        self,
        selected: list[RankedDealCandidate],
        preferred_categories: set[str],
    ) -> int:
        return sum(1 for candidate in selected if self._is_exploration_candidate(candidate, preferred_categories))

    def _titles_are_similar(self, left: str, right: str) -> bool:
        left_tokens = self._title_tokens(left)
        right_tokens = self._title_tokens(right)
        if not left_tokens or not right_tokens:
            return False
        overlap = len(left_tokens & right_tokens)
        threshold = max(2, min(len(left_tokens), len(right_tokens)) // 2)
        return overlap >= threshold

    def _title_tokens(self, value: str) -> set[str]:
        cleaned = []
        token = []
        for char in value.lower():
            if char.isalnum():
                token.append(char)
                continue
            if token:
                cleaned.append("".join(token))
                token.clear()
        if token:
            cleaned.append("".join(token))
        return {item for item in cleaned if len(item) >= 3 and item not in TITLE_STOPWORDS}

    def _apply_attributes(self, deal: DealRecord, attributes: DealAttributes, personalization_score: float) -> DealRecord:
        return replace(
            deal,
            category=attributes.category or deal.category,
            subcategories=list(attributes.subcategories),
            personalization_score=personalization_score,
        )

    def _rank_key(
        self,
        deal: DealRecord,
        score: DealPersonalizationScore,
        now: datetime,
    ) -> tuple[float, float, float, float, float, str]:
        return (
            self._discount_strength_score(deal),
            self._popularity_score(deal),
            score.total_score,
            self._quality_score(deal),
            self._freshness_timestamp(deal, now),
            str(deal.id),
        )

    def _dedupe_key(self, deal: DealRecord) -> str:
        if deal.product_variant_id is not None:
            return f"variant:{deal.product_variant_id}"
        if deal.asin:
            return f"asin:{deal.asin}"
        return f"deal:{deal.id}"

    def _build_deal_text(self, deal: DealRecord) -> str:
        parts = [
            deal.title,
            deal.category,
            deal.source_category,
            " ".join(deal.subcategories),
        ]
        return " ".join(part.lower() for part in parts if isinstance(part, str) and part.strip())

    def _infer_category(self, deal: DealRecord, text: str) -> str | None:
        for raw_value in (deal.category, deal.source_category):
            normalized = self._normalize_category_value(raw_value)
            if normalized is not None:
                return normalized

        best_category: str | None = None
        best_score = 0.0
        for category in CATEGORY_PRIORITY:
            keyword_score = sum(1.0 for keyword in CATEGORY_KEYWORDS[category] if keyword in text)
            brand_score = sum(1.5 for brand in BRAND_KEYWORDS[category] if brand in text)
            score = keyword_score + brand_score
            if score > best_score:
                best_category = category
                best_score = score

        return best_category

    def _infer_subcategories(self, text: str) -> tuple[str, ...]:
        matched = [name for name, keywords in SUBCATEGORY_KEYWORDS.items() if any(keyword in text for keyword in keywords)]
        return tuple(sorted(matched))

    def _infer_intent_tags(
        self,
        deal: DealRecord,
        category: str | None,
        subcategories: tuple[str, ...],
    ) -> tuple[str, ...]:
        tags: set[str] = set()
        if self._discount_strength_score(deal) >= 0.5:
            tags.add("save_money")
        if category in {"Tech", "Gaming"}:
            tags.add("discover_products")
        if category in {"Home", "Tech", "Fitness", "Lifestyle"}:
            tags.add("upgrade_life")
        if category in {"Home", "Lifestyle"} or {"cleaning", "kitchen", "pet_care", "baby_kids"} & set(subcategories):
            tags.add("practical")
        return tuple(sorted(tags))

    def _normalize_category_value(self, raw_value: str | None) -> str | None:
        if raw_value is None:
            return None
        normalized = raw_value.strip().lower()
        if not normalized:
            return None
        aliased = LEGACY_CATEGORY_ALIASES.get(normalized, normalized)
        for category in CATEGORY_PRIORITY:
            if aliased == category.lower():
                return category
        for category in CATEGORY_PRIORITY:
            if any(keyword == normalized or keyword == aliased for keyword in CATEGORY_KEYWORDS[category]):
                return category
            if any(brand == normalized or brand == aliased for brand in BRAND_KEYWORDS[category]):
                return category
        return None

    def _discount_strength_score(self, deal: DealRecord) -> float:
        percent = _normalize_percent(deal.savings_percent)
        if percent is None or percent <= 0:
            return 0.0
        return min(percent / 40.0, 1.0)

    def _popularity_score(self, deal: DealRecord) -> float:
        price_history = deal.score_breakdown.get("price_history")
        if not isinstance(price_history, dict):
            return 0.0
        obs_90d = price_history.get("observation_count_90d") or 0
        obs_all_time = price_history.get("observation_count_all_time") or 0
        try:
            score = (min(float(obs_90d), 60.0) / 60.0) * 0.7 + (min(float(obs_all_time), 180.0) / 180.0) * 0.3
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(score, 1.0))

    def _quality_score(self, deal: DealRecord) -> float:
        quality = deal.score_breakdown.get("quality_score")
        if not isinstance(quality, (int, float)):
            return 0.0
        return max(0.0, min(float(quality) / 100.0, 1.0))

    def _recency_score(self, deal: DealRecord, now: datetime) -> float:
        freshness_hours = max(0.0, (now - self._freshness_datetime(deal)).total_seconds() / 3600)
        return max(0.0, 1.0 - min(freshness_hours / 168.0, 1.0))

    def _budget_alignment_score(self, budget_preference: str | None, deal: DealRecord) -> float:
        price = _to_float(deal.current_price)
        if price is None:
            return 0.25
        if budget_preference == "low":
            if price <= 40:
                return 1.0
            if price <= 80:
                return 0.55
            return 0.0
        if budget_preference == "medium":
            if 20 <= price <= 150:
                return 1.0
            if price <= 250:
                return 0.55
            return 0.15
        if budget_preference == "high":
            if price >= 80:
                return 1.0
            if price >= 40:
                return 0.55
            return 0.2
        return 0.5

    def _default_score(self, deal: DealRecord, *, now: datetime) -> DealPersonalizationScore:
        savings_strength = self._discount_strength_score(deal) * DEFAULT_PERSONALIZATION_WEIGHTS.savings_strength
        quality_score = self._quality_score(deal) * DEFAULT_PERSONALIZATION_WEIGHTS.quality_score
        recency_boost = self._recency_score(deal, now) * DEFAULT_PERSONALIZATION_WEIGHTS.recency_boost
        total = savings_strength + quality_score + recency_boost
        return DealPersonalizationScore(
            total_score=round(total, 4),
            explicit_match=0.0,
            behavior_match=0.0,
            life_context_match=0.0,
            budget_alignment=0.0,
            savings_strength=round(savings_strength, 4),
            recency_boost=round(recency_boost, 4),
            quality_score=round(quality_score, 4),
            intent_match=0.0,
            negative_penalty=0.0,
            diversity_penalty=0.0,
            exploration_bonus=0.0,
            randomness_jitter=0.0,
        )

    def _apply_new_deal_boost(
        self,
        score: DealPersonalizationScore,
        *,
        deal: DealRecord,
        now: datetime,
        weights: PersonalizationWeights = DEFAULT_PERSONALIZATION_WEIGHTS,
    ) -> DealPersonalizationScore:
        boost = self._new_deal_score(deal, now) * weights.new_deal_boost
        if boost <= 0:
            return score
        return replace(
            score,
            total_score=round(score.total_score + boost, 4),
            recency_boost=round(score.recency_boost + boost, 4),
        )

    def _freshness_datetime(self, deal: DealRecord) -> datetime:
        candidate = deal.published_at or deal.detected_at
        if isinstance(candidate, datetime):
            if candidate.tzinfo is None:
                return candidate.replace(tzinfo=UTC)
            return candidate.astimezone(UTC)
        return datetime.now(UTC)

    def freshness_datetime(self, deal: DealRecord) -> datetime:
        return self._freshness_datetime(deal)

    def _freshness_timestamp(self, deal: DealRecord, now: datetime) -> float:
        return max(0.0, (self._freshness_datetime(deal) - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds())

    def _new_deal_score(self, deal: DealRecord, now: datetime) -> float:
        published_at = self._freshness_datetime(deal)
        freshness_hours = max(0.0, (now - published_at).total_seconds() / 3600)
        return max(0.0, 1.0 - min(freshness_hours / 72.0, 1.0))

    def _implicit_ignore_penalty(
        self,
        *,
        profile: PersonalizationProfile,
        category: str,
        now: datetime,
    ) -> float:
        last_interaction = profile.last_interacted_at_by_category.get(category)
        if last_interaction is None:
            return 0.0
        total_interactions = profile.saved_count_by_category.get(category, 0) + profile.clicked_count_by_category.get(category, 0)
        if total_interactions <= 0:
            return 0.0
        interacted_at = last_interaction.astimezone(UTC) if last_interaction.tzinfo else last_interaction.replace(tzinfo=UTC)
        days_since = max(0.0, (now - interacted_at).total_seconds() / 86400)
        if days_since <= 5:
            return 0.0
        staleness = min((days_since - 5.0) / 21.0, 1.0)
        interaction_scale = min(total_interactions / 6.0, 1.0)
        return staleness * interaction_scale

    def _controlled_randomness(self, deal: DealRecord, now: datetime) -> float:
        day_bucket = now.strftime("%Y-%m-%d")
        digest = hashlib.sha256(f"{deal.id}:{day_bucket}".encode("utf-8")).hexdigest()
        normalized = int(digest[:8], 16) / 0xFFFFFFFF
        return (normalized * 2.0) - 1.0

    def _decayed_signal(self, value: float, last_interacted_at: datetime | None, now: datetime) -> float:
        if last_interacted_at is None:
            return value
        return value * self._time_decay_factor(last_interacted_at, now)

    def _time_decay_factor(self, last_interacted_at: datetime, now: datetime) -> float:
        interacted_at = last_interacted_at.astimezone(UTC) if last_interacted_at.tzinfo else last_interacted_at.replace(tzinfo=UTC)
        days_since = max(0.0, (now - interacted_at).total_seconds() / 86400)
        # A gentle daily decay keeps stale categories from dominating forever.
        return max(0.35, 0.985 ** days_since)


def infer_preference_categories_for_deal(deal: DealRecord) -> list[str]:
    service = PersonalizationService()
    attributes = service.enrich_deal(deal)
    if attributes.category is None:
        return []
    return [attributes.category]


def rank_deals_for_preferences(deals: list[DealRecord], preferred_categories: Iterable[str]) -> list[DealRecord]:
    service = PersonalizationService()
    profile = PersonalizationProfile(
        categories=tuple(category for category in preferred_categories if category in CATEGORY_KEYWORDS),
        seed_categories=(),
        budget_preference=None,
        intent=(),
        has_pets=False,
        has_kids=False,
        context_flags={},
        category_affinity={},
        saved_count_by_category={},
        clicked_count_by_category={},
        negative_affinity={},
        last_interacted_at_by_category={},
    )
    return service.rank_deals_for_user(deals, profile=profile)


def _normalize_percent(value: object) -> float | None:
    amount = _to_float(value)
    if amount is None:
        return None
    if abs(amount) <= 1:
        return amount * 100.0
    return amount


def _to_float(value: object) -> float | None:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
