from __future__ import annotations

import argparse
import asyncio
from collections import Counter
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
from app.integrations.keepa_curation import (
    CuratedAsinInputs,
    curate_asin_candidates,
    extract_asin_candidates_from_text,
    preflight_keepa_batch_for_bulk_ingest,
)
from app.ingestion.parsers.keepa import KeepaParser

SOURCE_SLUG = "amazon-keepa"
SOURCE_NAME = "Amazon Keepa"
API_BASE_URL = "http://app:8000"
DOMAIN_ID = 9
MAX_BATCH_SIZE = 50
DEFAULT_ASINS = [
    "B09B8V1LZ3",
    "B09B94956P",
    "B0BLS3K8DT",
    "B08N2QK2TG",
    "B0B6GJ9V63",
]


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Keepa products in batches and ingest only parser-compatible products."
    )
    parser.add_argument(
        "asins",
        nargs="*",
        help="Optional ASINs or Amazon product URLs. Comma-separated values are also accepted.",
    )
    parser.add_argument(
        "--asin-file",
        help="Optional JSON array or raw text file with ASINs / Amazon product URLs.",
    )
    parser.add_argument(
        "--api-base-url",
        default=API_BASE_URL,
        help="Base URL for the existing backend API.",
    )
    parser.add_argument(
        "--domain-id",
        type=int,
        default=DOMAIN_ID,
        help="Keepa/Amazon domain id (default: %(default)s).",
    )
    return parser.parse_args()


def load_asins(args: argparse.Namespace) -> list[str]:
    return curate_asin_inputs(args).accepted_asins


def curate_asin_inputs(args: argparse.Namespace) -> CuratedAsinInputs:
    cli_values = list(args.asins or [])
    file_values = _load_asins_file(Path(args.asin_file)) if args.asin_file else []

    if cli_values:
        return curate_asin_candidates(cli_values, source="cli")
    if file_values:
        return curate_asin_candidates(file_values, source="file")
    return curate_asin_candidates(DEFAULT_ASINS, source="defaults")


def _load_asins_file(path: Path) -> list[str]:
    raw = path.read_text().strip()
    if not raw:
        raise SystemExit("ASIN file is empty.")
    try:
        return extract_asin_candidates_from_text(raw)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def ensure_source(domain_id: int) -> None:
    tld = KeepaParser.DOMAIN_MAP.get(domain_id, "com")
    config = {"parser": "keepa", "domain_id": domain_id, "region": tld.upper()}

    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.slug == SOURCE_SLUG))
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


async def fetch_batch(asins: list[str], *, domain_id: int) -> dict[str, Any]:
    return await fetch_products_by_asins(
        asins,
        domain_id=domain_id,
        timeout=60.0,
    )


def ingest_keepa_payload(payload: dict[str, Any], api_base_url: str) -> dict[str, Any]:
    request_payload = {
        "source_slug": SOURCE_SLUG,
        "parser": "keepa",
        "payload": payload,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{api_base_url.rstrip('/')}{settings.api_v1_prefix}/ingest/run",
                json=request_payload,
            )
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
    curated_inputs = curate_asin_inputs(args)
    asins = curated_inputs.accepted_asins
    if not asins:
        raise SystemExit("No valid ASINs remain after input curation.")
    ensure_source(args.domain_id)

    asin_batches = chunked(asins, MAX_BATCH_SIZE)
    total_fetched = 0
    total_posted = 0
    total_skipped = 0
    total_accepted = 0
    total_rejected = 0
    outcome_counts: Counter[str] = Counter()
    batch_results: list[dict[str, Any]] = []

    print(
        json.dumps(
            {
                "event": "asin_input_curation",
                "selected_source": curated_inputs.selected_source,
                "raw_candidate_count": len(curated_inputs.raw_candidates),
                "accepted_asin_count": len(curated_inputs.accepted_asins),
                "accepted_asins": curated_inputs.accepted_asins,
                "issue_counts_by_outcome": curated_inputs.counts_by_outcome,
                "issue_counts_by_reason": curated_inputs.counts_by_reason,
                "issues": [issue.as_dict() for issue in curated_inputs.issues],
            }
        )
    )

    for batch_number, asin_batch in enumerate(asin_batches, start=1):
        try:
            raw_payload = asyncio.run(fetch_batch(asin_batch, domain_id=args.domain_id))
            preflight = preflight_keepa_batch_for_bulk_ingest(
                raw_payload,
                requested_asins=asin_batch,
                domain_id=args.domain_id,
            )
        except KeepaConfigurationError as exc:
            raise SystemExit(str(exc)) from exc
        except KeepaClientError as exc:
            print(
                json.dumps(
                    {
                        "batch": batch_number,
                        "domain_id": args.domain_id,
                        "requested_asins": asin_batch,
                        "error": str(exc),
                    }
                )
            )
            continue

        fetched_products = preflight.fetched_products
        payload = preflight.payload
        posted_products = len(payload.get("products", []))
        skipped_count = len(preflight.skipped_outcomes)
        total_fetched += fetched_products
        total_posted += posted_products
        total_skipped += skipped_count
        outcome_counts.update(preflight.counts_by_outcome)

        if preflight.outcomes:
            print(
                json.dumps(
                    {
                        "batch": batch_number,
                        "domain_id": args.domain_id,
                        "event": "keepa_batch_preflight",
                        "requested_asins": asin_batch,
                        "outcome_counts": preflight.counts_by_outcome,
                        "outcomes": [outcome.as_dict() for outcome in preflight.outcomes],
                    }
                )
            )

        if posted_products == 0:
            batch_summary = {
                "batch": batch_number,
                "domain_id": args.domain_id,
                "requested_asins": asin_batch,
                "fetched_products": fetched_products,
                "posted_products": 0,
                "skipped_products": skipped_count,
                "outcome_counts": preflight.counts_by_outcome,
                "accepted": 0,
                "rejected": 0,
            }
            batch_results.append(batch_summary)
            print(json.dumps(batch_summary))
            continue

        ingest_result = ingest_keepa_payload(payload, args.api_base_url)

        accepted = int(ingest_result.get("accepted", 0))
        rejected = int(ingest_result.get("rejected", 0))

        total_accepted += accepted
        total_rejected += rejected

        batch_summary = {
            "batch": batch_number,
            "domain_id": args.domain_id,
            "requested_asins": asin_batch,
            "fetched_products": fetched_products,
            "posted_products": posted_products,
            "skipped_products": skipped_count,
            "outcome_counts": preflight.counts_by_outcome,
            "accepted": accepted,
            "rejected": rejected,
        }
        batch_results.append(batch_summary)
        print(json.dumps(batch_summary))

    print(
        json.dumps(
            {
                "source_slug": SOURCE_SLUG,
                "domain_id": args.domain_id,
                "asin_count": len(asins),
                "batch_count": len(asin_batches),
                "input_curation": {
                    "selected_source": curated_inputs.selected_source,
                    "raw_candidate_count": len(curated_inputs.raw_candidates),
                    "accepted_asin_count": len(curated_inputs.accepted_asins),
                    "issue_counts_by_outcome": curated_inputs.counts_by_outcome,
                    "issue_counts_by_reason": curated_inputs.counts_by_reason,
                },
                "keepa_outcome_counts": dict(sorted(outcome_counts.items())),
                "total_fetched_products": total_fetched,
                "total_posted_products": total_posted,
                "total_skipped_products": total_skipped,
                "total_accepted": total_accepted,
                "total_rejected": total_rejected,
                "batches": batch_results,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
