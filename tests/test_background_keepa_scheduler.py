from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.jobs import background_keepa_scheduler as scheduler_module
from app.jobs.background_keepa_scheduler import (
    BackgroundKeepaScheduler,
    BackgroundKeepaRunSummary,
    TrackedKeepaCandidate,
    maybe_start_background_keepa_scheduler,
)


class FakeLogger:
    def __init__(self) -> None:
        self.info_messages: list[str] = []

    def info(self, message: str, *args) -> None:
        self.info_messages.append(message % args if args else message)

    def exception(self, message: str, *args) -> None:
        self.info_messages.append(message % args if args else message)


class FakeThread:
    def __init__(self, *, target, name, daemon) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True

    def is_alive(self) -> bool:
        return self.started

    def join(self, timeout=None) -> None:
        self.started = False


class FakeSession:
    def __init__(self, *, has_keepa_source: bool = True) -> None:
        self.has_keepa_source = has_keepa_source

    def scalar(self, stmt):
        return uuid4() if self.has_keepa_source else None


class FakeTrackedProductSession:
    def __init__(self, tracked_products: list[SimpleNamespace]) -> None:
        self.tracked_products = tracked_products
        self.committed = False

    def scalars(self, stmt):
        return SimpleNamespace(all=lambda: self.tracked_products)

    def add(self, obj) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


def make_counts(*, obs_30d: int, obs_90d: int, obs_all_time: int):
    return SimpleNamespace(
        observation_count_30d=obs_30d,
        observation_count_90d=obs_90d,
        observation_count_all_time=obs_all_time,
    )


def test_scheduler_run_once_fetches_only_policy_allowed_asins(monkeypatch) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(scheduler_module, "setup_job_logger", lambda job_name: logger)

    scheduler = BackgroundKeepaScheduler(session_factory=lambda: nullcontext(FakeSession()))
    candidates = [
        TrackedKeepaCandidate(
            tracked_product_id=uuid4(),
            asin="B0FETCHME01",
            domain_id=9,
            product_variant_id=uuid4(),
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0FETCHME01",
        ),
        TrackedKeepaCandidate(
            tracked_product_id=uuid4(),
            asin="B0SKIPME02",
            domain_id=9,
            product_variant_id=uuid4(),
            source_slug="amazon-keepa",
            product_url="https://www.amazon.es/dp/B0SKIPME02",
        ),
    ]
    fetched_batches: list[list[str]] = []

    monkeypatch.setattr(scheduler, "_load_tracked_keepa_candidates", lambda db: candidates)
    monkeypatch.setattr(
        scheduler,
        "_history_counts_for_variant",
        lambda db, variant_id: make_counts(obs_30d=0, obs_90d=0, obs_all_time=0)
        if variant_id == candidates[0].product_variant_id
        else make_counts(obs_30d=5, obs_90d=15, obs_all_time=30),
    )
    monkeypatch.setattr(
        scheduler,
        "_fetch_keepa_batch",
        lambda asins, *, domain_id: fetched_batches.append(asins) or {"products": [{"asin": asin} for asin in asins]},
    )
    monkeypatch.setattr(
        scheduler,
        "_ingest_keepa_payload",
        lambda db, payload: SimpleNamespace(accepted=len(payload["products"]), rejected=0),
    )
    monkeypatch.setattr(scheduler, "_mark_tracked_products_attempted", lambda candidates: None)
    monkeypatch.setattr(scheduler, "_mark_tracked_products_succeeded", lambda candidates: None)
    monkeypatch.setattr(
        scheduler,
        "_mark_tracked_products_failed",
        lambda candidates, *, status, failure_reason: None,
    )

    summary = scheduler.run_once()

    assert summary.tracked_asins == 2
    assert summary.eligible_asins == 1
    assert summary.fetched_products == 1
    assert summary.accepted == 1
    assert fetched_batches == [["B0FETCHME01"]]
    assert any(message.startswith("background_keepa_refresh_batch_complete") for message in logger.info_messages)


def test_scheduler_run_once_batches_keepa_requests_at_fifty(monkeypatch) -> None:
    monkeypatch.setattr(scheduler_module, "setup_job_logger", lambda job_name: FakeLogger())

    scheduler = BackgroundKeepaScheduler(session_factory=lambda: nullcontext(FakeSession()))
    candidates = [
        TrackedKeepaCandidate(
            tracked_product_id=uuid4(),
            asin=f"B0TEST{i:05d}",
            domain_id=9,
            product_variant_id=uuid4(),
            source_slug="amazon-keepa",
            product_url=f"https://www.amazon.es/dp/B0TEST{i:05d}",
        )
        for i in range(51)
    ]
    fetched_batches: list[list[str]] = []

    monkeypatch.setattr(scheduler, "_load_tracked_keepa_candidates", lambda db: candidates)
    monkeypatch.setattr(
        scheduler,
        "_history_counts_for_variant",
        lambda db, variant_id: make_counts(obs_30d=0, obs_90d=0, obs_all_time=0),
    )
    monkeypatch.setattr(
        scheduler,
        "_fetch_keepa_batch",
        lambda asins, *, domain_id: fetched_batches.append(asins) or {"products": [{"asin": asin} for asin in asins]},
    )
    monkeypatch.setattr(
        scheduler,
        "_ingest_keepa_payload",
        lambda db, payload: SimpleNamespace(accepted=len(payload["products"]), rejected=0),
    )
    monkeypatch.setattr(scheduler, "_mark_tracked_products_attempted", lambda candidates: None)
    monkeypatch.setattr(scheduler, "_mark_tracked_products_succeeded", lambda candidates: None)
    monkeypatch.setattr(
        scheduler,
        "_mark_tracked_products_failed",
        lambda candidates, *, status, failure_reason: None,
    )

    summary = scheduler.run_once()

    assert summary.eligible_asins == 51
    assert [len(batch) for batch in fetched_batches] == [50, 1]
    assert summary.accepted == 51


def test_maybe_start_background_keepa_scheduler_respects_toggle(monkeypatch) -> None:
    monkeypatch.setattr("app.jobs.background_keepa_scheduler.settings.enable_background_jobs", False)
    assert maybe_start_background_keepa_scheduler() is None

    started = {"value": False}

    class FakeScheduler:
        def start(self) -> None:
            started["value"] = True

    monkeypatch.setattr("app.jobs.background_keepa_scheduler.settings.enable_background_jobs", True)
    monkeypatch.setattr(scheduler_module, "BackgroundKeepaScheduler", FakeScheduler)

    scheduler = maybe_start_background_keepa_scheduler()

    assert isinstance(scheduler, FakeScheduler)
    assert started["value"] is True


def test_scheduler_start_logs_explicit_startup_message(monkeypatch) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(scheduler_module, "setup_job_logger", lambda job_name: logger)
    monkeypatch.setattr(scheduler_module, "Thread", FakeThread)

    scheduler = BackgroundKeepaScheduler(session_factory=lambda: nullcontext(FakeSession()))
    scheduler.start()

    assert "background_keepa_scheduler_started interval_seconds=600" in logger.info_messages


def test_scheduler_run_once_logs_refresh_start_and_completion(monkeypatch) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(scheduler_module, "setup_job_logger", lambda job_name: logger)

    scheduler = BackgroundKeepaScheduler(session_factory=lambda: nullcontext(FakeSession()))
    monkeypatch.setattr(scheduler, "_load_tracked_keepa_candidates", lambda db: [])

    summary = scheduler.run_once()

    assert summary.tracked_asins == 0
    assert summary.eligible_asins == 0
    assert "background_keepa_refresh_started tracked_asins=0 eligible_asins=0" in logger.info_messages
    assert any(message.startswith("background_keepa_refresh_complete") for message in logger.info_messages)


def test_maybe_start_background_keepa_scheduler_logs_disabled_state(monkeypatch) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(scheduler_module, "setup_job_logger", lambda job_name: logger)
    monkeypatch.setattr("app.jobs.background_keepa_scheduler.settings.enable_background_jobs", False)

    scheduler = maybe_start_background_keepa_scheduler()

    assert scheduler is None
    assert "background_keepa_scheduler_disabled enable_background_jobs=false" in logger.info_messages


def test_load_tracked_keepa_candidates_uses_tracked_product_pool(monkeypatch) -> None:
    monkeypatch.setattr(scheduler_module, "setup_job_logger", lambda job_name: FakeLogger())

    tracked_product = SimpleNamespace(id=uuid4(), asin="B0POOL1234", domain_id=9)
    product_variant_id = uuid4()

    def fake_execute(stmt):
        statement_text = str(stmt)
        if "FROM deals" in statement_text:
            return SimpleNamespace(all=lambda: [])
        return SimpleNamespace(first=lambda: (product_variant_id, "https://www.amazon.es/dp/B0POOL1234", "amazon-keepa"))

    db = SimpleNamespace(execute=fake_execute)
    scheduler = BackgroundKeepaScheduler(session_factory=lambda: nullcontext(FakeSession()))

    monkeypatch.setattr(scheduler_module, "get_active_tracked_asins", lambda db, limit=100: [tracked_product])

    candidates = scheduler._load_tracked_keepa_candidates(db)

    assert len(candidates) == 1
    assert candidates[0].tracked_product_id == tracked_product.id
    assert candidates[0].asin == "B0POOL1234"
    assert candidates[0].domain_id == 9


def test_scheduler_marks_tracked_products_attempted_and_failed() -> None:
    tracked_product = SimpleNamespace(
        id=uuid4(),
        last_checked_at=None,
        last_refresh_attempt_at=None,
        last_refresh_succeeded_at=None,
        last_refresh_failed_at=None,
        last_refresh_status=None,
        last_refresh_failure_reason=None,
        consecutive_refresh_failures=0,
        next_refresh_eligible_at=None,
    )
    session = FakeTrackedProductSession([tracked_product])
    scheduler = BackgroundKeepaScheduler(session_factory=lambda: nullcontext(session))
    candidate = TrackedKeepaCandidate(
        tracked_product_id=tracked_product.id,
        asin="B0TEST1234",
        domain_id=9,
        product_variant_id=None,
        source_slug="amazon-keepa",
        product_url="https://www.amazon.es/dp/B0TEST1234",
    )

    scheduler._mark_tracked_products_attempted([candidate])

    assert tracked_product.last_refresh_attempt_at is not None
    assert tracked_product.last_refresh_status == "in_progress"
    assert tracked_product.last_refresh_failure_reason is None
    assert tracked_product.next_refresh_eligible_at is not None

    scheduler._mark_tracked_products_failed(
        [candidate],
        status="fetch_failed",
        failure_reason="keepa_fetch_failed",
    )

    assert tracked_product.last_checked_at is not None
    assert tracked_product.last_refresh_failed_at is not None
    assert tracked_product.last_refresh_status == "fetch_failed"
    assert tracked_product.last_refresh_failure_reason == "keepa_fetch_failed"
    assert tracked_product.consecutive_refresh_failures == 1
    assert session.committed is True


def test_scheduler_marks_success_and_resets_failure_streak() -> None:
    now = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)
    tracked_product = SimpleNamespace(
        id=uuid4(),
        last_checked_at=None,
        last_refresh_attempt_at=now - timedelta(minutes=5),
        last_refresh_succeeded_at=None,
        last_refresh_failed_at=now - timedelta(hours=2),
        last_refresh_status="fetch_failed",
        last_refresh_failure_reason="keepa_fetch_failed",
        consecutive_refresh_failures=2,
        next_refresh_eligible_at=now,
    )
    session = FakeTrackedProductSession([tracked_product])
    scheduler = BackgroundKeepaScheduler(session_factory=lambda: nullcontext(session))
    candidate = TrackedKeepaCandidate(
        tracked_product_id=tracked_product.id,
        asin="B0TEST1234",
        domain_id=9,
        product_variant_id=None,
        source_slug="amazon-keepa",
        product_url="https://www.amazon.es/dp/B0TEST1234",
        has_published_deal=True,
    )

    scheduler._mark_tracked_products_succeeded([candidate])

    assert tracked_product.last_refresh_status == "succeeded"
    assert tracked_product.last_refresh_succeeded_at is not None
    assert tracked_product.consecutive_refresh_failures == 0
    assert tracked_product.next_refresh_eligible_at is not None
    assert tracked_product.next_refresh_eligible_at > tracked_product.last_refresh_succeeded_at


def test_scheduler_runtime_snapshot_exposes_last_run_summary(monkeypatch) -> None:
    monkeypatch.setattr(scheduler_module, "setup_job_logger", lambda job_name: FakeLogger())
    scheduler = BackgroundKeepaScheduler(session_factory=lambda: nullcontext(FakeSession()))
    summary = BackgroundKeepaRunSummary(tracked_asins=4, eligible_asins=2, accepted=2, rejected=0)

    scheduler._mark_run_started()
    scheduler._mark_run_completed(summary, status="succeeded")
    snapshot = scheduler.get_runtime_snapshot()

    assert snapshot.last_status == "succeeded"
    assert snapshot.last_summary is not None
    assert snapshot.last_summary.tracked_asins == 4
    assert snapshot.last_completed_at is not None
