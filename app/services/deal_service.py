from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import AICopyType, DealStatus, ReviewStatus, ReviewType
from app.db.models import AICopyDraft, Deal, ProductVariant, ReviewQueue
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
    personalization_score: float | None
    score_breakdown: dict[str, Any]
    ai_copy_draft: dict[str, Any] | None


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
        deals = db.scalars(stmt.order_by(Deal.detected_at.desc())).all()
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
        stmt = self._base_query().where(
            Deal.status.in_([DealStatus.APPROVED, DealStatus.PUBLISHED]),
            Deal.published_at.is_not(None),
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
        ).all()
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
            selectinload(Deal.ai_copy_drafts),
            selectinload(Deal.product_variant).selectinload(ProductVariant.product),
            selectinload(Deal.product_source_record),
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
        stmt = (
            select(ReviewQueue)
            .join(Deal, Deal.id == ReviewQueue.entity_id)
            .where(
                ReviewQueue.entity_type == ReviewType.DEAL_VALIDATION,
                ReviewQueue.status == ReviewStatus.PENDING,
                Deal.status == DealStatus.PENDING_REVIEW,
            )
            .order_by(ReviewQueue.priority.asc(), ReviewQueue.created_at.asc())
        )
        review_items = db.scalars(stmt).all()
        return [self._to_review_queue_record(db, item) for item in review_items]

    def _to_review_queue_record(self, db: Session, item: ReviewQueue) -> ReviewQueueRecord:
        deal = db.get(Deal, item.entity_id)
        if deal is None:
            raise ValueError(f"deal_not_found_for_review_queue:{item.id}")
        return ReviewQueueRecord(
            id=item.id,
            status=item.status.value,
            reason=item.reason,
            priority=item.priority,
            created_at=item.created_at,
            resolved_at=item.resolved_at,
            deal=self._to_record(deal),
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
