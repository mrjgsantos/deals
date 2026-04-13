from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.enums import DealStatus, SourceType
from app.db.models import Deal, Source, User
from app.services.product_analytics_service import (
    EVENT_DEAL_CLICK,
    EVENT_DEAL_IMPRESSION,
    EVENT_DEAL_SAVED,
    EVENT_ONBOARDING_COMPLETED,
    EVENT_RECOMMENDED_DEAL_CLICK,
    EVENT_RECOMMENDED_DEAL_IMPRESSION,
    EVENT_USER_SIGNUP,
    ProductAnalyticsService,
)


def test_product_analytics_service_aggregates_core_rates(db_session) -> None:
    source = Source(name="Amazon ES", slug="amazon-es", source_type=SourceType.MARKETPLACE)
    user = User(email="analytics@example.com", password_hash="hash")
    db_session.add_all([source, user])
    db_session.flush()

    top_deal = Deal(
        source_id=source.id,
        title="Logitech monitor",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("199.99"),
        previous_price=Decimal("249.99"),
        savings_amount=Decimal("50.00"),
        savings_percent=Decimal("0.20"),
        deal_url="https://www.amazon.es/dp/B0ANALYTIC1",
        published_at=datetime.now(UTC),
    )
    second_deal = Deal(
        source_id=source.id,
        title="Cordless vacuum",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("129.99"),
        previous_price=Decimal("179.99"),
        savings_amount=Decimal("50.00"),
        savings_percent=Decimal("0.28"),
        deal_url="https://www.amazon.es/dp/B0ANALYTIC2",
        published_at=datetime.now(UTC),
    )
    db_session.add_all([top_deal, second_deal])
    db_session.flush()

    service = ProductAnalyticsService()
    service.record_event(db_session, user_id=user.id, event_type=EVENT_USER_SIGNUP)
    service.record_event(db_session, user_id=user.id, event_type=EVENT_ONBOARDING_COMPLETED)
    service.record_impressions(db_session, user_id=user.id, deal_ids=[top_deal.id, second_deal.id], recommended=False)
    service.record_event(db_session, user_id=user.id, event_type=EVENT_DEAL_CLICK, deal_id=top_deal.id)
    service.record_event(db_session, user_id=user.id, event_type=EVENT_DEAL_SAVED, deal_id=top_deal.id)
    service.record_impressions(db_session, user_id=user.id, deal_ids=[top_deal.id], recommended=True)
    service.record_event(db_session, user_id=user.id, event_type=EVENT_RECOMMENDED_DEAL_CLICK, deal_id=top_deal.id)

    overview = service.get_overview(db_session, days=30, limit=5)

    assert overview.user_signups == 1
    assert overview.onboarding_completed == 1
    assert overview.deal_impressions == 2
    assert overview.deal_clicks == 1
    assert overview.deal_saves == 1
    assert overview.recommended_deal_impressions == 1
    assert overview.recommended_deal_clicks == 1
    assert overview.ctr == 0.5
    assert overview.save_rate == 0.5
    assert overview.recommendation_ctr == 1.0
    assert overview.top_deals[0].deal_id == top_deal.id
    assert overview.top_deals[0].click_count == 1
    assert overview.top_deals[0].recommended_click_count == 1


def test_product_analytics_service_dedupes_repeated_events_and_bounds_rates(db_session) -> None:
    source = Source(name="Amazon ES", slug="amazon-es", source_type=SourceType.MARKETPLACE)
    user = User(email="analytics-dedupe@example.com", password_hash="hash")
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
        deal_url="https://www.amazon.es/dp/B0ANALYTIC3",
        published_at=datetime.now(UTC),
    )
    db_session.add(deal)
    db_session.flush()

    service = ProductAnalyticsService()
    tracked_once = service.record_impressions(db_session, user_id=user.id, deal_ids=[deal.id, deal.id], recommended=False)
    tracked_twice = service.record_impressions(db_session, user_id=user.id, deal_ids=[deal.id], recommended=False)
    first_click = service.record_event(db_session, user_id=user.id, event_type=EVENT_DEAL_CLICK, deal_id=deal.id)
    second_click = service.record_event(db_session, user_id=user.id, event_type=EVENT_DEAL_CLICK, deal_id=deal.id)
    first_save = service.record_event(db_session, user_id=user.id, event_type=EVENT_DEAL_SAVED, deal_id=deal.id)
    second_save = service.record_event(db_session, user_id=user.id, event_type=EVENT_DEAL_SAVED, deal_id=deal.id)

    overview = service.get_overview(db_session, days=30, limit=5)

    assert tracked_once == 1
    assert tracked_twice == 0
    assert first_click is True
    assert second_click is False
    assert first_save is True
    assert second_save is False
    assert overview.deal_impressions == 1
    assert overview.deal_clicks == 1
    assert overview.deal_saves == 1
    assert overview.ctr == 1.0
    assert overview.save_rate == 1.0
    assert overview.top_deals[0].impression_count == 1
    assert overview.top_deals[0].click_count == 1
    assert overview.top_deals[0].save_count == 1
