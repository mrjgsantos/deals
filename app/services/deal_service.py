from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, and_, cast, exists, or_, select, true
from sqlalchemy.orm import Session, aliased, contains_eager, joinedload, selectinload

from app.db.enums import AICopyType, DealStatus, ReviewStatus, ReviewType
from app.db.models import AICopyDraft, Deal, ProductSourceRecord, ProductVariant, ReviewQueue
from app.ingestion.amazon_identifiers import extract_amazon_asin_from_url, normalize_asin

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DealRecord:
    id: UUID
    title: str
    status: str
    currency: str
    current_price: Any
    previous_price: Any
    savings_amount: Any
    savings_percent: Any
    deal_url: str | None
    summary: str | None
    source_id: UUID
    product_variant_id: UUID | None
    product_source_record_id: UUID | None
    detected_at: Any
    published_at: Any | None
    category: str | None
    source_category: str | None
    subcategories: list[str]
    asin: str | None
    score_breakdown: dict[str, Any]
    ai_copy_draft: dict[str, Any] | None
    image_url: str | None = None
    personalization_score: float | None = None


@dataclass(slots=True)
class DealPublicationResult:
    deal_id: UUID
    deal_status: str
    published_at: datetime


@dataclass(slots=True)
class ReviewQueueRecord:
    id: UUID
    status: str
    reason: str
    priority: int
    created_at: datetime
    resolved_at: datetime | None
    deal: DealRecord


@dataclass(slots=True)
class ReviewQueueListItemRecord:
    """Lightweight DTO for the approval queue card view.

    Contains only what is needed for rapid approve/reject decisions.
    No ai_copy_draft, no summary, no product_variant hierarchy — those
    are fetched on demand via the deal detail endpoint.
    """

    id: UUID
    priority: int
    created_at: datetime
    deal_id: UUID
    title: str
    currency: str
    current_price: Any
    previous_price: Any
    savings_amount: Any
    savings_percent: Any
    deal_url: str | None
    source_id: UUID
    source_category: str | None
    image_url: str | None
    quality_score: int | None
    business_score: int | None
    promotable: bool
    fake_discount: bool
    confidence_level: str | None
    quality_reasons: list[str]
    price_history: dict | None
    asin: str | None


@dataclass(slots=True)
class ReviewQueuePage:
    items: list[ReviewQueueListItemRecord]
    total: int
    has_more: bool


@dataclass(slots=True)
class DealsListItemRecord:
    """Lightweight DTO for the deals exploration card view."""

    id: UUID
    title: str
    status: str
    currency: str
    current_price: Any
    previous_price: Any
    savings_amount: Any
    savings_percent: Any
    deal_url: str | None
    detected_at: datetime
    source_id: UUID
    source_category: str | None
    image_url: str | None
    quality_score: int | None
    business_score: int | None
    promotable: bool
    fake_discount: bool
    confidence_level: str | None
    quality_reasons: list[str]
    price_history: dict | None
    asin: str | None


@dataclass(slots=True)
class DealsListPage:
    items: list[DealsListItemRecord]
    total: int
    has_more: bool


@dataclass(slots=True)
class PublishedDealsPage:
    deals: list[DealRecord]
    has_more: bool
    next_published_at: datetime | None
    next_id: UUID | None


class DealQueryService:
    def list_deals(self, db: Session, *, status: DealStatus | None = None) -> list[DealRecord]:
        stmt = self._base_query()
        if status is not None:
            stmt = stmt.where(Deal.status == status)
        deals = db.scalars(stmt.order_by(Deal.detected_at.desc())).unique().all()
        return [self._to_record(deal) for deal in deals]

    def get_deal(self, db: Session, deal_id: UUID) -> DealRecord | None:
        stmt = self._base_query().where(Deal.id == deal_id)
        deal = db.scalar(stmt)
        if deal is None:
            return None
        return self._to_record(deal)

    def list_published_deals_page(
        self,
        db: Session,
        *,
        limit: int,
        cursor_published_at: datetime | None = None,
        cursor_id: UUID | None = None,
    ) -> PublishedDealsPage:
        t0 = time.perf_counter()

        # Lateral subquery: returns at most 1 row (latest draft) per deal.
        # Because a lateral returns ≤1 row per left-side row, LIMIT on the
        # outer query is safe — no cartesian product inflates the result set.
        latest_draft_sq = (
            select(AICopyDraft)
            .where(AICopyDraft.deal_id == Deal.id)
            .order_by(AICopyDraft.generated_at.desc())
            .limit(1)
            .correlate(Deal)
            .lateral()
        )
        latest_draft = aliased(AICopyDraft, latest_draft_sq)

        stmt = (
            select(Deal)
            .outerjoin(Deal.product_variant)
            .outerjoin(ProductVariant.product)
            .outerjoin(Deal.product_source_record)
            .outerjoin(latest_draft, true())
            .options(
                contains_eager(Deal.product_variant).contains_eager(ProductVariant.product),
                contains_eager(Deal.product_source_record),
                contains_eager(Deal.ai_copy_drafts, alias=latest_draft),
            )
            .where(
                Deal.status.in_([DealStatus.APPROVED, DealStatus.PUBLISHED]),
                Deal.published_at.is_not(None),
            )
        )

        if cursor_published_at is not None and cursor_id is not None:
            stmt = stmt.where(
                or_(
                    Deal.published_at < cursor_published_at,
                    and_(Deal.published_at == cursor_published_at, Deal.id < cursor_id),
                )
            )

        rows = db.scalars(
            stmt.order_by(Deal.published_at.desc(), Deal.id.desc()).limit(limit + 1)
        ).unique().all()

        logger.warning("perf_published_deals_page query=%.1fms rows=%d limit=%d cursor=%s", (time.perf_counter() - t0) * 1000, len(rows), limit, cursor_published_at is not None)
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_row = page_rows[-1] if has_more and page_rows else None
        return PublishedDealsPage(
            deals=[self._to_record(deal) for deal in page_rows],
            has_more=has_more,
            next_published_at=next_row.published_at if next_row is not None else None,
            next_id=next_row.id if next_row is not None else None,
        )

    def _base_query(self):
        return select(Deal).options(
            # many-to-one: safe to JOIN, single round-trip
            joinedload(Deal.product_variant).joinedload(ProductVariant.product),
            joinedload(Deal.product_source_record),
            # one-to-many: selectinload to avoid cartesian product with LIMIT
            selectinload(Deal.ai_copy_drafts),
        )

    def _to_record(self, deal: Deal) -> DealRecord:
        return DealRecord(
            id=deal.id,
            title=deal.title,
            status=deal.status.value,
            currency=deal.currency,
            current_price=deal.current_price,
            previous_price=deal.previous_price,
            savings_amount=deal.savings_amount,
            savings_percent=deal.savings_percent,
            deal_url=deal.deal_url,
            summary=deal.summary,
            source_id=deal.source_id,
            product_variant_id=deal.product_variant_id,
            product_source_record_id=deal.product_source_record_id,
            detected_at=deal.detected_at,
            published_at=deal.published_at,
            category=self._extract_category(deal),
            source_category=deal.product_source_record.source_category if deal.product_source_record is not None else None,
            subcategories=[],
            asin=self._extract_asin(deal),
            image_url=deal.product_source_record.image_url if deal.product_source_record is not None else None,
            personalization_score=None,
            score_breakdown=self._extract_score_breakdown(deal),
            ai_copy_draft=self._extract_ai_draft(deal.ai_copy_drafts),
        )

    def _extract_category(self, deal: Deal) -> str | None:
        if deal.product_variant is not None and deal.product_variant.product is not None:
            return deal.product_variant.product.category
        if deal.product_source_record is not None:
            return deal.product_source_record.source_category
        return None

    def _extract_score_breakdown(self, deal: Deal) -> dict[str, Any]:
        metadata = deal.metadata_json or {}
        return {
            "quality_score": metadata.get("quality_score"),
            "quality_reasons": metadata.get("quality_reasons", []),
            "business_score": metadata.get("business_score"),
            "business_reasons": metadata.get("business_reasons", []),
            "promotable": metadata.get("promotable", False),
            "fake_discount": metadata.get("fake_discount", False),
            "price_history": metadata.get("price_aggregation"),
        }

    def _extract_asin(self, deal: Deal) -> str | None:
        if deal.product_source_record is not None:
            source_attributes = deal.product_source_record.source_attributes or {}
            asin = normalize_asin(source_attributes.get("asin"))
            if asin is not None:
                return asin
            if deal.product_source_record.source_url:
                return extract_amazon_asin_from_url(deal.product_source_record.source_url)
        if deal.deal_url:
            return extract_amazon_asin_from_url(deal.deal_url)
        return None

    def _extract_ai_draft(self, drafts: list[AICopyDraft]) -> dict[str, Any] | None:
        package_drafts = [draft for draft in drafts if draft.copy_type == AICopyType.PACKAGE]
        if not package_drafts:
            return None
        latest = max(package_drafts, key=lambda draft: draft.generated_at)
        try:
            content = json.loads(latest.content)
        except json.JSONDecodeError:
            content = {"raw": latest.content}
        return {
            "id": str(latest.id),
            "status": latest.status.value,
            "model_name": latest.model_name,
            "prompt_version": latest.prompt_version,
            "generated_at": latest.generated_at,
            "content": content,
            "warnings": (latest.metadata_json or {}).get("warnings", []),
        }

    def list_pending_review_items(self, db: Session) -> list[ReviewQueueRecord]:
        queue_stmt = (
            select(ReviewQueue)
            .join(Deal, Deal.id == ReviewQueue.entity_id)
            .where(
                ReviewQueue.entity_type == ReviewType.DEAL_VALIDATION,
                ReviewQueue.status == ReviewStatus.PENDING,
                Deal.status == DealStatus.PENDING_REVIEW,
            )
            .order_by(ReviewQueue.priority.asc(), ReviewQueue.created_at.asc())
        )
        review_items = db.scalars(queue_stmt).all()
        if not review_items:
            return []

        # Batch-load all deals with eager loading — replaces N individual db.get() calls.
        deal_ids = [item.entity_id for item in review_items]
        deals_stmt = self._base_query().where(Deal.id.in_(deal_ids))
        deals_by_id = {deal.id: deal for deal in db.scalars(deals_stmt).all()}

        results = []
        for item in review_items:
            deal = deals_by_id.get(item.entity_id)
            if deal is None:
                continue
            results.append(ReviewQueueRecord(
                id=item.id,
                status=item.status.value,
                reason=item.reason,
                priority=item.priority,
                created_at=item.created_at,
                resolved_at=item.resolved_at,
                deal=self._to_record(deal),
            ))
        return results

    def list_review_queue(self, db: Session, *, limit: int = 50, offset: int = 0) -> ReviewQueuePage:
        """Lightweight paginated queue for the approval card view.

        Issues 3 queries regardless of page size:
        1. ReviewQueue items (paginated)
        2. Deals batch (IN query)
        3. PSRs (selectinload, 1 IN query)
        """
        queue_stmt = (
            select(ReviewQueue)
            .join(Deal, Deal.id == ReviewQueue.entity_id)
            .where(
                ReviewQueue.entity_type == ReviewType.DEAL_VALIDATION,
                ReviewQueue.status == ReviewStatus.PENDING,
                Deal.status == DealStatus.PENDING_REVIEW,
            )
            .order_by(ReviewQueue.priority.asc(), ReviewQueue.created_at.asc())
            # Fetch one extra to determine has_more without a separate COUNT query.
            .limit(limit + 1)
            .offset(offset)
        )
        review_items = db.scalars(queue_stmt).all()
        has_more = len(review_items) > limit
        review_items = review_items[:limit]

        if not review_items:
            return ReviewQueuePage(items=[], total=offset, has_more=False)

        deal_ids = [item.entity_id for item in review_items]
        deals_stmt = (
            select(Deal)
            .where(Deal.id.in_(deal_ids))
            .options(selectinload(Deal.product_source_record))
        )
        deals_by_id = {deal.id: deal for deal in db.scalars(deals_stmt).all()}

        items = []
        for item in review_items:
            deal = deals_by_id.get(item.entity_id)
            if deal is None:
                continue
            items.append(self._to_list_item_record(item, deal))

        return ReviewQueuePage(items=items, total=offset + len(items), has_more=has_more)

    def list_deals_page(
        self,
        db: Session,
        *,
        status: DealStatus | None = None,
        source: str | None = None,
        min_score: int | None = None,
        min_savings: float | None = None,
        since_days: int | None = None,
        fake_discount_only: bool = False,
        sort_by: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> DealsListPage:
        """Paginated, filtered deals list for the exploration view.

        Issues 2 queries: one paginated deals query + one selectinload for PSRs.
        """
        stmt = select(Deal).options(selectinload(Deal.product_source_record))

        if status is not None:
            stmt = stmt.where(Deal.status == status)

        if source == "amazon":
            amazon_psr_subq = exists(
                select(ProductSourceRecord.id).where(
                    ProductSourceRecord.id == Deal.product_source_record_id,
                    ProductSourceRecord.source_attributes.has_key("asin"),
                )
            )
            stmt = stmt.where(
                or_(
                    Deal.deal_url.ilike("%amazon.%"),
                    amazon_psr_subq,
                )
            )
        elif source == "google":
            amazon_psr_subq = exists(
                select(ProductSourceRecord.id).where(
                    ProductSourceRecord.id == Deal.product_source_record_id,
                    ProductSourceRecord.source_attributes.has_key("asin"),
                )
            )
            stmt = stmt.where(
                and_(
                    or_(Deal.deal_url.is_(None), ~Deal.deal_url.ilike("%amazon.%")),
                    ~amazon_psr_subq,
                )
            )

        if min_score is not None:
            stmt = stmt.where(
                cast(Deal.metadata_json["quality_score"].astext, Integer) >= min_score
            )

        if min_savings is not None:
            stmt = stmt.where(Deal.savings_percent >= min_savings / 100)

        if since_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
            stmt = stmt.where(Deal.detected_at >= cutoff)

        if fake_discount_only:
            stmt = stmt.where(Deal.metadata_json["fake_discount"].astext == "true")

        if sort_by == "score":
            stmt = stmt.order_by(
                cast(Deal.metadata_json["quality_score"].astext, Integer).desc().nulls_last()
            )
        elif sort_by == "savings":
            stmt = stmt.order_by(Deal.savings_percent.desc().nulls_last())
        else:
            stmt = stmt.order_by(Deal.detected_at.desc())

        stmt = stmt.limit(limit + 1).offset(offset)
        rows = list(db.scalars(stmt).all())
        has_more = len(rows) > limit
        rows = rows[:limit]

        return DealsListPage(
            items=[self._to_deals_list_item_record(deal) for deal in rows],
            total=offset + len(rows),
            has_more=has_more,
        )

    def _to_deals_list_item_record(self, deal: Deal) -> DealsListItemRecord:
        metadata = deal.metadata_json or {}
        psr = deal.product_source_record
        return DealsListItemRecord(
            id=deal.id,
            title=deal.title,
            status=deal.status.value,
            currency=deal.currency,
            current_price=deal.current_price,
            previous_price=deal.previous_price,
            savings_amount=deal.savings_amount,
            savings_percent=deal.savings_percent,
            deal_url=deal.deal_url,
            detected_at=deal.detected_at,
            source_id=deal.source_id,
            source_category=psr.source_category if psr is not None else None,
            image_url=psr.image_url if psr is not None else None,
            quality_score=metadata.get("quality_score"),
            business_score=metadata.get("business_score"),
            promotable=metadata.get("promotable", False),
            fake_discount=metadata.get("fake_discount", False),
            confidence_level=metadata.get("confidence_level"),
            quality_reasons=metadata.get("quality_reasons") or [],
            price_history=metadata.get("price_aggregation"),
            asin=self._extract_asin(deal),
        )

    def _to_list_item_record(self, item: ReviewQueue, deal: Deal) -> ReviewQueueListItemRecord:
        metadata = deal.metadata_json or {}
        psr = deal.product_source_record
        return ReviewQueueListItemRecord(
            id=item.id,
            priority=item.priority,
            created_at=item.created_at,
            deal_id=deal.id,
            title=deal.title,
            currency=deal.currency,
            current_price=deal.current_price,
            previous_price=deal.previous_price,
            savings_amount=deal.savings_amount,
            savings_percent=deal.savings_percent,
            deal_url=deal.deal_url,
            source_id=deal.source_id,
            source_category=psr.source_category if psr is not None else None,
            image_url=psr.image_url if psr is not None else None,
            quality_score=metadata.get("quality_score"),
            business_score=metadata.get("business_score"),
            promotable=metadata.get("promotable", False),
            fake_discount=metadata.get("fake_discount", False),
            confidence_level=metadata.get("confidence_level"),
            quality_reasons=metadata.get("quality_reasons") or [],
            price_history=metadata.get("price_aggregation"),
            asin=self._extract_asin(deal),
        )


class DealPublicationService:
    def mark_published(self, db: Session, deal_id: UUID) -> DealPublicationResult:
        deal = db.get(Deal, deal_id)
        if deal is None:
            raise ValueError("deal_not_found")
        if deal.status not in {DealStatus.APPROVED, DealStatus.PUBLISHED}:
            raise ValueError("invalid_deal_state")
        if deal.published_at is None or deal.status != DealStatus.PUBLISHED:
            previous_status = deal.status.value
            deal.published_at = datetime.now(timezone.utc)
            deal.status = DealStatus.PUBLISHED
            db.add(deal)
            db.commit()
            db.refresh(deal)
            logger.info(
                "deal_publication_marked deal_id=%s previous_status=%s current_status=%s published_at=%s",
                deal.id,
                previous_status,
                deal.status.value,
                deal.published_at.isoformat(),
            )
        else:
            logger.info(
                "deal_publication_noop deal_id=%s current_status=%s published_at=%s",
                deal.id,
                deal.status.value,
                deal.published_at.isoformat(),
            )
        return DealPublicationResult(
            deal_id=deal.id,
            deal_status=deal.status.value,
            published_at=deal.published_at,
        )
