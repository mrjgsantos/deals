from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.db.enums import AvailabilityStatus
from app.ingestion.interfaces import SourceParser
from app.ingestion.schemas import ParsedSourceRecord
from app.integrations.keepa_history import KEEPA_CSV_HISTORY_INDEX, keepa_minutes_to_datetime
from app.integrations.keepa_payloads import DOMAIN_CURRENCY_MAP


class KeepaParser(SourceParser):
    parser_name = "keepa"

    DOMAIN_MAP = {
        1: "com",
        2: "co.uk",
        3: "de",
        4: "fr",
        5: "co.jp",
        6: "ca",
        8: "it",
        9: "es",
        10: "in",
    }

    PRICE_HISTORY_FALLBACKS = {
        "buyBoxPrice": ("NEW", "AMAZON"),
        "newPrice": ("NEW", "AMAZON"),
        "lastPrice": ("NEW", "AMAZON"),
        "listPrice": ("LISTPRICE",),
    }

    def parse(self, payload: Any) -> list[ParsedSourceRecord]:
        products = self._extract_products(payload)
        return [self._parse_product(product, payload) for product in products]

    def _extract_products(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and isinstance(payload.get("products"), list):
            return [product for product in payload["products"] if isinstance(product, dict)]
        if isinstance(payload, list):
            return [product for product in payload if isinstance(product, dict)]
        if isinstance(payload, dict):
            return [payload]
        raise ValueError("Unsupported Keepa payload shape")

    def _parse_product(self, product: dict[str, Any], root_payload: Any) -> ParsedSourceRecord:
        asin = str(product.get("asin") or "").strip()
        domain_id = product.get("domainId")
        product_url = self._build_product_url(asin=asin, domain_id=domain_id, explicit_url=product.get("productURL"))
        current_price = self._pick_price(product, ("buyBoxPrice", "newPrice", "lastPrice"))
        list_price = self._pick_price(product, ("listPrice", "newPrice"))
        shipping_price = self._to_decimal(product.get("shipping"))
        image = self._extract_image_url(product, domain_id)
        category = self._extract_category(product)
        merchant_name = product.get("manufacturer") or product.get("brand")
        upc_list = product.get("upcList") or []
        primary_gtin = str(upc_list[0]).strip() if upc_list else None

        return ParsedSourceRecord(
            external_id=asin or product_url or "unknown",
            product_url=product_url,
            title=product.get("title"),
            brand=product.get("brand"),
            category=category,
            description=product.get("featuresCSV") or product.get("description"),
            image_url=image,
            merchant_name=merchant_name,
            currency=self._extract_currency(product),
            current_price=current_price,
            list_price=list_price,
            shipping_price=shipping_price,
            availability_status=self._availability_from_product(product),
            observed_at=self._extract_observed_at(product),
            source_attributes={
                "asin": asin,
                "gtin": primary_gtin or None,
                "domain_id": domain_id,
                "manufacturer": product.get("manufacturer"),
                "mpn": product.get("model"),
                "model": product.get("model"),
                "upc_list": upc_list,
            },
            raw_payload=product if isinstance(root_payload, dict) else {"product": product},
        )

    def _build_product_url(self, asin: str, domain_id: Any, explicit_url: Any) -> str | None:
        if explicit_url:
            return str(explicit_url)
        if not asin:
            return None
        tld = self.DOMAIN_MAP.get(domain_id, "com")
        return f"https://www.amazon.{tld}/dp/{asin}"

    def _pick_price(self, product: dict[str, Any], keys: tuple[str, ...]) -> Decimal | None:
        for key in keys:
            value = self._to_decimal(product.get(key))
            if value is not None:
                return value
        for key in keys:
            fallback_value = self._history_price(product, self.PRICE_HISTORY_FALLBACKS.get(key, ()))
            if fallback_value is not None:
                return fallback_value
        return None

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            numeric = Decimal(str(value))
        except Exception:
            return None
        if numeric <= 0:
            return None
        return numeric / Decimal("100")

    def _extract_category(self, product: dict[str, Any]) -> str | None:
        category_tree = product.get("categoryTree")
        if isinstance(category_tree, list) and category_tree:
            leaf = category_tree[-1]
            if isinstance(leaf, dict):
                return leaf.get("name")
        return None

    def _extract_image_url(self, product: dict[str, Any], domain_id: Any) -> str | None:
        # Primary: imagesCSV (comma-separated image filenames)
        images_csv = product.get("imagesCSV")
        if images_csv:
            first_image = str(images_csv).split(",")[0].strip()
            if first_image:
                return f"https://images-na.ssl-images-amazon.com/images/I/{first_image}"

        # Fallback: images array [{l: "filename.jpg", ...}, ...]
        images = product.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                filename = first.get("l") or first.get("m")
                if filename:
                    return f"https://images-na.ssl-images-amazon.com/images/I/{filename}"

        return None

    def _availability_from_product(self, product: dict[str, Any]) -> AvailabilityStatus:
        if product.get("availabilityAmazon", 0) in (0, None):
            return AvailabilityStatus.UNKNOWN
        if int(product.get("availabilityAmazon", 0)) < 0:
            return AvailabilityStatus.OUT_OF_STOCK
        return AvailabilityStatus.IN_STOCK

    def _extract_currency(self, product: dict[str, Any]) -> str | None:
        currency = str(product.get("currency") or "").strip()
        if currency:
            return currency.upper()
        try:
            domain_id = int(product.get("domainId"))
        except (TypeError, ValueError):
            return "USD"
        return DOMAIN_CURRENCY_MAP.get(domain_id, "USD")

    def _history_price(self, product: dict[str, Any], history_keys: tuple[str, ...]) -> Decimal | None:
        for history_key in history_keys:
            fallback_value = self._extract_latest_history_price(product, history_key)
            if fallback_value is not None:
                return fallback_value
        return None

    def _extract_latest_history_price(self, product: dict[str, Any], history_key: str) -> Decimal | None:
        data = product.get("data")
        if isinstance(data, dict):
            prices = data.get(history_key)
            if isinstance(prices, list):
                for raw_price in reversed(prices):
                    price = self._to_decimal(raw_price)
                    if price is not None:
                        return price

        csv_history = product.get("csv")
        if not isinstance(csv_history, list):
            return None

        csv_index = KEEPA_CSV_HISTORY_INDEX.get(history_key)
        if csv_index is None or csv_index >= len(csv_history):
            return None

        raw_series = csv_history[csv_index]
        if not isinstance(raw_series, list):
            return None

        for offset in range(len(raw_series) - 1, 0, -2):
            price = self._to_decimal(raw_series[offset])
            if price is not None:
                return price
        return None

    def _extract_observed_at(self, product: dict[str, Any]):
        from datetime import datetime, timezone

        last_update = product.get("lastUpdate")
        if last_update is None:
            return datetime.now(timezone.utc)
        try:
            converted = keepa_minutes_to_datetime(last_update)
            if converted is not None:
                return converted
            return datetime.now(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)
