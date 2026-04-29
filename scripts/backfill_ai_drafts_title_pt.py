"""One-off script: regenerate AI drafts for published deals that lack title_pt.

Usage:
    docker compose run --rm app python scripts/backfill_ai_drafts_title_pt.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.client import build_model_client_from_env
from app.ai.schemas import StructuredDealCopyInput
from app.ai.service import AICopyGenerationService
from app.core.config import settings
from app.db.enums import AICopyType, DealStatus
from app.db.models import AICopyDraft, Deal, Merchant, Product, ProductVariant
from app.jobs.common import job_session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _has_title_pt(drafts: list[AICopyDraft]) -> bool:
    package_drafts = [d for d in drafts if d.copy_type == AICopyType.PACKAGE]
    if not package_drafts:
        return False
    latest = max(package_drafts, key=lambda d: d.generated_at)
    try:
        content = json.loads(latest.content)
        return bool(content.get("title_pt"))
    except (json.JSONDecodeError, AttributeError):
        return False


def _to_decimal(value) -> Decimal | None:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without calling the API")
    parser.add_argument("--limit", type=int, default=0, help="Max deals to process (0 = all)")
    args = parser.parse_args()

    client = build_model_client_from_env()
    service = AICopyGenerationService(client=client)

    generated = 0
    skipped = 0
    failed = 0

    with job_session() as db:
        deals = db.scalars(
            select(Deal)
            .options(selectinload(Deal.ai_copy_drafts))
            .where(Deal.status == DealStatus.PUBLISHED)
        ).all()

        log.info("Found %d published deals", len(deals))

        for deal in deals:
            if args.limit and generated + failed >= args.limit:
                break

            if _has_title_pt(deal.ai_copy_drafts):
                skipped += 1
                continue

            metadata = deal.metadata_json or {}
            if not metadata.get("promotable", False) or metadata.get("fake_discount", False):
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

            if args.dry_run:
                log.info("[dry-run] Would generate draft for deal %s (%s)", deal.id, product.normalized_name[:60])
                generated += 1
                continue

            try:
                service.generate_and_persist(
                    db,
                    input_data=structured_input,
                    model_name=settings.ai_copy_model_name,
                    prompt_version=settings.ai_copy_prompt_version,
                )
                db.flush()
                generated += 1
                log.info("Generated draft %d for deal %s (%s)", generated, deal.id, product.normalized_name[:60])
            except Exception:
                log.exception("Failed for deal %s", deal.id)
                failed += 1

        if not args.dry_run:
            db.commit()

    log.info("Done — generated=%d skipped=%d failed=%d", generated, skipped, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
