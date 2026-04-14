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
auto-published by the next run of the hourly pipeline.  The background
Keepa scheduler continues enriching them over the following days.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import settings
from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.parsers.keepa import KeepaParser
from app.ingestion.service import IngestionService
from app.integrations.amazon_es_discovery import (
    AmazonEsCandidate,
    AmazonEsCandidatePoolPage,
    assess_discovery_quality,
    discover_candidate_pool_from_html,
    fetch_amazon_es_page,
    filter_candidate_pool,
)
from app.integrations.keepa_client import KeepaClientError, KeepaConfigurationError, fetch_products_by_asins
from app.integrations.keepa_curation import preflight_keepa_batch_for_bulk_ingest
from app.jobs.common import job_session, run_job
from app.matching.service import MatchingService
from scripts.ingest_keepa_bulk import MAX_BATCH_SIZE, SOURCE_SLUG, chunked, ensure_source


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
            logger.info("amazon_discovery_skipped reason=no_urls_configured path=%s", urls_file)
            return 0

        logger.info("amazon_discovery_starting url_count=%s", len(source_urls))

        # ── Phase 1: discover ASINs ──────────────────────────────────────────
        candidates, page_stats = _run_discovery(
            source_urls,
            logger,
            max_candidates=settings.amazon_discovery_max_candidates,
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

        # ── Phase 2: Keepa ingest ────────────────────────────────────────────
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


# ── helpers ──────────────────────────────────────────────────────────────────


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
) -> tuple[list[AmazonEsCandidate], dict[str, int]]:
    """Fetch each URL, merge candidates, filter, and assess quality.

    Returns the accepted candidate list and basic page stats.
    Returns an empty list (not an error) if quality is too low to ingest.
    """
    pages: list[AmazonEsCandidatePoolPage] = []
    raw_count = 0

    for url in source_urls:
        try:
            html = fetch_amazon_es_page(url)
            page = discover_candidate_pool_from_html(html, source_url=url)
            pages.append(page)
            raw_count += page.raw_candidate_count
            logger.info(
                "amazon_discovery_page_fetched url=%s source_type=%s raw=%s candidates=%s issues=%s",
                url,
                page.source_type,
                page.raw_candidate_count,
                page.candidate_count,
                page.page_issues or "none",
            )
        except Exception:
            logger.exception("amazon_discovery_page_failed url=%s", url)

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


def _merge_page_candidates(pages: list[AmazonEsCandidatePoolPage]) -> list[AmazonEsCandidate]:
    """Deduplicate by ASIN across pages, keeping the richest title and first
    observed price."""
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
                if cand.title and (existing.title is None or len(cand.title) > len(existing.title)):
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
    """Fetch Keepa data for `asins` in batches and ingest directly into the DB.

    Returns (total_accepted, total_rejected).
    KeepaConfigurationError (missing API key) propagates — it should not be
    silenced.  Per-batch KeepaClientErrors are logged and skipped.
    """
    ensure_source(domain_id)

    parser = KeepaParser()
    service = IngestionService(
        parser=parser,
        normalizer=DefaultRecordNormalizer(),
        matcher=MatchingService(),
    )

    total_accepted = 0
    total_rejected = 0

    with job_session() as db:
        for batch_num, batch in enumerate(chunked(asins, MAX_BATCH_SIZE), start=1):
            try:
                raw_payload = asyncio.run(
                    fetch_products_by_asins(batch, domain_id=domain_id, timeout=60.0)
                )
                preflight = preflight_keepa_batch_for_bulk_ingest(
                    raw_payload,
                    requested_asins=batch,
                    domain_id=domain_id,
                )

                if not preflight.payload.get("products"):
                    logger.info(
                        "amazon_discovery_batch_empty batch=%s/%s asins=%s outcomes=%s",
                        batch_num,
                        -(-len(asins) // MAX_BATCH_SIZE),  # ceiling division
                        batch,
                        preflight.counts_by_outcome,
                    )
                    continue

                with db.begin_nested():
                    result = service.ingest(db, source_slug=SOURCE_SLUG, payload=preflight.payload)

                total_accepted += result.accepted
                total_rejected += result.rejected
                logger.info(
                    "amazon_discovery_batch_ingested batch=%s batch_size=%s accepted=%s rejected=%s",
                    batch_num,
                    len(batch),
                    result.accepted,
                    result.rejected,
                )

            except KeepaConfigurationError:
                raise  # Missing API key — surface immediately, abort job
            except KeepaClientError:
                logger.exception(
                    "amazon_discovery_keepa_error batch=%s asins=%s skipping_batch",
                    batch_num,
                    batch,
                )
            except Exception:
                logger.exception(
                    "amazon_discovery_batch_error batch=%s asins=%s skipping_batch",
                    batch_num,
                    batch,
                )

    return total_accepted, total_rejected


if __name__ == "__main__":
    raise SystemExit(main())
