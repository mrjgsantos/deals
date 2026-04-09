from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.enums import SourceType
from app.db.models import Source
from app.db.session import SessionLocal

SOURCE_SLUG = "serpapi-google-shopping"
SOURCE_NAME = "SerpApi Google Shopping"
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

SYMBOL_TO_CURRENCY = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "R$": "BRL",
    "C$": "CAD",
    "A$": "AUD",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Google Shopping results from SerpApi and ingest them.")
    parser.add_argument("query", help="Shopping query to fetch from SerpApi.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum number of shopping results to ingest.")
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the existing backend API.",
    )
    return parser.parse_args()


def env(name: str, *, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value or ""


def ensure_source() -> None:
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.slug == SOURCE_SLUG))
        if source is None:
            source = Source(
                name=SOURCE_NAME,
                slug=SOURCE_SLUG,
                source_type=SourceType.AFFILIATE_FEED,
                base_url="https://serpapi.com",
                is_active=True,
                config={"parser": "affiliate_csv", "engine": env("SERPAPI_ENGINE", default="google_shopping")},
            )
            db.add(source)
        else:
            source.name = SOURCE_NAME
            source.source_type = SourceType.AFFILIATE_FEED
            source.base_url = "https://serpapi.com"
            source.is_active = True
            source.config = {"parser": "affiliate_csv", "engine": env("SERPAPI_ENGINE", default="google_shopping")}
        db.commit()


def fetch_results(query: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "engine": env("SERPAPI_ENGINE", default="google_shopping"),
        "api_key": env("SERPAPI_API_KEY", required=True),
        "q": query,
        "gl": env("SERPAPI_COUNTRY", default="us"),
        "hl": env("SERPAPI_LANGUAGE", default="en"),
        "location": env("SERPAPI_LOCATION", required=True),
        "num": max(1, min(limit, 10)),
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.get(SERPAPI_ENDPOINT, params=params)
        response.raise_for_status()
        payload = response.json()

    results = payload.get("shopping_results")
    if not isinstance(results, list):
        raise SystemExit("SerpApi response did not contain shopping_results.")
    return [item for item in results if isinstance(item, dict)]


def infer_currency(result: dict[str, Any]) -> str | None:
    for key in ("currency", "price_currency"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()

    raw_price = str(result.get("price") or "").strip()
    for symbol, currency in sorted(SYMBOL_TO_CURRENCY.items(), key=lambda item: len(item[0]), reverse=True):
        if symbol in raw_price:
            return currency

    match = re.search(r"\b([A-Z]{3})\b", raw_price)
    if match:
        return match.group(1)
    return None


def extract_price(result: dict[str, Any]) -> str | None:
    extracted = result.get("extracted_price")
    if isinstance(extracted, (int, float)):
        return f"{extracted:.2f}"
    if isinstance(extracted, str):
        try:
            return f"{float(extracted):.2f}"
        except ValueError:
            pass

    raw_price = str(result.get("price") or "").strip()
    match = re.search(r"(\d[\d,]*\.?\d*)", raw_price)
    if not match:
        return None
    return match.group(1).replace(",", "")


def build_external_id(result: dict[str, Any], product_url: str, title: str) -> str:
    for key in ("product_id", "offer_id", "shopping_result_id"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:255]

    base = product_url or title
    if len(base) <= 255:
        return base
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def to_affiliate_csv(results: list[dict[str, Any]], limit: int) -> tuple[str, int]:
    output = StringIO()
    fieldnames = ["id", "url", "title", "merchant", "price", "currency", "image_url"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    accepted = 0
    for result in results:
        if accepted >= limit:
            break

        title = str(result.get("title") or "").strip()
        product_url = str(result.get("product_link") or result.get("link") or "").strip()
        price = extract_price(result)
        currency = infer_currency(result)

        if not title or not product_url or not price or not currency:
            continue

        writer.writerow(
            {
                "id": build_external_id(result, product_url, title),
                "url": product_url,
                "title": title,
                "merchant": str(result.get("source") or result.get("merchant_name") or "").strip() or None,
                "price": price,
                "currency": currency,
                "image_url": str(result.get("thumbnail") or result.get("image") or "").strip() or None,
            }
        )
        accepted += 1

    if accepted == 0:
        raise SystemExit("No SerpApi shopping results had the minimum fields required for ingestion.")

    return output.getvalue(), accepted


def ingest_csv(csv_payload: str, api_base_url: str) -> dict[str, Any]:
    request_payload = {
        "source_slug": SOURCE_SLUG,
        "parser": "affiliate_csv",
        "payload": csv_payload,
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(f"{api_base_url.rstrip('/')}{settings.api_v1_prefix}/ingest/run", json=request_payload)
        response.raise_for_status()
        return response.json()


def main() -> int:
    args = parse_args()
    ensure_source()
    results = fetch_results(args.query, args.limit)
    csv_payload, mapped_count = to_affiliate_csv(results, args.limit)
    ingest_result = ingest_csv(csv_payload, args.api_base_url)

    print(
        json.dumps(
            {
                "query": args.query,
                "fetched_results": len(results),
                "mapped_results": mapped_count,
                "ingest_result": ingest_result,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
