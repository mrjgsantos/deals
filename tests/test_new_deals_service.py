from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.enums import DealStatus, SourceType
from app.db.models import Deal, Source, User, UserEvent, UserPreference
from app.services.product_analytics_service import EVENT_DEAL_CLICK, EVENT_DEAL_IMPRESSION
from app.services.new_deals_service import NewDealsService


def test_new_deals_service_returns_unseen_published_deals_ranked_for_user(db_session) -> None:
    source = Source(name="Amazon ES", slug="amazon-es", source_type=SourceType.MARKETPLACE)
    user = User(
        email="newdeals@example.com",
        password_hash="hash",
        last_seen_deals_at=datetime(2026, 4, 11, 12, 0, tzinfo=UTC),
    )
    db_session.add_all([source, user])
    db_session.flush()

    db_session.add(
        UserPreference(
            user_id=user.id,
            categories=["Tech"],
            budget_preference="medium",
            intent=["save_money"],
            has_pets=False,
            has_kids=False,
            context_flags={},
        )
    )

    tech_new = Deal(
        source_id=source.id,
        title="Logitech monitor",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("199.99"),
        previous_price=Decimal("249.99"),
        savings_amount=Decimal("50.00"),
        savings_percent=Decimal("0.20"),
        deal_url="https://www.amazon.es/dp/B0TECH1111",
        published_at=datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
    )
    home_new = Deal(
        source_id=source.id,
        title="Cordless vacuum",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("149.99"),
        previous_price=Decimal("179.99"),
        savings_amount=Decimal("30.00"),
        savings_percent=Decimal("0.17"),
        deal_url="https://www.amazon.es/dp/B0HOME1111",
        published_at=datetime(2026, 4, 12, 11, 0, tzinfo=UTC),
    )
    old_deal = Deal(
        source_id=source.id,
        title="Older gaming deal",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("59.99"),
        previous_price=Decimal("79.99"),
        savings_amount=Decimal("20.00"),
        savings_percent=Decimal("0.25"),
        deal_url="https://www.amazon.es/dp/B0OLD11111",
        published_at=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([tech_new, home_new, old_deal])
    db_session.flush()

    result = NewDealsService().get_new_deals(db_session, user=user, now=datetime(2026, 4, 12, 12, 0, tzinfo=UTC))

    assert result.new_count == 2
    assert result.fallback_used is False
    assert [deal.id for deal in result.deals] == [tech_new.id, home_new.id]


def test_new_deals_service_falls_back_when_user_has_no_last_seen(db_session) -> None:
    source = Source(name="Amazon ES", slug="amazon-es", source_type=SourceType.MARKETPLACE)
    user = User(email="fallback@example.com", password_hash="hash")
    db_session.add_all([source, user])
    db_session.flush()

    db_session.add(
        UserPreference(
            user_id=user.id,
            categories=["Home"],
            budget_preference="medium",
            intent=["practical"],
            has_pets=False,
            has_kids=False,
            context_flags={},
        )
    )

    home_deal = Deal(
        source_id=source.id,
        title="Cordless vacuum",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("149.99"),
        previous_price=Decimal("179.99"),
        savings_amount=Decimal("30.00"),
        savings_percent=Decimal("0.17"),
        deal_url="https://www.amazon.es/dp/B0HOME2222",
        published_at=datetime(2026, 4, 12, 11, 0, tzinfo=UTC),
    )
    tech_deal = Deal(
        source_id=source.id,
        title="Logitech monitor",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("199.99"),
        previous_price=Decimal("249.99"),
        savings_amount=Decimal("50.00"),
        savings_percent=Decimal("0.20"),
        deal_url="https://www.amazon.es/dp/B0TECH2222",
        published_at=datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([home_deal, tech_deal])
    db_session.flush()

    result = NewDealsService().get_new_deals(db_session, user=user, now=datetime(2026, 4, 12, 12, 0, tzinfo=UTC))

    assert result.new_count == 0
    assert result.fallback_used is True
    assert result.deals[0].id == home_deal.id


def test_new_deals_service_marks_seen_timestamp(db_session) -> None:
    user = User(email="seen@example.com", password_hash="hash")
    db_session.add(user)
    db_session.flush()

    seen_at = datetime(2026, 4, 12, 9, 30, tzinfo=UTC)
    result = NewDealsService().mark_seen(db_session, user=user, seen_at=seen_at)

    assert result == seen_at
    assert user.last_seen_deals_at == seen_at


def test_new_deals_service_excludes_already_seen_and_clicked_new_deals(db_session) -> None:
    source = Source(name="Amazon ES", slug="amazon-es", source_type=SourceType.MARKETPLACE)
    user = User(
        email="seen-clicked@example.com",
        password_hash="hash",
        last_seen_deals_at=datetime(2026, 4, 11, 12, 0, tzinfo=UTC),
    )
    db_session.add_all([source, user])
    db_session.flush()

    db_session.add(
        UserPreference(
            user_id=user.id,
            categories=["Tech"],
            budget_preference="medium",
            intent=["save_money"],
            has_pets=False,
            has_kids=False,
            context_flags={},
        )
    )

    fresh_keep = Deal(
        source_id=source.id,
        title="Anker charger",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("29.99"),
        previous_price=Decimal("39.99"),
        savings_amount=Decimal("10.00"),
        savings_percent=Decimal("0.25"),
        deal_url="https://www.amazon.es/dp/B0KEEP1111",
        published_at=datetime(2026, 4, 12, 11, 0, tzinfo=UTC),
    )
    seen_new = Deal(
        source_id=source.id,
        title="Logitech monitor",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("199.99"),
        previous_price=Decimal("249.99"),
        savings_amount=Decimal("50.00"),
        savings_percent=Decimal("0.20"),
        deal_url="https://www.amazon.es/dp/B0SEEN1111",
        published_at=datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
    )
    clicked_new = Deal(
        source_id=source.id,
        title="Xiaomi tablet",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("159.99"),
        previous_price=Decimal("199.99"),
        savings_amount=Decimal("40.00"),
        savings_percent=Decimal("0.20"),
        deal_url="https://www.amazon.es/dp/B0CLICK111",
        published_at=datetime(2026, 4, 12, 9, 0, tzinfo=UTC),
    )
    db_session.add_all([fresh_keep, seen_new, clicked_new])
    db_session.flush()

    db_session.add_all(
        [
            UserEvent(user_id=user.id, event_type=EVENT_DEAL_IMPRESSION, deal_id=seen_new.id),
            UserEvent(user_id=user.id, event_type=EVENT_DEAL_CLICK, deal_id=clicked_new.id),
        ]
    )
    db_session.flush()

    result = NewDealsService().get_new_deals(db_session, user=user, now=datetime(2026, 4, 12, 12, 0, tzinfo=UTC))

    assert result.new_count == 1
    assert result.fallback_used is False
    assert [deal.id for deal in result.deals] == [fresh_keep.id]


def test_new_deals_service_fallback_uses_best_recent_items_in_profile_categories(db_session) -> None:
    source = Source(name="Amazon ES", slug="amazon-es", source_type=SourceType.MARKETPLACE)
    user = User(
        email="fallback-categories@example.com",
        password_hash="hash",
        last_seen_deals_at=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
    )
    db_session.add_all([source, user])
    db_session.flush()

    db_session.add(
        UserPreference(
            user_id=user.id,
            categories=["Tech"],
            budget_preference="medium",
            intent=["discover_products"],
            has_pets=False,
            has_kids=False,
            context_flags={},
        )
    )

    recent_tech = Deal(
        source_id=source.id,
        title="Sony earbuds",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("79.99"),
        previous_price=Decimal("109.99"),
        savings_amount=Decimal("30.00"),
        savings_percent=Decimal("0.27"),
        deal_url="https://www.amazon.es/dp/B0TECHFB01",
        published_at=datetime(2026, 4, 10, 11, 0, tzinfo=UTC),
    )
    recent_home = Deal(
        source_id=source.id,
        title="Cordless vacuum",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("149.99"),
        previous_price=Decimal("189.99"),
        savings_amount=Decimal("40.00"),
        savings_percent=Decimal("0.21"),
        deal_url="https://www.amazon.es/dp/B0HOMEFB01",
        published_at=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([recent_tech, recent_home])
    db_session.flush()

    result = NewDealsService().get_new_deals(db_session, user=user, now=datetime(2026, 4, 12, 12, 0, tzinfo=UTC))

    assert result.new_count == 0
    assert result.fallback_used is True
    assert [deal.id for deal in result.deals] == [recent_tech.id]
