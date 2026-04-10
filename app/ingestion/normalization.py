from __future__ import annotations

import re
from decimal import Decimal

from app.ingestion.amazon_identifiers import extract_amazon_asin_from_url, normalize_asin
from app.ingestion.exceptions import RecordRejectedError
from app.ingestion.interfaces import RecordNormalizer
from app.ingestion.schemas import NormalizedIngestionRecord, ParsedSourceRecord
from app.ingestion.variant_parser import parse_variant_attributes
from app.matching.feature_extraction import extract_title_normalization_features


class DefaultRecordNormalizer(RecordNormalizer):
    def normalize(self, record: ParsedSourceRecord) -> NormalizedIngestionRecord:
        product_url = self._clean_string(record.product_url)
        if not product_url:
            raise RecordRejectedError("missing product URL")

        current_price = record.current_price
        if current_price is None or current_price <= 0:
            raise RecordRejectedError("missing current price")

        source_title = self._clean_string(record.title)
        if not source_title:
            raise RecordRejectedError("missing title")

        parsed_variant = parse_variant_attributes(source_title)
        extracted_features = extract_title_normalization_features(
            source_title,
            brand=record.brand,
        )
        pack_count = record.pack_count if record.pack_count is not None else parsed_variant.attributes.pack_count
        if pack_count is None:
            pack_count = extracted_features.normalized_pack_count
        quantity = record.quantity if record.quantity is not None else parsed_variant.attributes.quantity
        quantity_unit = self._clean_string(record.quantity_unit) or parsed_variant.attributes.quantity_unit
        weight = record.weight if record.weight is not None else parsed_variant.attributes.weight
        weight_unit = self._clean_string(record.weight_unit) or parsed_variant.attributes.weight_unit
        volume = record.volume if record.volume is not None else parsed_variant.attributes.volume
        volume_unit = self._clean_string(record.volume_unit) or parsed_variant.attributes.volume_unit
        size = self._clean_string(record.size) or parsed_variant.attributes.size
        color = self._clean_string(record.color) or parsed_variant.attributes.color
        if color is None:
            color = extracted_features.normalized_color
        material = self._clean_string(record.material) or parsed_variant.attributes.material
        is_bundle = record.is_bundle or parsed_variant.attributes.is_bundle

        normalized_name = self._collapse_whitespace(source_title)
        currency = (record.currency or "USD").strip().upper()
        list_price = record.list_price if record.list_price and record.list_price > 0 else None
        shipping_price = record.shipping_price if record.shipping_price and record.shipping_price >= 0 else None
        total_price = current_price + (shipping_price or Decimal("0"))
        merchant_name = self._clean_string(record.merchant_name)
        source_attributes = {
            **record.source_attributes,
            "asin": self._resolved_asin(record),
            "variant_parse": parsed_variant.as_dict(),
            "title_normalization": extracted_features.as_dict(),
        }

        return NormalizedIngestionRecord(
            normalized_name=normalized_name,
            variant_key=self._build_variant_key(record),
            product_url=product_url,
            external_id=record.external_id,
            brand=self._clean_string(record.brand),
            category=self._clean_string(record.category),
            description=self._clean_string(record.description),
            image_url=self._clean_string(record.image_url),
            merchant_name=merchant_name,
            merchant_slug=self._slugify(merchant_name) if merchant_name else None,
            currency=currency,
            current_price=current_price,
            list_price=list_price,
            shipping_price=shipping_price,
            total_price=total_price,
            availability_status=record.availability_status,
            source_title=source_title,
            source_brand=self._clean_string(record.brand),
            source_description=self._clean_string(record.description),
            source_category=self._clean_string(record.category),
            source_attributes=source_attributes,
            raw_payload=record.raw_payload,
            observed_at=record.observed_at,
            pack_count=pack_count,
            quantity=quantity,
            quantity_unit=quantity_unit,
            weight=weight,
            weight_unit=weight_unit,
            volume=volume,
            volume_unit=volume_unit,
            size=size,
            color=color,
            material=material,
            is_bundle=is_bundle,
        )

    def _build_variant_key(self, record: ParsedSourceRecord) -> str:
        parsed_variant = parse_variant_attributes(record.title or "")
        return parsed_variant.variant_key()

    def _clean_string(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = self._collapse_whitespace(value)
        return cleaned or None

    def _collapse_whitespace(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "unknown"

    def _resolved_asin(self, record: ParsedSourceRecord) -> str | None:
        existing_asin = normalize_asin((record.source_attributes or {}).get("asin"))
        if existing_asin:
            return existing_asin
        return extract_amazon_asin_from_url(self._clean_string(record.product_url))
