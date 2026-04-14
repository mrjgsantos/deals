from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AvailabilityStatus
from app.db.models import (
    AsinIngestionCheckpoint,
    Merchant,
    PriceObservation,
    Product,
    ProductSourceRecord,
    ProductVariant,
    RawIngestionRecord,
    Source,
)
from app.ingestion.amazon_identifiers import canonicalize_amazon_product_url, normalize_asin
from app.ingestion.exceptions import PayloadValidationError, RecordRejectedError, SourceNotFoundError
from app.ingestion.interfaces import RecordNormalizer, SourceParser
from app.ingestion.schemas import IngestionBatchResult, IngestionRecordResult, NormalizedIngestionRecord
from app.integrations.keepa_client import fetch_product_by_asin
from app.integrations.keepa_fetch_policy import (
    KeepaFetchContext,
    KeepaFetchRunState,
    should_fetch_keepa_for_record,
)
from app.integrations.keepa_history import extract_keepa_price_points
from app.matching.service import MatchingService
from app.matching.types import Matcher
from app.pricing.aggregation import aggregate_price_history_for_variant
from app.services.deal_generation_service import DealGenerationService

logger = logging.getLogger(__name__)
MAX_KEEPA_HISTORY_POINTS = 90
ASIN_DEDUPE_WINDOW = timedelta(hours=24)


class IngestionService:
    def __init__(
        self,
        parser: SourceParser,
        normalizer: RecordNormalizer,
        matcher: Matcher | None = None,
        deal_generation_service: DealGenerationService | None = None,
    ) -> None:
        self.parser = parser
        self.normalizer = normalizer
        self.matcher = matcher or MatchingService()
        self.deal_generation_service = deal_generation_service or DealGenerationService()

    def ingest(self, db: Session, source_slug: str, payload: Any, *, commit: bool = False) -> IngestionBatchResult:
        source = self._get_source(db, source_slug)
        parsed_records = self.parser.parse(payload)
        self._validate_parsed_records(parsed_records)
        result = IngestionBatchResult(source_slug=source.slug, parser_name=self.parser.parser_name)
        keepa_run_state = KeepaFetchRunState()
        logger.info(
            "ingestion_batch_started source=%s parser=%s parsed_record_count=%s commit=%s",
            source.slug,
            self.parser.parser_name,
            len(parsed_records),
            commit,
        )

        total_records = len(parsed_records)
        for parsed_record in parsed_records:
            result.processed += 1
            logger.info(
                "ingestion_record_start source=%s parser=%s record=%s/%s external_id=%s",
                source.slug,
                self.parser.parser_name,
                result.processed,
                total_records,
                parsed_record.external_id,
            )
            record_start = time.monotonic()
            raw_record = RawIngestionRecord(
                source_id=source.id,
                parser_name=self.parser.parser_name,
                external_id=parsed_record.external_id,
                raw_payload=parsed_record.raw_payload,
                status="pending",
            )
            db.add(raw_record)
            db.flush()

            try:
                with db.begin_nested():
                    normalized = self.normalizer.normalize(parsed_record)
                    dedupe_asin = self._normalized_asin(normalized)
                    if self._should_skip_recent_asin(
                        db=db,
                        source=source,
                        asin=dedupe_asin,
                    ):
                        write_result = self._mark_dedupe_skipped(
                            raw_record=raw_record,
                            normalized=normalized,
                            asin=dedupe_asin,
                        )
                        result.skipped_due_to_dedupe += 1
                    else:
                        write_result = self._persist_normalized_record(
                            db=db,
                            source=source,
                            raw_record=raw_record,
                            normalized=normalized,
                            keepa_run_state=keepa_run_state,
                            dedupe_asin=dedupe_asin,
                        )
                        result.accepted += 1
                result.records.append(write_result)
                logger.info(
                    "ingestion_record_done source=%s record=%s/%s external_id=%s elapsed_s=%.2f",
                    source.slug,
                    result.processed,
                    total_records,
                    parsed_record.external_id,
                    time.monotonic() - record_start,
                )
            except RecordRejectedError as exc:
                raw_record.status = "rejected"
                raw_record.rejection_reason = str(exc)
                raw_record.processed_at = datetime.now(timezone.utc)
                db.flush()
                result.rejected += 1
                result.records.append(
                    IngestionRecordResult(
                        raw_ingestion_record_id=str(raw_record.id),
                        status="rejected",
                        rejection_reason=str(exc),
                    )
                )
                logger.info(
                    "ingestion_record_done source=%s record=%s/%s external_id=%s status=rejected elapsed_s=%.2f",
                    source.slug,
                    result.processed,
                    total_records,
                    parsed_record.external_id,
                    time.monotonic() - record_start,
                )
            except Exception as exc:
                raw_record.status = "failed"
                raw_record.rejection_reason = "internal_error"
                raw_record.processed_at = datetime.now(timezone.utc)
                db.flush()
                logger.exception(
                    "ingestion_record_failed source=%s parser=%s external_id=%s error=%s elapsed_s=%.2f",
                    source.slug,
                    self.parser.parser_name,
                    parsed_record.external_id,
                    exc,
                    time.monotonic() - record_start,
                )
                result.rejected += 1
                result.records.append(
                    IngestionRecordResult(
                        raw_ingestion_record_id=str(raw_record.id),
                        status="failed",
                        rejection_reason="internal_error",
                    )
                )

        if commit:
            db.commit()
        logger.info(
            "ingestion_batch_complete source=%s parser=%s processed=%s accepted=%s rejected=%s skipped_due_to_dedupe=%s",
            source.slug,
            self.parser.parser_name,
            result.processed,
            result.accepted,
            result.rejected,
            result.skipped_due_to_dedupe,
        )
        return result

    def _persist_normalized_record(
        self,
        db: Session,
        source: Source,
        raw_record: RawIngestionRecord,
        normalized: NormalizedIngestionRecord,
        keepa_run_state: KeepaFetchRunState | None = None,
        dedupe_asin: str | None = None,
    ) -> IngestionRecordResult:
        _match_start = time.monotonic()
        match_decision = self.matcher.match_normalized_record(db, normalized)
        logger.debug(
            "ingestion_phase_match source=%s external_id=%s elapsed_s=%.2f matched=%s strategy=%s",
            source.slug,
            normalized.external_id,
            time.monotonic() - _match_start,
            match_decision.matched,
            match_decision.match_strategy,
        )
        merchant = self._get_or_create_merchant(db, normalized)
        product_source_record = self._get_or_create_product_source_record(db, source, normalized)
        db.add(product_source_record)
        product = self._get_or_create_product(db, product_source_record, normalized, merchant, match_decision)
        product_variant = self._get_or_create_product_variant(
            db,
            product_source_record,
            product,
            normalized,
            match_decision,
        )

        product_source_record.merchant = merchant
        product_source_record.product = product
        product_source_record.product_variant = product_variant
        normalized_product_url = str(normalized.product_url)
        canonical_product_url = canonicalize_amazon_product_url(normalized_product_url) or normalized_product_url

        product_source_record.source_url = canonical_product_url
        product_source_record.image_url = normalized.image_url
        product_source_record.source_title = normalized.source_title
        product_source_record.source_brand = normalized.source_brand
        product_source_record.source_description = normalized.source_description
        product_source_record.source_category = normalized.source_category
        product_source_record.currency = normalized.currency
        product_source_record.availability_status = normalized.availability_status
        product_source_record.source_attributes = normalized.source_attributes
        product_source_record.raw_payload = {
            "product_url": canonical_product_url,
            "image_url": normalized.image_url,
            "external_id": normalized.external_id,
        }
        product_source_record.last_seen_at = normalized.observed_at
        if product_source_record.first_seen_at is None:
            product_source_record.first_seen_at = normalized.observed_at
        product_source_record.matched_at = datetime.now(timezone.utc)

        price_observation, duplicate_observation = self._create_or_reuse_price_observation(
            db=db,
            product_source_record=product_source_record,
            normalized=normalized,
            source_slug=source.slug,
        )
        _history_start = time.monotonic()
        keepa_history_inserted = self._persist_keepa_history_observations_safely(
            db=db,
            source=source,
            product_source_record=product_source_record,
            normalized=normalized,
        )
        logger.info(
            "ingestion_phase_keepa_history source=%s external_id=%s inserted=%s elapsed_s=%.2f",
            source.slug,
            normalized.external_id,
            keepa_history_inserted,
            time.monotonic() - _history_start,
        )
        keepa_fetch_inserted = self._enrich_with_keepa_history_if_needed_safely(
            db=db,
            source=source,
            product_source_record=product_source_record,
            product_variant=product_variant,
            normalized=normalized,
            keepa_run_state=keepa_run_state,
        )

        raw_record.status = "duplicate" if duplicate_observation else "accepted"
        raw_record.product_source_record = product_source_record
        raw_record.normalized_payload = normalized.model_dump(mode="json")
        raw_record.processed_at = datetime.now(timezone.utc)
        self._touch_asin_checkpoint(
            db=db,
            source=source,
            asin=dedupe_asin,
            processed_at=raw_record.processed_at,
        )
        _sync_start = time.monotonic()
        self._sync_review_candidate(
            db=db,
            source=source,
            product_source_record=product_source_record,
            price_observation=price_observation,
        )
        logger.info(
            "ingestion_phase_deal_sync source=%s external_id=%s elapsed_s=%.2f",
            source.slug,
            normalized.external_id,
            time.monotonic() - _sync_start,
        )
        logger.info(
            "ingestion_record_persisted source=%s external_id=%s status=%s match_strategy=%s match_reason=%s matched=%s duplicate_observation=%s keepa_history_inserted=%s keepa_fetch_inserted=%s product_source_record_id=%s product_variant_id=%s price_observation_id=%s",
            source.slug,
            normalized.external_id,
            raw_record.status,
            match_decision.match_strategy,
            match_decision.reason,
            match_decision.matched,
            duplicate_observation,
            keepa_history_inserted,
            keepa_fetch_inserted,
            product_source_record.id,
            product_variant.id if product_variant is not None else None,
            price_observation.id,
        )

        return IngestionRecordResult(
            raw_ingestion_record_id=str(raw_record.id),
            product_source_record_id=str(product_source_record.id),
            price_observation_id=str(price_observation.id),
            status="duplicate" if duplicate_observation else "accepted",
        )

    def _should_skip_recent_asin(
        self,
        *,
        db: Session,
        source: Source,
        asin: str | None,
        now: datetime | None = None,
    ) -> bool:
        if asin is None:
            return False
        checkpoint = self._get_asin_checkpoint(db=db, source=source, asin=asin)
        if checkpoint is None:
            return False
        reference_time = now or datetime.now(timezone.utc)
        return checkpoint.last_processed_at >= (reference_time - ASIN_DEDUPE_WINDOW)

    def _mark_dedupe_skipped(
        self,
        *,
        raw_record: RawIngestionRecord,
        normalized: NormalizedIngestionRecord,
        asin: str | None,
    ) -> IngestionRecordResult:
        raw_record.status = "skipped"
        raw_record.rejection_reason = "recent_asin_dedupe"
        raw_record.normalized_payload = normalized.model_dump(mode="json")
        raw_record.processed_at = datetime.now(timezone.utc)
        logger.info(
            "ingestion_record_skipped_recent_asin_dedupe external_id=%s asin=%s raw_ingestion_record_id=%s",
            normalized.external_id,
            asin,
            raw_record.id,
        )
        return IngestionRecordResult(
            raw_ingestion_record_id=str(raw_record.id),
            status="skipped",
            rejection_reason="recent_asin_dedupe",
        )

    def _get_asin_checkpoint(
        self,
        *,
        db: Session,
        source: Source,
        asin: str,
    ) -> AsinIngestionCheckpoint | None:
        return db.scalar(
            select(AsinIngestionCheckpoint).where(
                AsinIngestionCheckpoint.source_id == source.id,
                AsinIngestionCheckpoint.asin == asin,
            )
        )

    def _touch_asin_checkpoint(
        self,
        *,
        db: Session,
        source: Source,
        asin: str | None,
        processed_at: datetime,
    ) -> None:
        if asin is None:
            return
        checkpoint = self._get_asin_checkpoint(db=db, source=source, asin=asin)
        if checkpoint is None:
            checkpoint = AsinIngestionCheckpoint(
                source_id=source.id,
                asin=asin,
                last_processed_at=processed_at,
            )
            db.add(checkpoint)
            return
        checkpoint.last_processed_at = processed_at

    def _normalized_asin(self, normalized: NormalizedIngestionRecord) -> str | None:
        return normalize_asin((normalized.source_attributes or {}).get("asin"))

    def _get_source(self, db: Session, source_slug: str) -> Source:
        source = db.scalar(select(Source).where(Source.slug == source_slug))
        if source is None:
            raise SourceNotFoundError(f"Source not found for slug '{source_slug}'")
        return source

    def _validate_parsed_records(self, parsed_records: Any) -> None:
        if not isinstance(parsed_records, list):
            raise PayloadValidationError("parser must return a list of records")
        if len(parsed_records) > 5_000:
            raise PayloadValidationError("parser returned too many records")

    def _get_or_create_merchant(
        self,
        db: Session,
        normalized: NormalizedIngestionRecord,
    ) -> Merchant | None:
        if not normalized.merchant_slug or not normalized.merchant_name:
            return None
        merchant = db.scalar(select(Merchant).where(Merchant.slug == normalized.merchant_slug))
        if merchant is None:
            merchant = Merchant(
                canonical_name=normalized.merchant_name,
                slug=normalized.merchant_slug,
            )
            db.add(merchant)
            db.flush()
        else:
            merchant.canonical_name = normalized.merchant_name
        return merchant

    def _get_or_create_product_source_record(
        self,
        db: Session,
        source: Source,
        normalized: NormalizedIngestionRecord,
    ) -> ProductSourceRecord:
        existing = db.scalar(
            select(ProductSourceRecord).where(
                ProductSourceRecord.source_id == source.id,
                ProductSourceRecord.external_id == normalized.external_id,
            )
        )
        if existing is not None:
            return existing
        product_source_record = ProductSourceRecord(
            source_id=source.id,
            external_id=normalized.external_id,
            source_url=str(normalized.product_url),
            image_url=normalized.image_url,
            source_title=normalized.source_title,
            source_brand=normalized.source_brand,
            source_description=normalized.source_description,
            source_category=normalized.source_category,
            currency=normalized.currency,
            availability_status=normalized.availability_status,
            source_attributes=normalized.source_attributes,
            raw_payload={
                "product_url": str(normalized.product_url),
                "image_url": normalized.image_url,
                "external_id": normalized.external_id,
            },
            first_seen_at=normalized.observed_at,
            last_seen_at=normalized.observed_at,
        )
        db.add(product_source_record)
        db.flush()
        return product_source_record

    def _get_or_create_product(
        self,
        db: Session,
        product_source_record: ProductSourceRecord,
        normalized: NormalizedIngestionRecord,
        merchant: Merchant | None,
        match_decision,
    ) -> Product:
        product = product_source_record.product
        if product is None and match_decision.matched and match_decision.product_id:
            product = db.get(Product, match_decision.product_id)
        if product is None:
            product = Product(
                merchant=merchant,
                normalized_name=normalized.normalized_name,
                brand=normalized.brand,
                category=normalized.category,
                description=normalized.description,
                metadata_json=self._merged_metadata(
                    None,
                    {"source_external_id": normalized.external_id},
                ),
            )
            db.add(product)
            db.flush()
        else:
            product.merchant = merchant
            product.normalized_name = normalized.normalized_name
            product.brand = normalized.brand
            product.category = normalized.category
            product.description = normalized.description
            product.metadata_json = self._merged_metadata(
                product.metadata_json,
                {"source_external_id": normalized.external_id},
            )
        return product

    def _get_or_create_product_variant(
        self,
        db: Session,
        product_source_record: ProductSourceRecord,
        product: Product,
        normalized: NormalizedIngestionRecord,
        match_decision,
    ) -> ProductVariant:
        variant = product_source_record.product_variant
        if variant is None and match_decision.matched and match_decision.product_variant_id:
            variant = db.get(ProductVariant, match_decision.product_variant_id)
        if variant is None:
            variant = db.scalar(
                select(ProductVariant).where(
                    ProductVariant.product_id == product.id,
                    ProductVariant.variant_key == normalized.variant_key,
                )
            )
        if variant is None:
            variant = ProductVariant(
                product=product,
                variant_key=normalized.variant_key,
                sku=self._clean_identifier(normalized.source_attributes.get("sku")),
                gtin=self._clean_identifier(normalized.source_attributes.get("gtin")),
                mpn=self._clean_identifier(normalized.source_attributes.get("mpn")),
                pack_count=normalized.pack_count,
                quantity=normalized.quantity,
                quantity_unit=normalized.quantity_unit,
                weight=normalized.weight,
                weight_unit=normalized.weight_unit,
                volume=normalized.volume,
                volume_unit=normalized.volume_unit,
                size=normalized.size,
                color=normalized.color,
                material=normalized.material,
                is_bundle=normalized.is_bundle,
                metadata_json=self._merged_metadata(
                    None,
                    {"source_external_id": normalized.external_id},
                ),
            )
            db.add(variant)
            db.flush()
        else:
            variant.product = product
            variant.variant_key = normalized.variant_key
            variant.sku = self._clean_identifier(normalized.source_attributes.get("sku")) or variant.sku
            variant.gtin = self._clean_identifier(normalized.source_attributes.get("gtin")) or variant.gtin
            variant.mpn = self._clean_identifier(normalized.source_attributes.get("mpn")) or variant.mpn
            variant.pack_count = normalized.pack_count
            variant.quantity = normalized.quantity
            variant.quantity_unit = normalized.quantity_unit
            variant.weight = normalized.weight
            variant.weight_unit = normalized.weight_unit
            variant.volume = normalized.volume
            variant.volume_unit = normalized.volume_unit
            variant.size = normalized.size
            variant.color = normalized.color
            variant.material = normalized.material
            variant.is_bundle = normalized.is_bundle
            variant.metadata_json = self._merged_metadata(
                variant.metadata_json,
                {"source_external_id": normalized.external_id},
            )
        return variant

    def _create_or_reuse_price_observation(
        self,
        db: Session,
        product_source_record: ProductSourceRecord,
        normalized: NormalizedIngestionRecord,
        source_slug: str,
    ) -> tuple[PriceObservation, bool]:
        observed_hash = self._build_observed_hash(normalized, source_slug)
        existing = db.scalar(
            select(PriceObservation).where(
                PriceObservation.product_source_record_id == product_source_record.id,
                PriceObservation.observed_hash == observed_hash,
            )
        )
        if existing is not None:
            return existing, True

        price_observation = PriceObservation(
            product_source_record=product_source_record,
            observed_at=normalized.observed_at,
            currency=normalized.currency,
            list_price=normalized.list_price,
            sale_price=normalized.current_price,
            shipping_price=normalized.shipping_price,
            total_price=normalized.total_price,
            in_stock=normalized.availability_status == AvailabilityStatus.IN_STOCK,
            is_promotional=bool(normalized.list_price and normalized.list_price > normalized.current_price),
            observed_hash=observed_hash,
            metadata_json={"source": source_slug},
        )
        db.add(price_observation)
        db.flush()
        return price_observation, False

    def _build_observed_hash(self, normalized: NormalizedIngestionRecord, source_slug: str) -> str:
        return self._build_observed_hash_for_values(
            source_slug=source_slug,
            external_id=normalized.external_id,
            currency=normalized.currency,
            current_price=normalized.current_price,
            list_price=normalized.list_price,
            shipping_price=normalized.shipping_price,
            total_price=normalized.total_price,
            availability_status=normalized.availability_status,
            observed_at=normalized.observed_at,
        )

    def _build_observed_hash_for_values(
        self,
        *,
        source_slug: str,
        external_id: str,
        currency: str,
        current_price,
        list_price,
        shipping_price,
        total_price,
        availability_status: AvailabilityStatus,
        observed_at: datetime,
    ) -> str:
        payload = {
            "source_slug": source_slug,
            "external_id": external_id,
            "currency": currency,
            "current_price": str(current_price),
            "list_price": str(list_price) if list_price is not None else None,
            "shipping_price": str(shipping_price) if shipping_price is not None else None,
            "total_price": str(total_price),
            "availability_status": availability_status.value,
            "observed_at": observed_at.isoformat(),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _persist_keepa_history_observations_safely(
        self,
        db: Session,
        source: Source,
        product_source_record: ProductSourceRecord,
        normalized: NormalizedIngestionRecord,
    ) -> int:
        try:
            inserted = self._persist_keepa_history_observations(
                db=db,
                source=source,
                product_source_record=product_source_record,
                normalized=normalized,
            )
            if inserted > 0:
                logger.info(
                    "keepa_history_persisted source=%s external_id=%s asin=%s inserted=%s product_source_record_id=%s",
                    source.slug,
                    normalized.external_id,
                    (normalized.source_attributes or {}).get("asin"),
                    inserted,
                    product_source_record.id,
                )
            elif source.slug == "amazon-keepa" and (normalized.source_attributes or {}).get("asin"):
                logger.info(
                    "keepa_history_unavailable source=%s external_id=%s asin=%s reason=no_history_points product_source_record_id=%s",
                    source.slug,
                    normalized.external_id,
                    (normalized.source_attributes or {}).get("asin"),
                    product_source_record.id,
                )
            return inserted
        except Exception:
            logger.exception(
                "keepa_history_enrichment_failed source=%s product_source_record_id=%s external_id=%s",
                source.slug,
                product_source_record.id,
                normalized.external_id,
            )
            return 0

    def _persist_keepa_history_observations(
        self,
        db: Session,
        source: Source,
        product_source_record: ProductSourceRecord,
        normalized: NormalizedIngestionRecord,
    ) -> int:
        if source.slug != "amazon-keepa":
            return 0
        if not (normalized.source_attributes or {}).get("asin"):
            return 0

        return self._persist_keepa_history_observations_from_payload(
            db=db,
            source=source,
            product_source_record=product_source_record,
            normalized=normalized,
            keepa_product_payload=normalized.raw_payload,
        )

    def _persist_keepa_history_observations_from_payload(
        self,
        db: Session,
        source: Source,
        product_source_record: ProductSourceRecord,
        normalized: NormalizedIngestionRecord,
        *,
        keepa_product_payload: dict[str, Any],
    ) -> int:
        history_points = extract_keepa_price_points(keepa_product_payload, history_key="NEW")
        if not history_points:
            history_points = extract_keepa_price_points(keepa_product_payload, history_key="AMAZON")
        if not history_points:
            return 0

        filtered_points = self._recent_unique_keepa_history_points(history_points=history_points, normalized=normalized)
        if not filtered_points:
            return 0

        logger.info(
            "keepa_history_bulk_start source=%s external_id=%s candidate_points=%s product_source_record_id=%s",
            source.slug,
            normalized.external_id,
            len(filtered_points),
            product_source_record.id,
        )
        # Bulk-load all existing hashes for this record in a single SELECT —
        # avoids N round-trips to the remote DB (one per candidate point).
        existing_hashes = self._load_existing_price_observation_hashes(
            db, product_source_record_id=product_source_record.id
        )

        asin = (normalized.source_attributes or {}).get("asin")
        inserted = 0
        for point in filtered_points:
            observed_hash = self._build_observed_hash_for_values(
                source_slug=source.slug,
                external_id=normalized.external_id,
                currency=normalized.currency,
                current_price=point.sale_price,
                list_price=None,
                shipping_price=None,
                total_price=point.sale_price,
                availability_status=AvailabilityStatus.UNKNOWN,
                observed_at=point.observed_at,
            )
            if observed_hash in existing_hashes:
                continue

            db.add(
                PriceObservation(
                    product_source_record=product_source_record,
                    observed_at=point.observed_at,
                    currency=normalized.currency,
                    list_price=None,
                    sale_price=point.sale_price,
                    shipping_price=None,
                    total_price=point.sale_price,
                    in_stock=None,
                    is_promotional=False,
                    observed_hash=observed_hash,
                    metadata_json={
                        "source": source.slug,
                        "derived_from": "keepa_history",
                        "asin": asin,
                    },
                )
            )
            inserted += 1

        # Single flush for all new observations — replaces N individual flushes.
        if inserted > 0:
            db.flush()

        return inserted

    def _enrich_with_keepa_history_if_needed_safely(
        self,
        db: Session,
        source: Source,
        product_source_record: ProductSourceRecord,
        product_variant: ProductVariant,
        normalized: NormalizedIngestionRecord,
        keepa_run_state: KeepaFetchRunState | None,
    ) -> int:
        try:
            return self._enrich_with_keepa_history_if_needed(
                db=db,
                source=source,
                product_source_record=product_source_record,
                product_variant=product_variant,
                normalized=normalized,
                keepa_run_state=keepa_run_state,
            )
        except Exception:
            logger.exception(
                "keepa_fetch_enrichment_failed source=%s product_source_record_id=%s product_variant_id=%s external_id=%s",
                source.slug,
                product_source_record.id,
                product_variant.id,
                normalized.external_id,
            )
            return 0

    def _enrich_with_keepa_history_if_needed(
        self,
        db: Session,
        source: Source,
        product_source_record: ProductSourceRecord,
        product_variant: ProductVariant,
        normalized: NormalizedIngestionRecord,
        keepa_run_state: KeepaFetchRunState | None,
    ) -> int:
        if source.slug == "amazon-keepa":
            return 0

        asin = self._clean_identifier((normalized.source_attributes or {}).get("asin"))
        preliminary = should_fetch_keepa_for_record(
            KeepaFetchContext(
                asin=asin,
                product_variant_id=product_variant.id,
                source_slug=source.slug,
                product_url=product_source_record.source_url or str(normalized.product_url),
            )
        )
        if not preliminary.should_fetch and preliminary.reason in {"missing_asin", "not_amazon_relevant"}:
            logger.info(
                "keepa_fetch_enrichment_skipped source=%s external_id=%s asin=%s reason=%s",
                source.slug,
                normalized.external_id,
                asin,
                preliminary.reason,
            )
            return 0

        observation_count_30d, observation_count_90d, observation_count_all_time = self._price_history_counts_for_variant(
            db,
            product_variant.id,
            now=normalized.observed_at,
        )
        decision = should_fetch_keepa_for_record(
            KeepaFetchContext(
                asin=asin,
                product_variant_id=product_variant.id,
                source_slug=source.slug,
                product_url=product_source_record.source_url or str(normalized.product_url),
                observation_count_30d=observation_count_30d,
                observation_count_90d=observation_count_90d,
                observation_count_all_time=observation_count_all_time,
            ),
            run_state=keepa_run_state,
        )
        if not decision.should_fetch:
            logger.info(
                "keepa_fetch_enrichment_skipped source=%s external_id=%s asin=%s reason=%s observation_count_30d=%s observation_count_90d=%s observation_count_all_time=%s next_eligible_at=%s",
                source.slug,
                normalized.external_id,
                asin,
                decision.reason,
                observation_count_30d,
                observation_count_90d,
                observation_count_all_time,
                decision.next_eligible_at.isoformat() if decision.next_eligible_at is not None else None,
            )
            return 0

        logger.info(
            "keepa_fetch_enrichment_due source=%s external_id=%s asin=%s reason=%s observation_count_30d=%s observation_count_90d=%s observation_count_all_time=%s",
            source.slug,
            normalized.external_id,
            asin,
            decision.reason,
            observation_count_30d,
            observation_count_90d,
            observation_count_all_time,
        )
        keepa_payload = self._fetch_keepa_payload_for_asin(asin)
        keepa_product = self._extract_first_keepa_product_payload(keepa_payload)
        if keepa_product is None:
            logger.info(
                "keepa_fetch_enrichment_skipped source=%s external_id=%s asin=%s reason=keepa_product_missing",
                source.slug,
                normalized.external_id,
                asin,
            )
            return 0
        inserted = self._persist_keepa_history_observations_from_payload(
            db=db,
            source=source,
            product_source_record=product_source_record,
            normalized=normalized,
            keepa_product_payload=keepa_product,
        )
        logger.info(
            "keepa_fetch_enrichment_complete source=%s external_id=%s asin=%s inserted=%s product_source_record_id=%s",
            source.slug,
            normalized.external_id,
            asin,
            inserted,
            product_source_record.id,
        )
        return inserted

    def _price_history_counts_for_variant(
        self,
        db: Session,
        product_variant_id,
        *,
        now: datetime,
    ) -> tuple[int, int, int]:
        aggregation = aggregate_price_history_for_variant(db, product_variant_id, now=now)
        return (
            aggregation.observation_count_30d,
            aggregation.observation_count_90d,
            aggregation.observation_count_all_time,
        )

    def _fetch_keepa_payload_for_asin(self, asin: str) -> dict[str, Any]:
        return asyncio.run(fetch_product_by_asin(asin))

    def _extract_first_keepa_product_payload(self, keepa_payload: dict[str, Any]) -> dict[str, Any] | None:
        products = keepa_payload.get("products")
        if not isinstance(products, list):
            return None
        return next((product for product in products if isinstance(product, dict)), None)

    def _recent_unique_keepa_history_points(
        self,
        *,
        history_points,
        normalized: NormalizedIngestionRecord,
    ):
        seen: set[tuple[datetime, str]] = set()
        unique_points = []
        for point in sorted(history_points, key=lambda item: item.observed_at):
            if point.observed_at >= normalized.observed_at:
                continue
            if point.sale_price == normalized.current_price and point.observed_at.date() == normalized.observed_at.date():
                continue
            dedupe_key = (point.observed_at, str(point.sale_price))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            unique_points.append(point)
        return unique_points[-MAX_KEEPA_HISTORY_POINTS:]

    def _find_existing_price_observation_by_hash(
        self,
        db: Session,
        *,
        product_source_record_id,
        observed_hash: str,
    ) -> PriceObservation | None:
        return db.scalar(
            select(PriceObservation).where(
                PriceObservation.product_source_record_id == product_source_record_id,
                PriceObservation.observed_hash == observed_hash,
            )
        )

    def _load_existing_price_observation_hashes(
        self,
        db: Session,
        *,
        product_source_record_id,
    ) -> set[str]:
        """Return all observed_hash values for a product_source_record in one query.

        Used to replace per-point existence checks with a single bulk SELECT,
        eliminating the N+1 flush pattern in keepa history ingestion.
        """
        return set(
            db.scalars(
                select(PriceObservation.observed_hash).where(
                    PriceObservation.product_source_record_id == product_source_record_id,
                )
            ).all()
        )

    def _clean_identifier(self, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    def _merged_metadata(self, existing: dict | None, updates: dict) -> dict:
        merged = dict(existing or {})
        merged.update(updates)
        return merged

    def _sync_review_candidate(
        self,
        db: Session,
        source: Source,
        product_source_record: ProductSourceRecord,
        price_observation: PriceObservation,
    ) -> None:
        try:
            with db.begin_nested():
                self.deal_generation_service.sync_deal_for_source_record(
                    db=db,
                    source=source,
                    product_source_record=product_source_record,
                    price_observation=price_observation,
                )
        except Exception:
            logger.exception(
                "deal_generation_failed source=%s product_source_record_id=%s price_observation_id=%s",
                source.slug,
                product_source_record.id,
                price_observation.id,
            )
