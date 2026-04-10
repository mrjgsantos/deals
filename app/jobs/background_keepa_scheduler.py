from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.enums import DealStatus
from app.db.models import Deal, ProductSourceRecord, Source, TrackedProduct
from app.db.session import SessionLocal
from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.parsers.keepa import KeepaParser
from app.ingestion.service import IngestionService
from app.integrations.keepa_client import (
    KeepaClientError,
    KeepaConfigurationError,
    fetch_products_by_asins,
)
from app.integrations.keepa_fetch_policy import (
    KeepaFetchContext,
    KeepaFetchRunState,
    next_eligible_after_attempt,
    next_eligible_after_failure,
    next_eligible_after_success,
    should_fetch_keepa_for_record,
)
from app.jobs.common import setup_job_logger
from app.matching.service import MatchingService
from app.pricing.aggregation import aggregate_price_history_for_variant
from app.services.tracked_product_service import get_active_tracked_asins
from app.integrations.keepa_payloads import normalize_keepa_payload_for_ingest

BACKGROUND_KEEPA_JOB_NAME = "background_keepa_scheduler"
BACKGROUND_KEEPA_INTERVAL_SECONDS = 600
MAX_KEEPA_BATCH_SIZE = 50
KEEPA_SOURCE_SLUG = "amazon-keepa"


@dataclass(slots=True)
class TrackedKeepaCandidate:
    tracked_product_id: UUID
    asin: str
    domain_id: int
    product_variant_id: UUID | None
    source_slug: str | None
    product_url: str | None
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
    observation_count_30d: int = 0
    observation_count_90d: int = 0
    observation_count_all_time: int = 0


@dataclass(slots=True)
class BackgroundKeepaRunSummary:
    tracked_asins: int = 0
    eligible_asins: int = 0
    fetched_products: int = 0
    accepted: int = 0
    rejected: int = 0
    failed_batches: int = 0
    skipped_reason: str | None = None


@dataclass(slots=True)
class BackgroundKeepaRuntimeSnapshot:
    interval_seconds: int
    is_running: bool
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_status: str = "idle"
    last_error_reason: str | None = None
    last_summary: BackgroundKeepaRunSummary | None = None


class BackgroundKeepaScheduler:
    def __init__(
        self,
        *,
        interval_seconds: int = BACKGROUND_KEEPA_INTERVAL_SECONDS,
        session_factory=SessionLocal,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.session_factory = session_factory
        self.logger = setup_job_logger(BACKGROUND_KEEPA_JOB_NAME)
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._runtime_lock = Lock()
        self._last_started_at: datetime | None = None
        self._last_completed_at: datetime | None = None
        self._last_status = "idle"
        self._last_error_reason: str | None = None
        self._last_summary: BackgroundKeepaRunSummary | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run_loop,
            name="background-keepa-scheduler",
            daemon=True,
        )
        self._thread.start()
        self.logger.info(
            "background_keepa_scheduler_started interval_seconds=%s",
            self.interval_seconds,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.logger.info("background_keepa_scheduler_stopped")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                self._mark_run_failed(error_reason="unhandled_run_failure")
                self.logger.exception("background_keepa_scheduler_run_failed")
            if self._stop_event.wait(self.interval_seconds):
                break

    def run_once(self) -> BackgroundKeepaRunSummary:
        summary = BackgroundKeepaRunSummary()
        self._mark_run_started()

        with self._session_scope() as db:
            if not self._keepa_source_exists(db):
                summary.skipped_reason = "missing_keepa_source"
                self._mark_run_completed(summary, status="skipped")
                self.logger.info("background_keepa_refresh_skipped reason=%s", summary.skipped_reason)
                return summary

            try:
                tracked_candidates = self._load_tracked_keepa_candidates(db)
                summary.tracked_asins = len(tracked_candidates)
                fetchable_candidates = self._select_fetchable_candidates(db, tracked_candidates)
                summary.eligible_asins = len(fetchable_candidates)
            except SQLAlchemyError:
                summary.skipped_reason = "tracked_products_unavailable"
                self._mark_run_completed(summary, status="skipped")
                self.logger.exception(
                    "background_keepa_refresh_skipped reason=%s",
                    summary.skipped_reason,
                )
                return summary

        self.logger.info(
            "background_keepa_refresh_started tracked_asins=%s eligible_asins=%s",
            summary.tracked_asins,
            summary.eligible_asins,
        )

        if not fetchable_candidates:
            self._mark_run_completed(summary, status="succeeded")
            self.logger.info(
                "background_keepa_refresh_complete tracked_asins=%s eligible_asins=%s fetched_products=%s accepted=%s rejected=%s failed_batches=%s",
                summary.tracked_asins,
                summary.eligible_asins,
                summary.fetched_products,
                summary.accepted,
                summary.rejected,
                summary.failed_batches,
            )
            return summary

        grouped_candidates = self._group_candidates_by_domain(fetchable_candidates)
        for domain_id, domain_candidates in grouped_candidates.items():
            for candidate_batch in _chunked(domain_candidates, MAX_KEEPA_BATCH_SIZE):
                asin_batch = [candidate.asin for candidate in candidate_batch]
                self._mark_tracked_products_attempted(candidate_batch)
                try:
                    payload = self._fetch_keepa_batch(asin_batch, domain_id=domain_id)
                    summary.fetched_products += len(payload.get("products", []))
                except (KeepaClientError, KeepaConfigurationError):
                    summary.failed_batches += 1
                    self.logger.exception(
                        "background_keepa_fetch_batch_failed domain_id=%s asin_count=%s batch=%s",
                        domain_id,
                        len(asin_batch),
                        ",".join(asin_batch),
                    )
                    self._mark_tracked_products_failed(
                        candidate_batch,
                        status="fetch_failed",
                        failure_reason="keepa_fetch_failed",
                    )
                    continue

                try:
                    batch_succeeded = False
                    batch_accepted = 0
                    batch_rejected = 0
                    with self._session_scope() as db:
                        result = self._ingest_keepa_payload(db, payload)
                        summary.accepted += result.accepted
                        summary.rejected += result.rejected
                        batch_accepted = result.accepted
                        batch_rejected = result.rejected
                        batch_succeeded = True
                except Exception:
                    summary.failed_batches += 1
                    self.logger.exception(
                        "background_keepa_ingest_batch_failed domain_id=%s asin_count=%s batch=%s",
                        domain_id,
                        len(asin_batch),
                        ",".join(asin_batch),
                    )
                    self._mark_tracked_products_failed(
                        candidate_batch,
                        status="ingest_failed",
                        failure_reason="keepa_ingest_failed",
                    )
                finally:
                    if batch_succeeded:
                        self.logger.info(
                            "background_keepa_refresh_batch_complete domain_id=%s asin_count=%s fetched_products=%s accepted=%s rejected=%s batch=%s",
                            domain_id,
                            len(asin_batch),
                            len(payload.get("products", [])),
                            batch_accepted,
                            batch_rejected,
                            ",".join(asin_batch),
                        )
                        self._mark_tracked_products_succeeded(candidate_batch)

        self._mark_run_completed(
            summary,
            status="completed_with_failures" if summary.failed_batches else "succeeded",
        )
        self.logger.info(
            "background_keepa_refresh_complete tracked_asins=%s eligible_asins=%s fetched_products=%s accepted=%s rejected=%s failed_batches=%s",
            summary.tracked_asins,
            summary.eligible_asins,
            summary.fetched_products,
            summary.accepted,
            summary.rejected,
            summary.failed_batches,
        )
        return summary

    def _session_scope(self):
        session = self.session_factory()
        if hasattr(session, "__enter__") and hasattr(session, "__exit__"):
            return session
        return nullcontext(session)

    def _keepa_source_exists(self, db) -> bool:
        return db.scalar(select(Source.id).where(Source.slug == KEEPA_SOURCE_SLUG)) is not None

    def _load_tracked_keepa_candidates(self, db) -> list[TrackedKeepaCandidate]:
        candidates: list[TrackedKeepaCandidate] = []
        for tracked_product in get_active_tracked_asins(db):
            row = db.execute(
                select(
                    ProductSourceRecord.product_variant_id,
                    ProductSourceRecord.source_url,
                    Source.slug,
                )
                .join(Source, Source.id == ProductSourceRecord.source_id)
                .where(ProductSourceRecord.source_attributes["asin"].astext == tracked_product.asin)
                .order_by(ProductSourceRecord.last_seen_at.desc(), ProductSourceRecord.created_at.desc())
                .limit(1)
            ).first()

            product_variant_id = row[0] if row is not None else None
            source_url = row[1] if row is not None else None
            source_slug = row[2] if row is not None else None
            candidates.append(
                TrackedKeepaCandidate(
                    tracked_product_id=tracked_product.id,
                    asin=tracked_product.asin,
                    domain_id=tracked_product.domain_id,
                    product_variant_id=product_variant_id,
                    source_slug=source_slug,
                    product_url=source_url,
                    last_refresh_attempt_at=getattr(tracked_product, "last_refresh_attempt_at", None),
                    last_refresh_succeeded_at=getattr(tracked_product, "last_refresh_succeeded_at", None),
                    last_refresh_failed_at=getattr(tracked_product, "last_refresh_failed_at", None),
                    last_refresh_status=getattr(tracked_product, "last_refresh_status", None),
                    last_refresh_failure_reason=getattr(tracked_product, "last_refresh_failure_reason", None),
                    consecutive_refresh_failures=getattr(tracked_product, "consecutive_refresh_failures", 0),
                    next_refresh_eligible_at=getattr(tracked_product, "next_refresh_eligible_at", None),
                )
            )
        deal_flags_by_variant = self._load_deal_flags_by_variant(
            db,
            [candidate.product_variant_id for candidate in candidates if candidate.product_variant_id is not None],
        )
        for candidate in candidates:
            if candidate.product_variant_id is None:
                continue
            linked_deal_count, has_pending_review_deal, has_published_deal = deal_flags_by_variant.get(
                candidate.product_variant_id,
                (0, False, False),
            )
            candidate.linked_deal_count = linked_deal_count
            candidate.has_pending_review_deal = has_pending_review_deal
            candidate.has_published_deal = has_published_deal
        return candidates

    def _select_fetchable_candidates(self, db, candidates: list[TrackedKeepaCandidate]) -> list[TrackedKeepaCandidate]:
        run_state = KeepaFetchRunState()
        fetchable: list[TrackedKeepaCandidate] = []
        decision_at = datetime.now(timezone.utc)
        for candidate in candidates:
            history_counts = self._history_counts_for_variant(db, candidate.product_variant_id)
            candidate.observation_count_30d = history_counts.observation_count_30d
            candidate.observation_count_90d = history_counts.observation_count_90d
            candidate.observation_count_all_time = history_counts.observation_count_all_time
            decision = should_fetch_keepa_for_record(
                self._keepa_fetch_context(candidate),
                now=decision_at,
                run_state=run_state,
            )
            if decision.should_fetch:
                self.logger.info(
                    "background_keepa_refresh_candidate_due asin=%s reason=%s priority=%s staleness=%s next_eligible_at=%s failures=%s",
                    candidate.asin,
                    decision.reason,
                    decision.refresh_priority,
                    decision.staleness_classification,
                    decision.next_eligible_at.isoformat() if decision.next_eligible_at is not None else "now",
                    candidate.consecutive_refresh_failures,
                )
                fetchable.append(candidate)
                continue
            self.logger.info(
                "background_keepa_refresh_candidate_skipped asin=%s reason=%s priority=%s staleness=%s next_eligible_at=%s failures=%s",
                candidate.asin,
                decision.reason,
                decision.refresh_priority,
                decision.staleness_classification,
                decision.next_eligible_at.isoformat() if decision.next_eligible_at is not None else "n/a",
                candidate.consecutive_refresh_failures,
            )
        return fetchable

    def _load_deal_flags_by_variant(
        self,
        db,
        product_variant_ids: list[UUID],
    ) -> dict[UUID, tuple[int, bool, bool]]:
        if not product_variant_ids:
            return {}
        rows = db.execute(
            select(
                Deal.product_variant_id,
                func.count(Deal.id),
                func.max(case((Deal.status == DealStatus.PENDING_REVIEW, 1), else_=0)),
                func.max(
                    case(
                        (
                            Deal.status.in_((DealStatus.APPROVED, DealStatus.PUBLISHED))
                            & Deal.published_at.is_not(None),
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
            .where(Deal.product_variant_id.in_(product_variant_ids))
            .group_by(Deal.product_variant_id)
        ).all()
        return {
            product_variant_id: (int(linked_deal_count), bool(has_pending_review_deal), bool(has_published_deal))
            for product_variant_id, linked_deal_count, has_pending_review_deal, has_published_deal in rows
        }

    def _history_counts_for_variant(self, db, product_variant_id: UUID | None):
        if product_variant_id is None:
            return type("Counts", (), {"observation_count_30d": 0, "observation_count_90d": 0, "observation_count_all_time": 0})()
        try:
            aggregation = aggregate_price_history_for_variant(db, product_variant_id)
        except ValueError:
            return type("Counts", (), {"observation_count_30d": 0, "observation_count_90d": 0, "observation_count_all_time": 0})()
        return aggregation

    def _fetch_keepa_batch(self, asins: list[str], *, domain_id: int) -> dict:
        payload = asyncio.run(
            fetch_products_by_asins(
                asins,
                domain_id=domain_id,
                timeout=60.0,
            )
        )
        return normalize_keepa_payload_for_ingest(payload, domain_id=domain_id)

    def _ingest_keepa_payload(self, db, payload: dict):
        service = IngestionService(
            parser=KeepaParser(),
            normalizer=DefaultRecordNormalizer(),
            matcher=MatchingService(),
        )
        return service.ingest(db, KEEPA_SOURCE_SLUG, payload, commit=True)

    def _group_candidates_by_domain(
        self,
        candidates: list[TrackedKeepaCandidate],
    ) -> dict[int, list[TrackedKeepaCandidate]]:
        grouped: dict[int, list[TrackedKeepaCandidate]] = {}
        for candidate in candidates:
            grouped.setdefault(candidate.domain_id, []).append(candidate)
        return grouped

    def _keepa_fetch_context(
        self,
        candidate: TrackedKeepaCandidate,
        **overrides,
    ) -> KeepaFetchContext:
        return KeepaFetchContext(
            asin=candidate.asin,
            product_variant_id=candidate.product_variant_id,
            source_slug=candidate.source_slug,
            product_url=candidate.product_url,
            observation_count_30d=overrides.get("observation_count_30d", candidate.observation_count_30d),
            observation_count_90d=overrides.get("observation_count_90d", candidate.observation_count_90d),
            observation_count_all_time=overrides.get("observation_count_all_time", candidate.observation_count_all_time),
            last_refresh_attempt_at=overrides.get("last_refresh_attempt_at", candidate.last_refresh_attempt_at),
            last_refresh_succeeded_at=overrides.get("last_refresh_succeeded_at", candidate.last_refresh_succeeded_at),
            last_refresh_failed_at=overrides.get("last_refresh_failed_at", candidate.last_refresh_failed_at),
            last_refresh_status=overrides.get("last_refresh_status", candidate.last_refresh_status),
            last_refresh_failure_reason=overrides.get(
                "last_refresh_failure_reason",
                candidate.last_refresh_failure_reason,
            ),
            consecutive_refresh_failures=overrides.get(
                "consecutive_refresh_failures",
                candidate.consecutive_refresh_failures,
            ),
            next_refresh_eligible_at=overrides.get("next_refresh_eligible_at", candidate.next_refresh_eligible_at),
            linked_deal_count=overrides.get("linked_deal_count", candidate.linked_deal_count),
            has_pending_review_deal=overrides.get(
                "has_pending_review_deal",
                candidate.has_pending_review_deal,
            ),
            has_published_deal=overrides.get("has_published_deal", candidate.has_published_deal),
        )

    def get_runtime_snapshot(self) -> BackgroundKeepaRuntimeSnapshot:
        with self._runtime_lock:
            return BackgroundKeepaRuntimeSnapshot(
                interval_seconds=self.interval_seconds,
                is_running=bool(self._thread is not None and self._thread.is_alive()),
                last_started_at=self._last_started_at,
                last_completed_at=self._last_completed_at,
                last_status=self._last_status,
                last_error_reason=self._last_error_reason,
                last_summary=(
                    None
                    if self._last_summary is None
                    else BackgroundKeepaRunSummary(
                        tracked_asins=self._last_summary.tracked_asins,
                        eligible_asins=self._last_summary.eligible_asins,
                        fetched_products=self._last_summary.fetched_products,
                        accepted=self._last_summary.accepted,
                        rejected=self._last_summary.rejected,
                        failed_batches=self._last_summary.failed_batches,
                        skipped_reason=self._last_summary.skipped_reason,
                    )
                ),
            )

    def _mark_tracked_products_attempted(self, candidates: list[TrackedKeepaCandidate]) -> None:
        if not candidates:
            return
        attempted_at = datetime.now(timezone.utc)
        attempted_by_id = {
            candidate.tracked_product_id: next_eligible_after_attempt(
                interval_seconds=self.interval_seconds,
                now=attempted_at,
            )
            for candidate in candidates
        }
        with self._session_scope() as db:
            tracked_products = db.scalars(
                select(TrackedProduct).where(TrackedProduct.id.in_(attempted_by_id))
            ).all()
            for tracked_product in tracked_products:
                tracked_product.last_checked_at = attempted_at
                tracked_product.last_refresh_attempt_at = attempted_at
                tracked_product.last_refresh_status = "in_progress"
                tracked_product.last_refresh_failure_reason = None
                tracked_product.next_refresh_eligible_at = attempted_by_id[tracked_product.id]
                db.add(tracked_product)
            if hasattr(db, "commit"):
                db.commit()

    def _mark_tracked_products_succeeded(self, candidates: list[TrackedKeepaCandidate]) -> None:
        self._update_tracked_products_refresh_state(
            candidates,
            status="succeeded",
            succeeded_at=datetime.now(timezone.utc),
            failure_reason=None,
        )

    def _mark_tracked_products_failed(
        self,
        candidates: list[TrackedKeepaCandidate],
        *,
        status: str,
        failure_reason: str,
    ) -> None:
        self._update_tracked_products_refresh_state(
            candidates,
            status=status,
            succeeded_at=None,
            failure_reason=failure_reason,
        )

    def _update_tracked_products_refresh_state(
        self,
        candidates: list[TrackedKeepaCandidate],
        *,
        status: str,
        succeeded_at: datetime | None,
        failure_reason: str | None,
    ) -> None:
        if not candidates:
            return
        checked_at = datetime.now(timezone.utc)
        candidate_by_id = {candidate.tracked_product_id: candidate for candidate in candidates}
        with self._session_scope() as db:
            tracked_products = db.scalars(
                select(TrackedProduct).where(TrackedProduct.id.in_(candidate_by_id))
            ).all()
            for tracked_product in tracked_products:
                candidate = candidate_by_id[tracked_product.id]
                tracked_product.last_checked_at = checked_at
                tracked_product.last_refresh_status = status
                tracked_product.last_refresh_failure_reason = failure_reason
                if succeeded_at is not None:
                    tracked_product.last_refresh_succeeded_at = succeeded_at
                    tracked_product.consecutive_refresh_failures = 0
                    tracked_product.next_refresh_eligible_at = next_eligible_after_success(
                        self._keepa_fetch_context(
                            candidate,
                            consecutive_refresh_failures=0,
                            last_refresh_succeeded_at=succeeded_at,
                            last_refresh_status=status,
                            next_refresh_eligible_at=None,
                        ),
                        now=succeeded_at,
                    )
                else:
                    failed_at = checked_at
                    consecutive_failures = tracked_product.consecutive_refresh_failures + 1
                    tracked_product.last_refresh_failed_at = failed_at
                    tracked_product.consecutive_refresh_failures = consecutive_failures
                    tracked_product.next_refresh_eligible_at = next_eligible_after_failure(
                        self._keepa_fetch_context(
                            candidate,
                            consecutive_refresh_failures=consecutive_failures,
                            last_refresh_failed_at=failed_at,
                            last_refresh_status=status,
                            next_refresh_eligible_at=None,
                        ),
                        now=failed_at,
                    )
                db.add(tracked_product)
            if hasattr(db, "commit"):
                db.commit()

    def _mark_run_started(self) -> None:
        with self._runtime_lock:
            self._last_started_at = datetime.now(timezone.utc)
            self._last_status = "running"
            self._last_error_reason = None

    def _mark_run_completed(self, summary: BackgroundKeepaRunSummary, *, status: str) -> None:
        with self._runtime_lock:
            self._last_completed_at = datetime.now(timezone.utc)
            self._last_status = status
            self._last_error_reason = summary.skipped_reason
            self._last_summary = BackgroundKeepaRunSummary(
                tracked_asins=summary.tracked_asins,
                eligible_asins=summary.eligible_asins,
                fetched_products=summary.fetched_products,
                accepted=summary.accepted,
                rejected=summary.rejected,
                failed_batches=summary.failed_batches,
                skipped_reason=summary.skipped_reason,
            )

    def _mark_run_failed(self, *, error_reason: str) -> None:
        with self._runtime_lock:
            self._last_completed_at = datetime.now(timezone.utc)
            self._last_status = "failed"
            self._last_error_reason = error_reason


def maybe_start_background_keepa_scheduler() -> BackgroundKeepaScheduler | None:
    if not settings.enable_background_jobs:
        setup_job_logger(BACKGROUND_KEEPA_JOB_NAME).info(
            "background_keepa_scheduler_disabled enable_background_jobs=false"
        )
        return None
    scheduler = BackgroundKeepaScheduler()
    scheduler.start()
    return scheduler


def stop_background_keepa_scheduler(scheduler: BackgroundKeepaScheduler | None) -> None:
    if scheduler is None:
        return
    scheduler.stop()


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _normalized_asin(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip().upper()
    return candidate or None
