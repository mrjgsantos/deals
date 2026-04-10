from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.integrations.keepa_fetch_policy import (
    KeepaFetchContext,
    KeepaFetchRunState,
    classify_refresh_priority,
    next_eligible_after_failure,
    next_eligible_after_success,
    should_fetch_keepa_for_record,
)


def test_no_asin_disables_keepa_fetch() -> None:
    decision = should_fetch_keepa_for_record(
        KeepaFetchContext(
            asin=None,
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
        )
    )

    assert decision.should_fetch is False
    assert decision.reason == "missing_asin"


def test_enough_local_observations_disable_keepa_fetch_for_unattempted_row() -> None:
    decision = should_fetch_keepa_for_record(
        KeepaFetchContext(
            asin="B0TEST1234",
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
            observation_count_30d=5,
            observation_count_90d=8,
            observation_count_all_time=8,
        )
    )

    assert decision.should_fetch is False
    assert decision.reason == "sufficient_local_history"


def test_missing_history_with_asin_allows_keepa_fetch_on_cold_start() -> None:
    decision = should_fetch_keepa_for_record(
        KeepaFetchContext(
            asin="B0TEST1234",
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
            observation_count_30d=0,
            observation_count_90d=1,
            observation_count_all_time=1,
        )
    )

    assert decision.should_fetch is True
    assert decision.reason == "cold_start_due"
    assert decision.refresh_priority == "normal"
    assert decision.staleness_classification == "cold_start"


def test_recent_success_delays_refresh_until_next_eligible_time() -> None:
    now = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)
    last_success = now - timedelta(hours=2)
    decision = should_fetch_keepa_for_record(
        KeepaFetchContext(
            asin="B0TEST1234",
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
            last_refresh_succeeded_at=last_success,
            last_refresh_status="succeeded",
            linked_deal_count=1,
            observation_count_90d=15,
        ),
        now=now,
    )

    assert decision.should_fetch is False
    assert decision.reason == "refresh_not_due"
    assert decision.next_eligible_at == last_success + timedelta(hours=24)
    assert decision.staleness_classification == "scheduled"


def test_failure_backoff_blocks_retry_until_window_elapses() -> None:
    now = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)
    last_failure = now - timedelta(hours=1)
    decision = should_fetch_keepa_for_record(
        KeepaFetchContext(
            asin="B0TEST1234",
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
            last_refresh_failed_at=last_failure,
            last_refresh_status="fetch_failed",
            consecutive_refresh_failures=2,
        ),
        now=now,
    )

    assert decision.should_fetch is False
    assert decision.reason == "failure_backoff_active"
    assert decision.next_eligible_at == last_failure + timedelta(hours=6)
    assert decision.staleness_classification == "retry_backoff"


def test_elapsed_failure_backoff_allows_retry() -> None:
    now = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)
    decision = should_fetch_keepa_for_record(
        KeepaFetchContext(
            asin="B0TEST1234",
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
            last_refresh_failed_at=now - timedelta(hours=7),
            last_refresh_status="fetch_failed",
            consecutive_refresh_failures=2,
        ),
        now=now,
    )

    assert decision.should_fetch is True
    assert decision.reason == "failure_backoff_elapsed"
    assert decision.staleness_classification == "stale"


def test_pending_review_products_are_classified_as_urgent_when_history_is_shallow() -> None:
    priority = classify_refresh_priority(
        KeepaFetchContext(
            asin="B0TEST1234",
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
            has_pending_review_deal=True,
            observation_count_all_time=2,
        )
    )

    assert priority == "urgent"


def test_success_and_failure_helpers_use_expected_cadence() -> None:
    now = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)

    next_after_success = next_eligible_after_success(
        KeepaFetchContext(
            asin="B0TEST1234",
            has_published_deal=True,
        ),
        now=now,
    )
    next_after_failure = next_eligible_after_failure(
        KeepaFetchContext(
            asin="B0TEST1234",
            consecutive_refresh_failures=3,
        ),
        now=now,
    )

    assert next_after_success == now + timedelta(hours=12)
    assert next_after_failure == now + timedelta(hours=24)


def test_repeated_same_variant_fetch_is_suppressed_in_one_run() -> None:
    variant_id = uuid4()
    run_state = KeepaFetchRunState()
    first = should_fetch_keepa_for_record(
        KeepaFetchContext(
            asin="B0TEST1234",
            product_variant_id=variant_id,
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
        ),
        run_state=run_state,
    )
    second = should_fetch_keepa_for_record(
        KeepaFetchContext(
            asin="B0TEST1234",
            product_variant_id=variant_id,
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0TEST1234",
        ),
        run_state=run_state,
    )

    assert first.should_fetch is True
    assert second.should_fetch is False
    assert second.reason == "variant_already_requested_in_run"
