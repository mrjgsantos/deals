from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID
from urllib.parse import urlparse


MIN_RECENT_OBSERVATIONS_30D = 5
MIN_SUPPORT_OBSERVATIONS_90D = 15
MIN_SUPPORT_OBSERVATIONS_ALL_TIME = 30
IN_PROGRESS_GRACE_PERIOD = timedelta(minutes=30)


@dataclass(slots=True)
class KeepaFetchContext:
    asin: str | None
    product_variant_id: UUID | None = None
    source_slug: str | None = None
    product_url: str | None = None
    observation_count_30d: int = 0
    observation_count_90d: int = 0
    observation_count_all_time: int = 0
    last_refresh_attempt_at: datetime | None = None
    last_refresh_succeeded_at: datetime | None = None
    last_refresh_failed_at: datetime | None = None
    last_refresh_status: str | None = None
    last_refresh_failure_reason: str | None = None
    consecutive_refresh_failures: int = 0
    next_refresh_eligible_at: datetime | None = None
    linked_deal_count: int = 0
    has_pending_review_deal: bool = False
    has_published_deal: bool = False


@dataclass(slots=True)
class KeepaFetchDecision:
    should_fetch: bool
    reason: str
    next_eligible_at: datetime | None = None
    refresh_priority: str = "normal"
    staleness_classification: str = "scheduled"


@dataclass(slots=True)
class KeepaFetchRunState:
    fetched_variant_ids: set[UUID] = field(default_factory=set)
    fetched_asins: set[str] = field(default_factory=set)


def should_fetch_keepa_for_record(
    context: KeepaFetchContext,
    *,
    now: datetime | None = None,
    run_state: KeepaFetchRunState | None = None,
) -> KeepaFetchDecision:
    now = now or datetime.now(timezone.utc)
    normalized_asin = (context.asin or "").strip().upper()
    refresh_priority = classify_refresh_priority(context)
    staleness_classification = classify_staleness(context, now=now)

    if not normalized_asin:
        return KeepaFetchDecision(
            should_fetch=False,
            reason="missing_asin",
            refresh_priority=refresh_priority,
            staleness_classification=staleness_classification,
        )

    if not _is_amazon_relevant(context):
        return KeepaFetchDecision(
            should_fetch=False,
            reason="not_amazon_relevant",
            refresh_priority=refresh_priority,
            staleness_classification=staleness_classification,
        )

    if (
        context.last_refresh_attempt_at is None
        and context.last_refresh_succeeded_at is None
        and context.last_refresh_failed_at is None
        and _has_sufficient_history(context)
    ):
        return KeepaFetchDecision(
            should_fetch=False,
            reason="sufficient_local_history",
            next_eligible_at=derive_next_eligible_at(context, now=now),
            refresh_priority=refresh_priority,
            staleness_classification="fresh",
        )

    due_at = derive_next_eligible_at(context, now=now)
    if due_at is not None and due_at > now:
        return KeepaFetchDecision(
            should_fetch=False,
            reason=_not_due_reason(context),
            next_eligible_at=due_at,
            refresh_priority=refresh_priority,
            staleness_classification=classify_staleness(context, now=now, due_at=due_at),
        )

    if run_state is not None:
        if context.product_variant_id is not None and context.product_variant_id in run_state.fetched_variant_ids:
            return KeepaFetchDecision(
                should_fetch=False,
                reason="variant_already_requested_in_run",
                next_eligible_at=due_at,
                refresh_priority=refresh_priority,
                staleness_classification=classify_staleness(context, now=now, due_at=due_at),
            )
        if normalized_asin in run_state.fetched_asins:
            return KeepaFetchDecision(
                should_fetch=False,
                reason="asin_already_requested_in_run",
                next_eligible_at=due_at,
                refresh_priority=refresh_priority,
                staleness_classification=classify_staleness(context, now=now, due_at=due_at),
            )
        if context.product_variant_id is not None:
            run_state.fetched_variant_ids.add(context.product_variant_id)
        run_state.fetched_asins.add(normalized_asin)

    fetch_reason = "scheduled_refresh_due"
    if context.last_refresh_succeeded_at is None and context.last_refresh_failed_at is None:
        fetch_reason = "cold_start_due"
    elif context.consecutive_refresh_failures > 0:
        fetch_reason = "failure_backoff_elapsed"
    elif not _has_sufficient_history(context):
        fetch_reason = "insufficient_local_history_due"

    return KeepaFetchDecision(
        should_fetch=True,
        reason=fetch_reason,
        next_eligible_at=due_at,
        refresh_priority=refresh_priority,
        staleness_classification=classify_staleness(context, now=now, due_at=due_at),
    )


def next_eligible_after_attempt(
    *,
    interval_seconds: int,
    now: datetime | None = None,
) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now + max(IN_PROGRESS_GRACE_PERIOD, timedelta(seconds=max(interval_seconds, 0)))


def next_eligible_after_success(
    context: KeepaFetchContext,
    *,
    now: datetime | None = None,
) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now + _success_refresh_interval(context)


def next_eligible_after_failure(
    context: KeepaFetchContext,
    *,
    now: datetime | None = None,
) -> datetime:
    now = now or datetime.now(timezone.utc)
    failure_count = max(context.consecutive_refresh_failures, 1)
    return now + _failure_backoff_window(failure_count)


def derive_next_eligible_at(
    context: KeepaFetchContext,
    *,
    now: datetime | None = None,
) -> datetime | None:
    now = now or datetime.now(timezone.utc)
    if context.next_refresh_eligible_at is not None:
        return context.next_refresh_eligible_at
    if context.last_refresh_status == "in_progress" and context.last_refresh_attempt_at is not None:
        return context.last_refresh_attempt_at + IN_PROGRESS_GRACE_PERIOD
    if context.last_refresh_failed_at is not None and context.consecutive_refresh_failures > 0:
        return context.last_refresh_failed_at + _failure_backoff_window(context.consecutive_refresh_failures)
    if context.last_refresh_succeeded_at is not None:
        return context.last_refresh_succeeded_at + _success_refresh_interval(context)
    if (
        context.last_refresh_attempt_at is None
        and context.last_refresh_succeeded_at is None
        and context.last_refresh_failed_at is None
        and _has_sufficient_history(context)
    ):
        return now + _success_refresh_interval(context)
    return None


def classify_refresh_priority(context: KeepaFetchContext) -> str:
    if context.has_pending_review_deal and not _has_sufficient_history(context):
        return "urgent"
    if context.has_pending_review_deal or context.has_published_deal:
        return "high"
    if context.linked_deal_count > 0 or not _has_sufficient_history(context):
        return "normal"
    return "low"


def classify_staleness(
    context: KeepaFetchContext,
    *,
    now: datetime | None = None,
    due_at: datetime | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    due_at = due_at if due_at is not None else derive_next_eligible_at(context, now=now)
    if (
        context.last_refresh_attempt_at is None
        and context.last_refresh_succeeded_at is None
        and context.last_refresh_failed_at is None
    ):
        return "fresh" if _has_sufficient_history(context) else "cold_start"
    if context.consecutive_refresh_failures > 0 and due_at is not None and due_at > now:
        return "retry_backoff"
    if due_at is not None and due_at <= now:
        return "stale"
    if _has_recent_history(context):
        return "fresh"
    return "scheduled"


def _not_due_reason(context: KeepaFetchContext) -> str:
    if context.last_refresh_status == "in_progress":
        return "refresh_in_progress"
    if context.consecutive_refresh_failures > 0:
        return "failure_backoff_active"
    return "refresh_not_due"


def _success_refresh_interval(context: KeepaFetchContext) -> timedelta:
    if context.has_pending_review_deal:
        return timedelta(hours=6)
    if context.has_published_deal:
        return timedelta(hours=12)
    if context.linked_deal_count > 0:
        if not _has_sufficient_history(context):
            return timedelta(hours=12)
        return timedelta(hours=24)
    if not _has_sufficient_history(context):
        return timedelta(hours=24)
    return timedelta(hours=72)


def _failure_backoff_window(consecutive_failures: int) -> timedelta:
    if consecutive_failures <= 1:
        return timedelta(hours=1)
    if consecutive_failures == 2:
        return timedelta(hours=6)
    if consecutive_failures == 3:
        return timedelta(hours=24)
    return timedelta(hours=72)


def _has_sufficient_history(context: KeepaFetchContext) -> bool:
    return any(
        (
            context.observation_count_30d >= MIN_RECENT_OBSERVATIONS_30D,
            context.observation_count_90d >= MIN_SUPPORT_OBSERVATIONS_90D,
            context.observation_count_all_time >= MIN_SUPPORT_OBSERVATIONS_ALL_TIME,
        )
    )


def _has_recent_history(context: KeepaFetchContext) -> bool:
    return context.observation_count_30d >= MIN_RECENT_OBSERVATIONS_30D


def _is_amazon_relevant(context: KeepaFetchContext) -> bool:
    if (context.source_slug or "").strip().casefold() == "amazon-keepa":
        return True
    if not context.product_url:
        return False
    try:
        host = (urlparse(context.product_url).netloc or "").casefold()
    except ValueError:
        return False
    return "amazon." in host or host.endswith("amzn.to")
