from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
from typing import Any

from app.db.enums import AvailabilityStatus
from app.ingestion.amazon_identifiers import normalize_asin
from app.ingestion.interfaces import SourceParser
from app.ingestion.schemas import ParsedSourceRecord


class AffiliateFeedCSVParser(SourceParser):
    parser_name = "affiliate_csv"

    def parse(self, payload: Any) -> list[ParsedSourceRecord]:
        csv_text = self._to_text(payload)
        reader = csv.DictReader(StringIO(csv_text))
        return [self._parse_row(row) for row in reader]

    def _parse_row(self, row: dict[str, str | None]) -> ParsedSourceRecord:
        external_id = (row.get("id") or row.get("sku") or row.get("product_id") or row.get("url") or "").strip()
        return ParsedSourceRecord(
            external_id=external_id,
            product_url=(row.get("url") or row.get("product_url") or "").strip() or None,
            title=(row.get("title") or row.get("name") or "").strip() or None,
            brand=(row.get("brand") or "").strip() or None,
            category=(row.get("category") or "").strip() or None,
            description=(row.get("description") or "").strip() or None,
            image_url=(row.get("image_url") or row.get("image") or "").strip() or None,
            merchant_name=(row.get("merchant") or row.get("merchant_name") or "").strip() or None,
            currency=(row.get("currency") or "USD").strip().upper(),
            current_price=self._to_decimal(row.get("price") or row.get("current_price")),
            list_price=self._to_decimal(row.get("list_price") or row.get("original_price")),
            shipping_price=self._to_decimal(row.get("shipping_price")),
            availability_status=self._availability_from_text(row.get("availability")),
            pack_count=self._to_int(row.get("pack_count")),
            quantity=self._to_decimal(row.get("quantity")),
            quantity_unit=(row.get("quantity_unit") or "").strip() or None,
            weight=self._to_decimal(row.get("weight")),
            weight_unit=(row.get("weight_unit") or "").strip() or None,
            volume=self._to_decimal(row.get("volume")),
            volume_unit=(row.get("volume_unit") or "").strip() or None,
            size=(row.get("size") or "").strip() or None,
            color=(row.get("color") or "").strip() or None,
            material=(row.get("material") or "").strip() or None,
            is_bundle=self._to_bool(row.get("is_bundle")),
            source_attributes={
                "asin": normalize_asin(row.get("asin")),
                "gtin": row.get("gtin"),
                "sku": row.get("sku"),
                "mpn": row.get("mpn"),
                "source_link_type": (row.get("source_link_type") or "").strip() or None,
                "is_google_redirect": self._to_optional_bool(row.get("is_google_redirect")),
                "merchant_confidence": (row.get("merchant_confidence") or "").strip() or None,
                "merchant_label_source": (row.get("merchant_label_source") or "").strip() or None,
            },
            raw_payload={key: value for key, value in row.items()},
        )

    def _to_text(self, payload: Any) -> str:
        if isinstance(payload, bytes):
            return payload.decode("utf-8")
        if isinstance(payload, str):
            return payload
        raise ValueError("Affiliate CSV payload must be str or bytes")

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _to_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(str(value))
        except Exception:
            return None

    def _to_bool(self, value: Any) -> bool:
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "y"}

    def _to_optional_bool(self, value: Any) -> bool | None:
        if value in (None, ""):
            return None
        return self._to_bool(value)

    def _availability_from_text(self, value: Any) -> AvailabilityStatus:
        normalized = str(value or "").strip().lower()
        if normalized in {"in stock", "instock", "available", "true", "1"}:
            return AvailabilityStatus.IN_STOCK
        if normalized in {"out of stock", "outofstock", "unavailable", "false", "0"}:
            return AvailabilityStatus.OUT_OF_STOCK
        if normalized == "preorder":
            return AvailabilityStatus.PREORDER
        return AvailabilityStatus.UNKNOWN
