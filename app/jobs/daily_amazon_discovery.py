"""
Daily Amazon.es ASIN discovery job.

Designed to run once per day (not in the hourly SerpApi loop) via
.github/workflows/amazon-discovery.yml.

Flow
----
1. Load Amazon.es category URLs from data/amazon_es_discovery_urls.txt.
2. Fetch each page with plain HTTP (no JS / headless browser needed for
   category / bestseller pages).
3. Extract ASIN candidates, merge across pages, filter by price and signal
   quality.
4. Skip ingest entirely when the extraction quality is too low (blocked
   page, rate-limited response, etc.) — returns exit-code 0 so the
   calling workflow does not show a red flag for network noise.
5. Fetch Keepa price history for accepted ASINs in batches.
6. Ingest directly into the DB via IngestionService + KeepaParser — same
   path used by the background Keepa scheduler and daily_ingestion.py.

Newly created ProductSourceRecords are then scored and (if eligible)
auto-published by the next run of the hourly pipeline. The background
Keepa scheduler continues enriching them over the following days.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from sqlalchemy import select, text

from app.core.config import settings
from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.parsers.keepa import KeepaParser
from app.ingestion.service import IngestionService
from app.integrations.amazon_es_discovery import (
    AmazonEsCandidate,
    AmazonEsCandidatePoolPage,
    assess_discovery_quality,
    discover_candidate_pool_from_html,
    discover_pagination_urls_from_html,
    fetch_amazon_es_page,
    filter_candidate_pool,
)
from app.db.models import ProductSourceRecord, Source
from app.integrations.keepa_client import (
    KeepaClientError,
    KeepaConfigurationError,
    fetch_products_by_asins,
)
from app.integrations.keepa_curation import preflight_keepa_batch_for_bulk_ingest
from app.jobs.common import job_session, run_job
from app.matching.service import MatchingService
from scripts.ingest_keepa_bulk import SOURCE_SLUG, chunked, ensure_source

DISCOVERY_KEEPA_BATCH_SIZE = 20
KEEPA_FETCH_TIMEOUT = 60.0
KEEPA_FETCH_HARD_TIMEOUT = 120.0
INGEST_STATEMENT_TIMEOUT_MS = 30_000


def main() -> int:
    def _runner(logger: logging.Logger) -> int:
        urls_file = Path(settings.amazon_discovery_urls_file)
        if not urls_file.exists():
            logger.info(
                "amazon_discovery_skipped reason=urls_file_not_found path=%s",
                urls_file,
            )
            return 0

        source_urls = _load_urls(urls_file)
        if not source_urls:
            logger.info(
                "amazon_discovery_skipped reason=no_urls_configured path=%s",
                urls_file,
            )
            return 0

        logger.info("amazon_discovery_starting url_count=%s", len(source_urls))

        candidates, page_stats = _run_discovery(
            source_urls,
            logger,
            max_candidates=settings.amazon_discovery_max_candidates,
            max_pages_per_url=settings.amazon_discovery_max_pages_per_url,
        )
        logger.info(
            "amazon_discovery_complete urls=%s pages_fetched=%s raw_asins=%s accepted=%s",
            len(source_urls),
            page_stats["pages_fetched"],
            page_stats["raw_count"],
            len(candidates),
        )

        if not candidates:
            return 0

        accepted, rejected = _run_keepa_ingest(
            [c.asin for c in candidates],
            domain_id=settings.amazon_discovery_domain_id,
            logger=logger,
        )
        logger.info(
            "amazon_discovery_ingest_complete total_asins=%s accepted=%s rejected=%s",
            len(candidates),
            accepted,
            rejected,
        )
        return 0

    return run_job("daily_amazon_discovery", _runner)


def _load_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def _run_discovery(
    source_urls: list[str],
    logger: logging.Logger,
    *,
    max_candidates: int,
    max_pages_per_url: int = 2,
) -> tuple[list[AmazonEsCandidate], dict[str, int]]:
    pages: list[AmazonEsCandidatePoolPage] = []
    raw_count = 0

    for source_url in source_urls:
        url_queue: list[str] = [source_url]
        visited: set[str] = set()
        pages_fetched_for_source = 0

        while url_queue and pages_fetched_for_source < max_pages_per_url:
            current_url = url_queue.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                html = fetch_amazon_es_page(current_url)
                page = discover_candidate_pool_from_html(html, source_url=current_url)
                pages.append(page)
                raw_count += page.raw_candidate_count
                pages_fetched_for_source += 1
                logger.info(
                    "amazon_discovery_page_fetched url=%s source_type=%s raw=%s candidates=%s issues=%s",
                    current_url,
                    page.source_type,
                    page.raw_candidate_count,
                    page.candidate_count,
                    page.page_issues or "none",
                )

                if pages_fetched_for_source < max_pages_per_url:
                    for next_url in discover_pagination_urls_from_html(html, current_url=current_url):
                        if next_url not in visited:
                            url_queue.append(next_url)

            except Exception:
                logger.exception("amazon_discovery_page_failed url=%s", current_url)

    if not pages:
        return [], {"pages_fetched": 0, "raw_count": 0}

    merged = _merge_page_candidates(pages)
    primary_source_type = pages[0].source_type

    filtered = filter_candidate_pool(
        merged,
        source_url="merged://amazon-es-discovery",
        source_type=primary_source_type,
        raw_candidate_count=raw_count,
        page_issues=[],
        duplicate_rejections=[],
        max_candidates=max_candidates,
        max_recovered_missing_price_candidates=10,
    )

    quality = assess_discovery_quality(
        source_url="merged://amazon-es-discovery",
        source_type=primary_source_type,
        raw_candidate_count=raw_count,
        unique_candidate_count=len(merged),
        accepted_candidate_count=filtered.accepted_candidate_count,
        candidates_with_price_count=sum(1 for c in merged if c.price_eur is not None),
        issue_counts={},
    )
    logger.info(
        "amazon_discovery_quality status=%s reasons=%s accepted=%s rejected=%s",
        quality.status,
        quality.reasons or "none",
        filtered.accepted_candidate_count,
        filtered.rejected_candidate_count,
    )

    if quality.status == "low_quality":
        logger.warning(
            "amazon_discovery_skipping_ingest reason=low_quality quality_reasons=%s",
            quality.reasons,
        )
        return [], {"pages_fetched": len(pages), "raw_count": raw_count}

    return filtered.accepted_candidates, {"pages_fetched": len(pages), "raw_count": raw_count}


def _merge_page_candidates(
    pages: list[AmazonEsCandidatePoolPage],
) -> list[AmazonEsCandidate]:
    by_asin: dict[str, AmazonEsCandidate] = {}
    order: list[str] = []

    for page in pages:
        for cand in page.candidates:
            existing = by_asin.get(cand.asin)
            if existing is None:
                by_asin[cand.asin] = AmazonEsCandidate(
                    asin=cand.asin,
                    title=cand.title,
                    price_eur=cand.price_eur,
                    product_url=cand.product_url,
                    source_url=cand.source_url,
                    source_type=cand.source_type,
                    issues=list(cand.issues),
                )
                order.append(cand.asin)
            else:
                if cand.title and (
                    existing.title is None or len(cand.title) > len(existing.title)
                ):
                    existing.title = cand.title
                if existing.price_eur is None and cand.price_eur is not None:
                    existing.price_eur = cand.price_eur

    return [by_asin[asin] for asin in order]


def _run_keepa_ingest(
    asins: list[str],
    *,
    domain_id: int,
    logger: logging.Logger,
) -> tuple[int, int]:
    ensure_source(domain_id)

    with job_session() as db:
        source = db.scalar(select(Source).where(Source.slug == SOURCE_SLUG))
        if source:
            known = set(
                db.scalars(
                    select(ProductSourceRecord.external_id).where(
                        ProductSourceRecord.source_id == source.id,
                        ProductSourceRecord.external_id.in_(asins),
                    )
                ).all()
            )
            asins = [a for a in asins if a not in known]
            if known:
                logger.info(
                    "amazon_discovery_skip_known known=%s remaining=%s",
                    len(known),
                    len(asins),
                )

    if not asins:
        logger.info("amazon_discovery_all_asins_known nothing_to_ingest")
        return 0, 0

    parser = KeepaParser()
    service = IngestionService(
        parser=parser,
        normalizer=DefaultRecordNormalizer(),
        matcher=MatchingService(),
    )

    total_accepted = 0
    total_rejected = 0
    total_batches = -(-len(asins) // DISCOVERY_KEEPA_BATCH_SIZE)
    job_start = time.monotonic()

    logger.info(
        "amazon_discovery_ingest_starting asin_count=%s batch_size=%s total_batches=%s",
        len(asins),
        DISCOVERY_KEEPA_BATCH_SIZE,
        total_batches,
    )

    for batch_num, batch in enumerate(
        chunked(asins, DISCOVERY_KEEPA_BATCH_SIZE), start=1
    ):
        batch_label = f"{batch_num}/{total_batches}"

        try:
            logger.info(
                "amazon_discovery_keepa_fetch_start batch=%s asins=%s",
                batch_label,
                batch,
            )
            fetch_start = time.monotonic()
            raw_payload = asyncio.run(
                asyncio.wait_for(
                    fetch_products_by_asins(
                        batch,
                        domain_id=domain_id,
                        timeout=KEEPA_FETCH_TIMEOUT,
                    ),
                    timeout=KEEPA_FETCH_HARD_TIMEOUT,
                )
            )
            fetch_elapsed = time.monotonic() - fetch_start
            products_returned = len((raw_payload or {}).get("products") or [])
            logger.info(
                "amazon_discovery_keepa_fetch_done batch=%s elapsed_s=%.1f products_returned=%s",
                batch_label,
                fetch_elapsed,
                products_returned,
            )

            logger.info(
                "amazon_discovery_preflight_start batch=%s",
                batch_label,
            )
            preflight_start = time.monotonic()
            preflight = preflight_keepa_batch_for_bulk_ingest(
                raw_payload,
                requested_asins=batch,
                domain_id=domain_id,
            )
            logger.info(
                "amazon_discovery_preflight_done batch=%s elapsed_s=%.1f outcomes=%s accepted_products=%s",
                batch_label,
                time.monotonic() - preflight_start,
                preflight.counts_by_outcome,
                len((preflight.payload or {}).get("products") or []),
            )

            products = (preflight.payload or {}).get("products") or []
            if not products:
                logger.info(
                    "amazon_discovery_batch_empty batch=%s",
                    batch_label,
                )
                continue

            logger.info(
                "amazon_discovery_ingest_start batch=%s product_count=%s",
                batch_label,
                len(products),
            )

            with job_session() as db:
                result = _ingest_batch_with_observability(
                    db=db,
                    service=service,
                    payload=preflight.payload,
                    source_slug=SOURCE_SLUG,
                    logger=logger,
                    batch_label=batch_label,
                )

            total_accepted += result.accepted
            total_rejected += result.rejected
            logger.info(
                "amazon_discovery_batch_ingested batch=%s accepted=%s rejected=%s",
                batch_label,
                result.accepted,
                result.rejected,
            )

        except asyncio.TimeoutError:
            logger.error(
                "amazon_discovery_keepa_timeout batch=%s hard_timeout_s=%s asins=%s skipping_batch",
                batch_label,
                KEEPA_FETCH_HARD_TIMEOUT,
                batch,
            )
        except KeepaConfigurationError:
            raise
        except KeepaClientError:
            logger.exception(
                "amazon_discovery_keepa_error batch=%s asins=%s skipping_batch",
                batch_label,
                batch,
            )
        except Exception:
            logger.exception(
                "amazon_discovery_batch_error batch=%s asins=%s skipping_batch",
                batch_label,
                batch,
            )

    logger.info(
        "amazon_discovery_ingest_summary total_batches=%s total_accepted=%s total_rejected=%s elapsed_s=%.1f",
        total_batches,
        total_accepted,
        total_rejected,
        time.monotonic() - job_start,
    )
    return total_accepted, total_rejected


def _ingest_batch_with_observability(
    *,
    db,
    service: IngestionService,
    payload: dict,
    source_slug: str,
    logger: logging.Logger,
    batch_label: str,
):
    products = (payload or {}).get("products") or []
    ingest_start = time.monotonic()

    logger.info(
        "amazon_discovery_txn_begin_start batch=%s product_count=%s",
        batch_label,
        len(products),
    )

    with db.begin_nested():
        logger.info(
            "amazon_discovery_txn_begin_done batch=%s",
            batch_label,
        )

        logger.info(
            "amazon_discovery_stmt_timeout_set_start batch=%s timeout_ms=%s",
            batch_label,
            INGEST_STATEMENT_TIMEOUT_MS,
        )
        db.execute(
            text("SELECT set_config('statement_timeout', :timeout_value, true)"),
            {"timeout_value": f"{INGEST_STATEMENT_TIMEOUT_MS}ms"},
        )
        logger.info(
            "amazon_discovery_stmt_timeout_set_done batch=%s",
            batch_label,
        )

        logger.info(
            "amazon_discovery_service_ingest_call_start batch=%s source_slug=%s",
            batch_label,
            source_slug,
        )
        service_call_start = time.monotonic()
        result = service.ingest(db, source_slug=source_slug, payload=payload)
        logger.info(
            "amazon_discovery_service_ingest_call_done batch=%s elapsed_s=%.2f accepted=%s rejected=%s",
            batch_label,
            time.monotonic() - service_call_start,
            getattr(result, "accepted", None),
            getattr(result, "rejected", None),
        )

        logger.info(
            "amazon_discovery_explicit_flush_start batch=%s",
            batch_label,
        )
        flush_start = time.monotonic()
        db.flush()
        logger.info(
            "amazon_discovery_explicit_flush_done batch=%s elapsed_s=%.2f",
            batch_label,
            time.monotonic() - flush_start,
        )

    logger.info(
        "amazon_discovery_txn_closed batch=%s total_elapsed_s=%.2f",
        batch_label,
        time.monotonic() - ingest_start,
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())