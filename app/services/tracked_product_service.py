from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.enums import DealStatus
from app.db.models import Deal, PriceObservation, ProductSourceRecord, Source, TrackedProduct
from app.integrations.keepa_fetch_policy import (
    KeepaFetchContext,
    classify_refresh_priority,
    classify_staleness,
    derive_next_eligible_at,
)

AMAZON_DOMAIN_ID_BY_HOST = {
    "amazon.com": 1,
    "amazon.co.uk": 2,
    "amazon.de": 3,
    "amazon.fr": 4,
    "amazon.co.jp": 5,
    "amazon.ca": 6,
    "amazon.it": 8,
    "amazon.es": 9,
    "amazon.in": 10,
}

FAILED_REFRESH_STATUSES = {"fetch_failed", "ingest_failed"}


@dataclass(slots=True)
class TrackedProductOperationsRecord:
    id: UUID
    asin: str
    domain_id: int
    display_name: str | None
    source_slug: str | None
    source_name: str | None
    source_url: str | None
    is_active: bool
    last_refresh_attempt_at: datetime | None
    last_successful_refresh_at: datetime | None
    last_failed_refresh_at: datetime | None
    refresh_status: str
    refresh_failure_reason: str | None
    consecutive_refresh_failures: int
    next_refresh_earliest_at: datetime | None
    refresh_priority: str
    staleness_classification: str
    observation_count_all_time: int
    linked_deal_count: int
    has_pending_review_deal: bool
    has_published_deal: bool


@dataclass(slots=True)
class TrackedProductOperationsSummaryRecord:
    total_tracked_products: int
    active_tracked_products: int
    never_attempted: int
    in_progress: int
    succeeded: int
    failed: int
    retry_backoff: int
    due_now: int


@dataclass(slots=True)
class _LatestSourceCandidate:
    asin: str
    raw_domain_id: str | None
    product_variant_id: UUID | None
    source_title: str | None
    source_url: str | None
    source_slug: str | None
    source_name: str | None


@dataclass(slots=True)
class _LinkedDealFlags:
    linked_deal_count: int = 0
    has_pending_review_deal: bool = False
    has_published_deal: bool = False


@dataclass(slots=True)
class _ObservationCounts:
    observation_count_30d: int = 0
    observation_count_90d: int = 0
    observation_count_all_time: int = 0


class TrackedProductOperationsService:
    def get_summary(self, db: Session) -> TrackedProductOperationsSummaryRecord:
        total_tracked_products = int(db.scalar(select(func.count(TrackedProduct.id))) or 0)
        status_counts = {
            status or "never_attempted": int(count)
            for status, count in db.execute(
                select(TrackedProduct.last_refresh_status, func.count(TrackedProduct.id)).group_by(
                    TrackedProduct.last_refresh_status
                )
            ).all()
        }
        never_attempted = status_counts.get("never_attempted", 0)
        failed = sum(status_counts.get(status, 0) for status in FAILED_REFRESH_STATUSES)
        tracked_products = list(db.scalars(select(TrackedProduct)).all())
        retry_backoff = sum(1 for tracked_product in tracked_products if self._staleness_for_summary(tracked_product) == "retry_backoff")
        due_now = sum(1 for tracked_product in tracked_products if self._staleness_for_summary(tracked_product) == "stale")
        return TrackedProductOperationsSummaryRecord(
            total_tracked_products=total_tracked_products,
            active_tracked_products=total_tracked_products,
            never_attempted=never_attempted,
            in_progress=status_counts.get("in_progress", 0),
            succeeded=status_counts.get("succeeded", 0),
            failed=failed,
            retry_backoff=retry_backoff,
            due_now=due_now,
        )

    def list_operations(
        self,
        db: Session,
        *,
        limit: int = 200,
        refresh_interval_seconds: int | None = None,
    ) -> list[TrackedProductOperationsRecord]:
        tracked_products = list(
            db.scalars(
                select(TrackedProduct)
                .order_by(
                    TrackedProduct.last_refresh_attempt_at.is_not(None).asc(),
                    TrackedProduct.last_refresh_attempt_at.asc(),
                    TrackedProduct.created_at.asc(),
                )
                .limit(limit)
            ).all()
        )
        if not tracked_products:
            return []

        source_context_by_tracked_id = self._load_latest_source_contexts(db, tracked_products)
        variant_ids = [
            candidate.product_variant_id
            for candidate in source_context_by_tracked_id.values()
            if candidate is not None and candidate.product_variant_id is not None
        ]
        observation_counts_by_variant = self._load_observation_counts(db, variant_ids)
        linked_deal_flags_by_variant = self._load_linked_deal_flags(db, variant_ids)

        records: list[TrackedProductOperationsRecord] = []
        for tracked_product in tracked_products:
            source_context = source_context_by_tracked_id.get(tracked_product.id)
            product_variant_id = source_context.product_variant_id if source_context is not None else None
            linked_deal_flags = (
                linked_deal_flags_by_variant.get(product_variant_id, _LinkedDealFlags())
                if product_variant_id is not None
                else _LinkedDealFlags()
            )
            refresh_status = tracked_product.last_refresh_status or "never_attempted"
            observation_counts = observation_counts_by_variant.get(product_variant_id, _ObservationCounts())
            fetch_context = self._fetch_context(
                tracked_product,
                observation_counts=observation_counts,
                linked_deal_count=linked_deal_flags.linked_deal_count,
                has_pending_review_deal=linked_deal_flags.has_pending_review_deal,
                has_published_deal=linked_deal_flags.has_published_deal,
            )
            records.append(
                TrackedProductOperationsRecord(
                    id=tracked_product.id,
                    asin=tracked_product.asin,
                    domain_id=tracked_product.domain_id,
                    display_name=source_context.source_title if source_context is not None else None,
                    source_slug=source_context.source_slug if source_context is not None else None,
                    source_name=source_context.source_name if source_context is not None else None,
                    source_url=source_context.source_url if source_context is not None else None,
                    is_active=True,
                    last_refresh_attempt_at=tracked_product.last_refresh_attempt_at,
                    last_successful_refresh_at=tracked_product.last_refresh_succeeded_at,
                    last_failed_refresh_at=tracked_product.last_refresh_failed_at,
                    refresh_status=refresh_status,
                    refresh_failure_reason=tracked_product.last_refresh_failure_reason,
                    consecutive_refresh_failures=tracked_product.consecutive_refresh_failures,
                    next_refresh_earliest_at=derive_next_eligible_at(fetch_context),
                    refresh_priority=classify_refresh_priority(fetch_context),
                    staleness_classification=classify_staleness(fetch_context),
                    observation_count_all_time=observation_counts.observation_count_all_time,
                    linked_deal_count=linked_deal_flags.linked_deal_count,
                    has_pending_review_deal=linked_deal_flags.has_pending_review_deal,
                    has_published_deal=linked_deal_flags.has_published_deal,
                )
            )
        return records

    def _load_latest_source_contexts(
        self,
        db: Session,
        tracked_products: list[TrackedProduct],
    ) -> dict[UUID, _LatestSourceCandidate | None]:
        asins = sorted({tracked_product.asin for tracked_product in tracked_products})
        if not asins:
            return {}

        asin_expression = ProductSourceRecord.source_attributes["asin"].astext
        domain_expression = ProductSourceRecord.source_attributes["domain_id"].astext
        rows = db.execute(
            select(
                asin_expression.label("asin"),
                domain_expression.label("raw_domain_id"),
                ProductSourceRecord.product_variant_id,
                ProductSourceRecord.source_title,
                ProductSourceRecord.source_url,
                Source.slug,
                Source.name,
            )
            .join(Source, Source.id == ProductSourceRecord.source_id)
            .where(asin_expression.in_(asins))
            .order_by(ProductSourceRecord.last_seen_at.desc(), ProductSourceRecord.created_at.desc())
        ).all()

        rows_by_asin: dict[str, list[_LatestSourceCandidate]] = {}
        for row in rows:
            rows_by_asin.setdefault(row.asin, []).append(
                _LatestSourceCandidate(
                    asin=row.asin,
                    raw_domain_id=row.raw_domain_id,
                    product_variant_id=row.product_variant_id,
                    source_title=row.source_title,
                    source_url=row.source_url,
                    source_slug=row.slug,
                    source_name=row.name,
                )
            )

        return {
            tracked_product.id: self._best_source_context_for_tracked_product(
                tracked_product,
                rows_by_asin.get(tracked_product.asin, []),
            )
            for tracked_product in tracked_products
        }

    def _best_source_context_for_tracked_product(
        self,
        tracked_product: TrackedProduct,
        candidates: list[_LatestSourceCandidate],
    ) -> _LatestSourceCandidate | None:
        if not candidates:
            return None
        exact_domain_match = [
            candidate
            for candidate in candidates
            if self._candidate_domain_id(candidate) == tracked_product.domain_id
        ]
        if exact_domain_match:
            return exact_domain_match[0]
        return candidates[0]

    def _candidate_domain_id(self, candidate: _LatestSourceCandidate) -> int | None:
        try:
            if candidate.raw_domain_id is not None:
                return int(candidate.raw_domain_id)
        except (TypeError, ValueError):
            pass

        source_url = candidate.source_url
        if source_url:
            try:
                host = (urlparse(source_url).hostname or "").casefold().removeprefix("www.")
            except ValueError:
                host = ""
            if host in AMAZON_DOMAIN_ID_BY_HOST:
                return AMAZON_DOMAIN_ID_BY_HOST[host]
        return None

    def _load_observation_counts(self, db: Session, variant_ids: list[UUID]) -> dict[UUID, _ObservationCounts]:
        if not variant_ids:
            return {}
        now = datetime.now(timezone.utc)
        observed_after_30d = now - timedelta(days=30)
        observed_after_90d = now - timedelta(days=90)
        rows = db.execute(
            select(
                ProductSourceRecord.product_variant_id,
                func.count(case((PriceObservation.observed_at >= observed_after_30d, 1))),
                func.count(case((PriceObservation.observed_at >= observed_after_90d, 1))),
                func.count(PriceObservation.id),
            )
            .join(ProductSourceRecord, ProductSourceRecord.id == PriceObservation.product_source_record_id)
            .where(ProductSourceRecord.product_variant_id.in_(variant_ids))
            .group_by(ProductSourceRecord.product_variant_id)
        ).all()
        return {
            product_variant_id: _ObservationCounts(
                observation_count_30d=int(count_30d),
                observation_count_90d=int(count_90d),
                observation_count_all_time=int(count_all_time),
            )
            for product_variant_id, count_30d, count_90d, count_all_time in rows
        }

    def _load_linked_deal_flags(self, db: Session, variant_ids: list[UUID]) -> dict[UUID, _LinkedDealFlags]:
        if not variant_ids:
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
            .where(Deal.product_variant_id.in_(variant_ids))
            .group_by(Deal.product_variant_id)
        ).all()
        return {
            product_variant_id: _LinkedDealFlags(
                linked_deal_count=int(linked_deal_count),
                has_pending_review_deal=bool(has_pending_review_deal),
                has_published_deal=bool(has_published_deal),
            )
            for product_variant_id, linked_deal_count, has_pending_review_deal, has_published_deal in rows
        }

    def _fetch_context(
        self,
        tracked_product: TrackedProduct,
        *,
        observation_counts: _ObservationCounts,
        linked_deal_count: int,
        has_pending_review_deal: bool,
        has_published_deal: bool,
    ) -> KeepaFetchContext:
        return KeepaFetchContext(
            asin=tracked_product.asin,
            observation_count_30d=observation_counts.observation_count_30d,
            observation_count_90d=observation_counts.observation_count_90d,
            observation_count_all_time=observation_counts.observation_count_all_time,
            last_refresh_attempt_at=tracked_product.last_refresh_attempt_at,
            last_refresh_succeeded_at=tracked_product.last_refresh_succeeded_at,
            last_refresh_failed_at=tracked_product.last_refresh_failed_at,
            last_refresh_status=tracked_product.last_refresh_status,
            last_refresh_failure_reason=tracked_product.last_refresh_failure_reason,
            consecutive_refresh_failures=tracked_product.consecutive_refresh_failures,
            next_refresh_eligible_at=tracked_product.next_refresh_eligible_at,
            linked_deal_count=linked_deal_count,
            has_pending_review_deal=has_pending_review_deal,
            has_published_deal=has_published_deal,
        )

    def _staleness_for_summary(self, tracked_product: TrackedProduct) -> str:
        return classify_staleness(
            KeepaFetchContext(
                asin=tracked_product.asin,
                last_refresh_attempt_at=tracked_product.last_refresh_attempt_at,
                last_refresh_succeeded_at=tracked_product.last_refresh_succeeded_at,
                last_refresh_failed_at=tracked_product.last_refresh_failed_at,
                last_refresh_status=tracked_product.last_refresh_status,
                consecutive_refresh_failures=tracked_product.consecutive_refresh_failures,
                next_refresh_eligible_at=tracked_product.next_refresh_eligible_at,
            )
        )


def get_active_tracked_asins(db: Session, limit: int = 100) -> list[TrackedProduct]:
    stmt = (
        select(TrackedProduct)
        .order_by(
            TrackedProduct.next_refresh_eligible_at.is_not(None).asc(),
            TrackedProduct.next_refresh_eligible_at.asc(),
            TrackedProduct.last_checked_at.is_not(None).asc(),
            TrackedProduct.last_checked_at.asc(),
            TrackedProduct.created_at.asc(),
        )
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def ensure_tracked_product_for_source_record(
    db: Session,
    product_source_record: ProductSourceRecord,
) -> TrackedProduct | None:
    asin = _normalized_asin((product_source_record.source_attributes or {}).get("asin"))
    if asin is None:
        return None

    domain_id = _resolved_domain_id(product_source_record)
    tracked_product = db.scalar(
        select(TrackedProduct).where(
            TrackedProduct.asin == asin,
            TrackedProduct.domain_id == domain_id,
        )
    )
    if tracked_product is not None:
        return tracked_product

    tracked_product = TrackedProduct(
        asin=asin,
        domain_id=domain_id,
    )
    db.add(tracked_product)
    db.flush()
    return tracked_product


def _resolved_domain_id(product_source_record: ProductSourceRecord) -> int:
    raw_domain_id = (product_source_record.source_attributes or {}).get("domain_id")
    try:
        if raw_domain_id is not None:
            return int(raw_domain_id)
    except (TypeError, ValueError):
        pass

    source_url = product_source_record.source_url
    if source_url:
        try:
            host = (urlparse(source_url).hostname or "").casefold().removeprefix("www.")
        except ValueError:
            host = ""
        if host in AMAZON_DOMAIN_ID_BY_HOST:
            return AMAZON_DOMAIN_ID_BY_HOST[host]

    return settings.keepa_domain_id


def _normalized_asin(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip().upper()
    return candidate or None
