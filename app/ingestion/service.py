from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AvailabilityStatus
from app.db.models import (
    Merchant,
    PriceObservation,
    Product,
    ProductSourceRecord,
    ProductVariant,
    RawIngestionRecord,
    Source,
)
from app.ingestion.exceptions import PayloadValidationError, RecordRejectedError, SourceNotFoundError
from app.ingestion.interfaces import RecordNormalizer, SourceParser
from app.ingestion.schemas import IngestionBatchResult, IngestionRecordResult, NormalizedIngestionRecord
from app.matching.service import MatchingService
from app.matching.types import Matcher
from app.services.deal_generation_service import DealGenerationService

logger = logging.getLogger(__name__)


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

        for parsed_record in parsed_records:
            result.processed += 1
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
                    write_result = self._persist_normalized_record(
                        db=db,
                        source=source,
                        raw_record=raw_record,
                        normalized=normalized,
                    )
                result.accepted += 1
                result.records.append(write_result)
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
            except Exception as exc:
                raw_record.status = "failed"
                raw_record.rejection_reason = "internal_error"
                raw_record.processed_at = datetime.now(timezone.utc)
                db.flush()
                logger.exception(
                    "ingestion_record_failed source=%s parser=%s external_id=%s error=%s",
                    source.slug,
                    self.parser.parser_name,
                    parsed_record.external_id,
                    exc,
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
        return result

    def _persist_normalized_record(
        self,
        db: Session,
        source: Source,
        raw_record: RawIngestionRecord,
        normalized: NormalizedIngestionRecord,
    ) -> IngestionRecordResult:
        match_decision = self.matcher.match_normalized_record(db, normalized)
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
        product_source_record.source_url = str(normalized.product_url)
        product_source_record.image_url = normalized.image_url
        product_source_record.source_title = normalized.source_title
        product_source_record.source_brand = normalized.source_brand
        product_source_record.source_description = normalized.source_description
        product_source_record.source_category = normalized.source_category
        product_source_record.currency = normalized.currency
        product_source_record.availability_status = normalized.availability_status
        product_source_record.source_attributes = normalized.source_attributes
        product_source_record.raw_payload = {
            "product_url": str(normalized.product_url),
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

        raw_record.status = "duplicate" if duplicate_observation else "accepted"
        raw_record.product_source_record = product_source_record
        raw_record.normalized_payload = normalized.model_dump(mode="json")
        raw_record.processed_at = datetime.now(timezone.utc)
        self._sync_review_candidate(
            db=db,
            source=source,
            product_source_record=product_source_record,
            price_observation=price_observation,
        )

        return IngestionRecordResult(
            raw_ingestion_record_id=str(raw_record.id),
            product_source_record_id=str(product_source_record.id),
            price_observation_id=str(price_observation.id),
            status="duplicate" if duplicate_observation else "accepted",
        )

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
        payload = {
            "source_slug": source_slug,
            "external_id": normalized.external_id,
            "currency": normalized.currency,
            "current_price": str(normalized.current_price),
            "list_price": str(normalized.list_price) if normalized.list_price is not None else None,
            "shipping_price": str(normalized.shipping_price) if normalized.shipping_price is not None else None,
            "total_price": str(normalized.total_price),
            "availability_status": normalized.availability_status.value,
            "observed_at": normalized.observed_at.isoformat(),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

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
