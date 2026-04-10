from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.enums import SourceType
from app.db.models import Source
from app.db.session import SessionLocal
from app.integrations.keepa_client import (
    KeepaClientError,
    KeepaConfigurationError,
    fetch_products_by_asins,
)
from app.integrations.keepa_payloads import normalize_keepa_payload_for_ingest
from app.ingestion.parsers.keepa import KeepaParser

SOURCE_SLUG = "amazon-keepa"
SOURCE_NAME = "Amazon Keepa"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch products from Keepa and ingest them with the existing Keepa parser.")
    parser.add_argument("asins", nargs="*", help="ASINs to fetch from Keepa.")
    parser.add_argument("--asin-file", help="Path to a JSON array or newline-delimited file with ASINs.")
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the existing backend API.",
    )
    parser.add_argument(
        "--domain-id",
        type=int,
        default=settings.keepa_domain_id,
        help="Keepa/Amazon domain id (default: %(default)s).",
    )
    return parser.parse_args()


def load_asins(args: argparse.Namespace) -> list[str]:
    asins = [asin.strip().upper() for asin in args.asins if asin.strip()]
    if args.asin_file:
        file_asins = _load_asins_file(Path(args.asin_file))
        asins.extend(file_asins)

    deduped: list[str] = []
    for asin in asins:
        if asin and asin not in deduped:
            deduped.append(asin)

    if not deduped:
        raise SystemExit("Provide at least one ASIN or --asin-file.")
    return deduped


def _load_asins_file(path: Path) -> list[str]:
    raw = path.read_text().strip()
    if not raw:
        raise SystemExit("ASIN file is empty.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = [line.strip() for line in raw.splitlines() if line.strip()]

    if not isinstance(payload, list):
        raise SystemExit("ASIN file must contain a JSON array or newline-delimited ASINs.")

    return [str(item).strip().upper() for item in payload if str(item).strip()]


def ensure_source(domain_id: int) -> None:
    tld = KeepaParser.DOMAIN_MAP.get(domain_id, "com")
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.slug == SOURCE_SLUG))
        config = {"parser": "keepa", "domain_id": domain_id, "region": tld.upper()}
        if source is None:
            source = Source(
                name=SOURCE_NAME,
                slug=SOURCE_SLUG,
                source_type=SourceType.AFFILIATE_FEED,
                base_url=f"https://www.amazon.{tld}",
                is_active=True,
                config=config,
            )
            db.add(source)
        else:
            source.name = SOURCE_NAME
            source.source_type = SourceType.AFFILIATE_FEED
            source.base_url = f"https://www.amazon.{tld}"
            source.is_active = True
            source.config = config
        db.commit()


def fetch_keepa_payload(asins: list[str], domain_id: int) -> dict[str, Any]:
    try:
        return asyncio.run(
            fetch_products_by_asins(
                asins,
                domain_id=domain_id,
                timeout=60.0,
            )
        )
    except KeepaConfigurationError as exc:
        raise SystemExit(str(exc)) from exc
    except KeepaClientError as exc:
        raise SystemExit(str(exc)) from exc


def ingest_keepa_payload(payload: dict[str, Any], api_base_url: str) -> dict[str, Any]:
    request_payload = {
        "source_slug": SOURCE_SLUG,
        "parser": "keepa",
        "payload": payload,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{api_base_url.rstrip('/')}{settings.api_v1_prefix}/ingest/run", json=request_payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise SystemExit(f"Ingest API request failed with status {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise SystemExit(f"Ingest API request failed: {exc}") from exc
    except ValueError as exc:
        raise SystemExit("Ingest API returned malformed JSON.") from exc


def main() -> int:
    args = parse_args()
    asins = load_asins(args)
    ensure_source(args.domain_id)
    payload = normalize_keepa_payload_for_ingest(
        fetch_keepa_payload(asins, args.domain_id),
        domain_id=args.domain_id,
    )
    ingest_result = ingest_keepa_payload(payload, args.api_base_url)

    print(
        json.dumps(
            {
                "source_slug": SOURCE_SLUG,
                "asin_count": len(asins),
                "fetched_products": len(payload.get("products", [])),
                "ingest_result": ingest_result,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
