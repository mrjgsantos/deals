from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.client import build_model_client_from_env
from app.ai.schemas import StructuredDealCopyInput
from app.ai.service import AICopyGenerationService
from app.core.config import settings
from app.db.enums import AICopyType, DealStatus
from app.db.models import AICopyDraft, Deal, Merchant, Product, ProductVariant
from app.jobs.common import job_session, run_job


def main() -> int:
    def _runner(logger):
        now = datetime.now(UTC)
        client = build_model_client_from_env()
        service = AICopyGenerationService(client=client)

        with job_session() as db:
            deals = db.scalars(
                select(Deal)
                .options(selectinload(Deal.ai_copy_drafts))
                .where(Deal.status.in_([DealStatus.PENDING_REVIEW, DealStatus.APPROVED]))
            ).all()

            generated = 0
            skipped = 0

            for deal in deals:
                metadata = deal.metadata_json or {}
                if not metadata.get("promotable", False) or metadata.get("fake_discount", False):
                    skipped += 1
                    continue

                existing = _existing_draft_today(
                    drafts=deal.ai_copy_drafts,
                    day=now.date(),
                )
                if existing:
                    skipped += 1
                    continue

                if deal.product_variant_id is None:
                    skipped += 1
                    continue

                variant = db.get(ProductVariant, deal.product_variant_id)
                product = db.get(Product, variant.product_id) if variant else None
                if product is None:
                    skipped += 1
                    continue
                merchant = db.get(Merchant, product.merchant_id) if product.merchant_id else None

                structured_input = StructuredDealCopyInput(
                    deal_id=str(deal.id),
                    product_name=product.normalized_name,
                    merchant_name=merchant.canonical_name if merchant else None,
                    brand=product.brand,
                    category=product.category,
                    current_price=deal.current_price,
                    previous_price=deal.previous_price,
                    currency=deal.currency,
                    savings_amount=deal.savings_amount,
                    savings_percent=deal.savings_percent,
                    quality_score=metadata.get("quality_score", 0),
                    business_score=metadata.get("business_score", 0),
                    promotable=metadata.get("promotable", False),
                    fake_discount=metadata.get("fake_discount", False),
                    days_at_current_price=(metadata.get("price_aggregation") or {}).get("days_at_current_price", 0),
                    avg_30d=_to_decimal((metadata.get("price_aggregation") or {}).get("avg_30d")),
                    avg_90d=_to_decimal((metadata.get("price_aggregation") or {}).get("avg_90d")),
                    min_90d=_to_decimal((metadata.get("price_aggregation") or {}).get("min_90d")),
                    all_time_min=_to_decimal((metadata.get("price_aggregation") or {}).get("all_time_min")),
                    variant_summary=_variant_summary(variant),
                )

                try:
                    service.generate_and_persist(
                        db,
                        input_data=structured_input,
                        model_name=settings.ai_copy_model_name,
                        prompt_version=settings.ai_copy_prompt_version,
                    )
                    generated += 1
                except Exception:
                    logger.exception("daily_ai_drafts_generate_failed deal_id=%s", deal.id)
                    skipped += 1

            logger.info("daily_ai_drafts_complete generated=%s skipped=%s", generated, skipped)
        return 0

    return run_job("daily_ai_drafts", _runner)


def _existing_draft_today(drafts: list[AICopyDraft], day) -> bool:
    for draft in drafts:
        if draft.copy_type != AICopyType.PACKAGE:
            continue
        if draft.generated_at.date() == day:
            return True
    return False


def _to_decimal(value):
    from decimal import Decimal

    if value is None:
        return None
    return Decimal(str(value))


def _variant_summary(variant: ProductVariant) -> str | None:
    parts = []
    if variant.pack_count is not None:
        parts.append(f"{variant.pack_count}-pack")
    if variant.weight is not None and variant.weight_unit:
        parts.append(f"{variant.weight}{variant.weight_unit}")
    if variant.volume is not None and variant.volume_unit:
        parts.append(f"{variant.volume}{variant.volume_unit}")
    if variant.size:
        parts.append(f"size {variant.size}")
    if variant.is_bundle:
        parts.append("bundle")
    return ", ".join(parts) if parts else None


if __name__ == "__main__":
    raise SystemExit(main())
