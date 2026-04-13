from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.db.enums import DealStatus, SourceType
from app.db.models import Deal, Source, User
from app.services.deal_service import DealQueryService, DealRecord
from app.services.personalization import PersonalizationProfile, PersonalizationService


def make_deal_record(**overrides) -> DealRecord:
    payload = {
        "id": uuid4(),
        "title": "Logitech monitor",
        "status": "published",
        "currency": "EUR",
        "current_price": Decimal("199.99"),
        "previous_price": Decimal("249.99"),
        "savings_amount": Decimal("50.00"),
        "savings_percent": Decimal("0.20"),
        "deal_url": "https://www.amazon.es/dp/B0TEST1234",
        "summary": "Useful deal",
        "source_id": uuid4(),
        "product_variant_id": None,
        "product_source_record_id": None,
        "detected_at": datetime(2026, 4, 11, 10, 0, tzinfo=UTC),
        "published_at": datetime(2026, 4, 11, 10, 5, tzinfo=UTC),
        "category": "Tech",
        "source_category": "Electronics",
        "subcategories": [],
        "asin": "B0TEST1234",
        "personalization_score": None,
        "score_breakdown": {
            "quality_score": 82,
            "quality_reasons": [],
            "business_score": 0,
            "business_reasons": [],
            "promotable": True,
            "fake_discount": False,
            "price_history": {
                "avg_30d": "249.99",
                "avg_90d": "239.99",
                "min_90d": "199.99",
                "max_90d": "279.99",
                "all_time_min": "199.99",
                "days_at_current_price": 1,
                "observation_count_30d": 18,
                "observation_count_90d": 36,
                "observation_count_all_time": 90,
            },
        },
        "ai_copy_draft": None,
    }
    payload.update(overrides)
    return DealRecord(**payload)


def test_personalization_service_prefers_explicit_and_behavioral_matches() -> None:
    service = PersonalizationService()
    profile = PersonalizationProfile(
        categories=("Tech",),
        seed_categories=(),
        budget_preference="medium",
        intent=("save_money",),
        has_pets=False,
        has_kids=False,
        context_flags={},
        category_affinity={"Tech": 1.5, "Home": 0.1},
        saved_count_by_category={"Tech": 2},
        clicked_count_by_category={"Tech": 4},
        negative_affinity={"Home": 0.5},
        last_interacted_at_by_category={"Tech": datetime(2026, 4, 10, 12, 0, tzinfo=UTC)},
    )
    now = datetime(2026, 4, 11, 12, 0, tzinfo=UTC)

    tech_deal = make_deal_record(title="Logitech monitor", category="Tech", savings_percent=Decimal("0.30"))
    home_deal = make_deal_record(
        title="Cordless vacuum",
        category="Home",
        deal_url="https://www.amazon.es/dp/B0TEST9999",
        asin="B0TEST9999",
        savings_percent=Decimal("0.18"),
    )

    ranked = service.rank_deals_for_user([home_deal, tech_deal], profile=profile, now=now)

    assert [deal.id for deal in ranked] == [tech_deal.id, home_deal.id]
    assert ranked[0].personalization_score is not None
    assert ranked[0].personalization_score > ranked[1].personalization_score


def test_personalization_service_uses_life_context_and_budget_alignment() -> None:
    service = PersonalizationService()
    profile = PersonalizationProfile(
        categories=(),
        seed_categories=(),
        budget_preference="low",
        intent=("practical",),
        has_pets=True,
        has_kids=False,
        context_flags={},
        category_affinity={"Lifestyle": 0.6},
        saved_count_by_category={},
        clicked_count_by_category={},
        negative_affinity={},
        last_interacted_at_by_category={"Lifestyle": datetime(2026, 4, 10, 10, 0, tzinfo=UTC)},
    )
    now = datetime(2026, 4, 11, 12, 0, tzinfo=UTC)

    pet_deal = make_deal_record(
        title="Pet feeder for cats",
        category="Lifestyle",
        current_price=Decimal("39.99"),
        previous_price=Decimal("59.99"),
        savings_amount=Decimal("20.00"),
        savings_percent=Decimal("0.33"),
        deal_url="https://www.amazon.es/dp/B0PET00001",
        asin="B0PET00001",
    )
    pricey_tech = make_deal_record(
        title="Premium gaming laptop",
        category="Tech",
        current_price=Decimal("999.99"),
        previous_price=Decimal("1199.99"),
        savings_amount=Decimal("200.00"),
        savings_percent=Decimal("0.17"),
        deal_url="https://www.amazon.es/dp/B0TECH0001",
        asin="B0TECH0001",
    )

    ranked = service.rank_deals_for_user([pricey_tech, pet_deal], profile=profile, now=now)

    assert [deal.id for deal in ranked] == [pet_deal.id, pricey_tech.id]


def test_personalization_service_dedupes_same_asin_to_best_ranked_record() -> None:
    service = PersonalizationService()
    profile = PersonalizationProfile(
        categories=("Tech",),
        seed_categories=(),
        budget_preference=None,
        intent=(),
        has_pets=False,
        has_kids=False,
        context_flags={},
        category_affinity={"Tech": 1.0},
        saved_count_by_category={},
        clicked_count_by_category={},
        negative_affinity={},
        last_interacted_at_by_category={"Tech": datetime(2026, 4, 11, 9, 0, tzinfo=UTC)},
    )
    now = datetime(2026, 4, 11, 12, 0, tzinfo=UTC)

    stronger = make_deal_record(
        title="Anker SSD",
        category="Tech",
        savings_percent=Decimal("0.35"),
        deal_url="https://www.amazon.es/dp/B0DUPL1111",
        asin="B0DUPL1111",
    )
    weaker = make_deal_record(
        title="Anker SSD old",
        category="Tech",
        savings_percent=Decimal("0.10"),
        deal_url="https://www.amazon.es/dp/B0DUPL1111",
        asin="B0DUPL1111",
        published_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
    )

    ranked = service.rank_deals_for_user([weaker, stronger], profile=profile, now=now)

    assert len(ranked) == 1
    assert ranked[0].id == stronger.id


def test_personalization_service_records_click_and_save_behavior(db_session) -> None:
    source = Source(name="Amazon ES", slug="amazon-es", source_type=SourceType.MARKETPLACE)
    user = User(email="signals@example.com", password_hash="hash")
    db_session.add_all([source, user])
    db_session.flush()

    deal = Deal(
        source_id=source.id,
        title="Logitech monitor",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("199.99"),
        previous_price=Decimal("249.99"),
        savings_amount=Decimal("50.00"),
        savings_percent=Decimal("0.20"),
        deal_url="https://www.amazon.es/dp/B0CLICK1111",
        published_at=datetime.now(UTC),
    )
    db_session.add(deal)
    db_session.flush()

    service = PersonalizationService()
    service.record_click(db_session, user=user, deal_id=deal.id)
    service.record_save(db_session, user=user, deal_id=deal.id)

    profile = service.load_profile(db_session, user=user)

    assert profile.clicked_count_by_category["Tech"] == 1
    assert profile.saved_count_by_category["Tech"] == 1
    assert profile.category_affinity["Tech"] > 1.0


def test_personalization_service_breaks_up_long_category_streaks() -> None:
    service = PersonalizationService()
    profile = PersonalizationProfile(
        categories=("Tech",),
        seed_categories=(),
        budget_preference="medium",
        intent=("discover_products",),
        has_pets=False,
        has_kids=False,
        context_flags={},
        category_affinity={"Tech": 1.6, "Home": 0.2},
        saved_count_by_category={"Tech": 3},
        clicked_count_by_category={"Tech": 5},
        negative_affinity={},
        last_interacted_at_by_category={"Tech": datetime(2026, 4, 11, 9, 0, tzinfo=UTC)},
    )
    now = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)

    deals = [
        make_deal_record(title="Logitech monitor", category="Tech", savings_percent=Decimal("0.32"), asin="B0TECH0001"),
        make_deal_record(title="Anker SSD", category="Tech", savings_percent=Decimal("0.31"), asin="B0TECH0002"),
        make_deal_record(title="Nintendo Switch controller", category="Gaming", source_category="Videojuegos", savings_percent=Decimal("0.18"), asin="B0GAME0001"),
        make_deal_record(title="Xiaomi tablet", category="Tech", savings_percent=Decimal("0.29"), asin="B0TECH0003"),
    ]

    ranked = service.rank_deals_for_user(deals, profile=profile, now=now)

    assert [deal.category for deal in ranked[:3]] != ["Tech", "Tech", "Tech"]
    assert "Gaming" in [deal.category for deal in ranked[:3]]


def test_personalization_service_maps_brand_and_keywords_into_new_category_tree() -> None:
    service = PersonalizationService()

    tech = service.enrich_deal(
        make_deal_record(
            title="Sony WH-1000XM5 headphones",
            category=None,
            source_category="Audio",
            subcategories=[],
        )
    )
    gaming = service.enrich_deal(
        make_deal_record(
            title="Nintendo Switch controller",
            category=None,
            source_category="Videojuegos",
            subcategories=[],
        )
    )
    lifestyle = service.enrich_deal(
        make_deal_record(
            title="Purina dog food pack",
            category=None,
            source_category=None,
            subcategories=[],
        )
    )

    assert tech.category == "Tech"
    assert "headphones" in tech.subcategories
    assert gaming.category == "Gaming"
    assert "gaming_accessories" in gaming.subcategories
    assert lifestyle.category == "Lifestyle"
    assert "pet_care" in lifestyle.subcategories


def test_personalization_service_injects_controlled_exploration() -> None:
    service = PersonalizationService()
    profile = PersonalizationProfile(
        categories=("Tech",),
        seed_categories=(),
        budget_preference="medium",
        intent=("discover_products",),
        has_pets=False,
        has_kids=False,
        context_flags={},
        category_affinity={"Tech": 1.8},
        saved_count_by_category={"Tech": 4},
        clicked_count_by_category={"Tech": 6},
        negative_affinity={},
        last_interacted_at_by_category={"Tech": datetime(2026, 4, 11, 9, 0, tzinfo=UTC)},
    )
    now = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)

    deals = [
        make_deal_record(title=f"Tech deal {index}", category="Tech", savings_percent=Decimal("0.24"), asin=f"B0TECH00{index}")
        for index in range(1, 6)
    ]
    exploration = make_deal_record(
        title="Cordless vacuum",
        category="Home",
        savings_percent=Decimal("0.34"),
        current_price=Decimal("129.99"),
        previous_price=Decimal("199.99"),
        savings_amount=Decimal("70.00"),
        asin="B0HOMEEXP1",
    )

    ranked = service.rank_deals_for_user(deals + [exploration], profile=profile, now=now)

    assert any(deal.id == exploration.id for deal in ranked[:5])


def test_personalization_service_stale_interest_cools_down_against_active_interest() -> None:
    service = PersonalizationService()
    now = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    profile = PersonalizationProfile(
        categories=(),
        seed_categories=(),
        budget_preference="medium",
        intent=(),
        has_pets=False,
        has_kids=False,
        context_flags={},
        category_affinity={"Tech": 1.5, "Home": 0.9},
        saved_count_by_category={"Tech": 4, "Home": 1},
        clicked_count_by_category={"Tech": 6, "Home": 1},
        negative_affinity={},
        last_interacted_at_by_category={
            "Tech": now - timedelta(days=30),
            "Home": now - timedelta(days=1),
        },
    )

    tech_deal = make_deal_record(title="Gaming monitor", category="Tech", savings_percent=Decimal("0.20"), asin="B0STALETE1")
    home_deal = make_deal_record(title="Robot vacuum", category="Home", savings_percent=Decimal("0.20"), asin="B0ACTIVE01")

    ranked = service.rank_deals_for_user([tech_deal, home_deal], profile=profile, now=now)

    assert [deal.id for deal in ranked] == [home_deal.id, tech_deal.id]


def test_default_ranking_prefers_discount_then_popularity() -> None:
    service = PersonalizationService()
    now = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)

    high_discount = make_deal_record(
        title="Anker charger",
        savings_percent=Decimal("0.35"),
        asin="B0HIGHDISC1",
        deal_url="https://www.amazon.es/dp/B0HIGHDISC1",
        score_breakdown={
            "quality_score": 70,
            "quality_reasons": [],
            "business_score": 0,
            "business_reasons": [],
            "promotable": True,
            "fake_discount": False,
            "price_history": {
                "avg_30d": "39.99",
                "avg_90d": "39.99",
                "min_90d": "24.99",
                "max_90d": "49.99",
                "all_time_min": "24.99",
                "days_at_current_price": 1,
                "observation_count_30d": 6,
                "observation_count_90d": 10,
                "observation_count_all_time": 18,
            },
        },
    )
    popular_lower_discount = make_deal_record(
        title="Logitech keyboard",
        savings_percent=Decimal("0.20"),
        asin="B0POPULAR01",
        deal_url="https://www.amazon.es/dp/B0POPULAR01",
        score_breakdown={
            "quality_score": 90,
            "quality_reasons": [],
            "business_score": 0,
            "business_reasons": [],
            "promotable": True,
            "fake_discount": False,
            "price_history": {
                "avg_30d": "99.99",
                "avg_90d": "95.99",
                "min_90d": "79.99",
                "max_90d": "109.99",
                "all_time_min": "79.99",
                "days_at_current_price": 1,
                "observation_count_30d": 40,
                "observation_count_90d": 60,
                "observation_count_all_time": 180,
            },
        },
    )

    ranked = service.rank_default_feed([popular_lower_discount, high_discount], now=now)

    assert [deal.id for deal in ranked] == [high_discount.id, popular_lower_discount.id]


def test_personalization_service_hides_recently_seen_same_asin() -> None:
    service = PersonalizationService()
    now = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    profile = PersonalizationProfile(
        categories=("Tech",),
        seed_categories=(),
        budget_preference="medium",
        intent=(),
        has_pets=False,
        has_kids=False,
        context_flags={},
        category_affinity={"Tech": 1.4},
        saved_count_by_category={},
        clicked_count_by_category={},
        negative_affinity={},
        last_interacted_at_by_category={"Tech": now - timedelta(hours=1)},
        recent_seen_asins=("B0SEEN0001",),
        recent_seen_category_counts={"Tech": 1},
    )

    seen_again = make_deal_record(title="Logitech monitor", asin="B0SEEN0001", deal_url="https://www.amazon.es/dp/B0SEEN0001")
    fresh_alternative = make_deal_record(
        title="Anker SSD",
        asin="B0FRESH001",
        deal_url="https://www.amazon.es/dp/B0FRESH001",
    )

    ranked = service.rank_deals_for_user([seen_again, fresh_alternative], profile=profile, now=now)

    assert [deal.id for deal in ranked] == [fresh_alternative.id]


def test_personalization_service_boosts_similar_to_saved_but_not_identical() -> None:
    service = PersonalizationService()
    now = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    profile = PersonalizationProfile(
        categories=(),
        seed_categories=(),
        budget_preference="medium",
        intent=(),
        has_pets=False,
        has_kids=False,
        context_flags={},
        category_affinity={"Tech": 0.6, "Home": 0.6},
        saved_count_by_category={},
        clicked_count_by_category={},
        negative_affinity={},
        last_interacted_at_by_category={"Tech": now - timedelta(days=1), "Home": now - timedelta(days=1)},
        recent_saved_asins=("B0SAVED001",),
        recent_saved_categories={"Tech": 1},
        recent_saved_subcategory_counts={"storage": 1},
    )

    similar = make_deal_record(
        title="Samsung Portable SSD",
        category="Tech",
        source_category="Electronics",
        asin="B0SIMILAR1",
        deal_url="https://www.amazon.es/dp/B0SIMILAR1",
        subcategories=["storage"],
        savings_percent=Decimal("0.18"),
    )
    unrelated = make_deal_record(
        title="Robot vacuum",
        category="Home",
        source_category="Home",
        asin="B0HOME0001",
        deal_url="https://www.amazon.es/dp/B0HOME0001",
        subcategories=["cleaning"],
        savings_percent=Decimal("0.18"),
    )

    ranked = service.rank_deals_for_user([unrelated, similar], profile=profile, now=now)

    assert [deal.id for deal in ranked] == [similar.id, unrelated.id]
