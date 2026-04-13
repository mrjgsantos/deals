from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.integrations.amazon_es_discovery import (
    AmazonEsDiscoveryResult,
    AmazonEsCandidate,
    AmazonEsCandidatePoolPage,
    BEST_EFFORT_SOURCE_TYPES,
    DEFAULT_MAX_PAGINATION_PAGES,
    assess_discovery_quality,
    discover_candidate_pool_from_html,
    discover_pagination_urls_from_html,
    fetch_amazon_es_page,
    filter_candidate_pool,
)
from scripts import ingest_keepa_bulk

DEFAULT_MAX_CANDIDATES = 100
LOW_QUALITY_EXIT_CODE = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Amazon.es product ASINs from commercial-intent pages, apply light price filtering, "
            "and optionally hand accepted ASINs to the existing Keepa bulk ingestion flow."
        )
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        default=[],
        help="Amazon.es source URL to scrape. May be provided multiple times.",
    )
    parser.add_argument(
        "--url-file",
        help="Optional newline-delimited file of Amazon.es source URLs.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=DEFAULT_MAX_CANDIDATES,
        help="Maximum accepted ASINs to keep across all pages (default: %(default)s).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGINATION_PAGES,
        help="Maximum pages to fetch per source when pagination is detected (default: %(default)s).",
    )
    parser.add_argument(
        "--write-asins",
        help="Optional output file path for accepted ASINs, one per line.",
    )
    parser.add_argument(
        "--run-keepa-bulk",
        action="store_true",
        help="Pass accepted ASINs into the existing bulk Keepa ingestion path.",
    )
    parser.add_argument(
        "--api-base-url",
        default=ingest_keepa_bulk.API_BASE_URL,
        help="Base URL for the existing backend API when using --run-keepa-bulk.",
    )
    parser.add_argument(
        "--domain-id",
        type=int,
        default=ingest_keepa_bulk.DOMAIN_ID,
        help="Keepa/Amazon domain id for optional bulk handoff (default: %(default)s).",
    )
    parser.add_argument(
        "--show-details",
        action="store_true",
        help="Include accepted/rejected candidate details in per-page and final summaries.",
    )
    return parser.parse_args()


def load_source_urls(args: argparse.Namespace) -> list[str]:
    candidates: list[str] = []
    candidates.extend(str(url).strip() for url in args.urls or [])
    if args.url_file:
        candidates.extend(_load_url_file(Path(args.url_file)))

    deduped: list[str] = []
    seen: set[str] = set()
    for raw_url in candidates:
        if not raw_url:
            continue
        if raw_url in seen:
            continue
        seen.add(raw_url)
        deduped.append(raw_url)
    return deduped


def _load_url_file(path: Path) -> list[str]:
    values: list[str] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        values.append(line)
    return values


def _aggregate_results(
    *,
    page_results: list[AmazonEsCandidatePoolPage],
    source_summaries: list[dict[str, object]],
    filtered_result: AmazonEsDiscoveryResult,
    total_after_dedupe_count: int,
    include_candidates: bool,
) -> dict[str, object]:
    accepted_candidates = [candidate.as_dict() for candidate in filtered_result.accepted_candidates]
    rejected_candidates = [candidate.as_dict() for candidate in filtered_result.rejected_candidates]
    page_summaries: list[dict[str, object]] = []

    for index, page in enumerate(page_results):
        page_summaries.append(
            {
                "source_url": page.source_url,
                "source_type": page.source_type,
                "page_number": _page_number_for_result(page, default=index + 1),
                "raw_candidate_count": page.raw_candidate_count,
                "candidate_count": page.candidate_count,
                "candidate_asins": page.candidate_asins,
            }
        )

    summary: dict[str, object] = {
        "event": "amazon_es_discovery_summary",
        "source_count": len(source_summaries),
        "fetched_page_count": len(page_results),
        "total_raw_asin_count": sum(page.raw_candidate_count for page in page_results),
        "total_after_dedupe_count": total_after_dedupe_count,
        "accepted_candidate_count": filtered_result.accepted_candidate_count,
        "borderline_candidate_count": filtered_result.accepted_borderline_count,
        "rejected_candidate_count": filtered_result.rejected_candidate_count,
        "accepted_standard_count": filtered_result.accepted_standard_count,
        "accepted_with_price_count": filtered_result.accepted_with_price_count,
        "accepted_price_missing_count": filtered_result.accepted_price_missing_count,
        "accepted_price_missing_recovered_count": filtered_result.accepted_price_missing_recovered_count,
        "recovered_asin_count": len(filtered_result.recovered_asins),
        "recovered_asins": filtered_result.recovered_asins,
        "total_unique_asin_count": len(filtered_result.accepted_asins),
        "counts_by_reason": filtered_result.counts_by_reason,
        "accepted_asins": filtered_result.accepted_asins,
        "source_summaries": source_summaries,
        "page_summaries": page_summaries,
    }
    if include_candidates:
        summary["accepted_candidates"] = accepted_candidates
        summary["rejected_candidates"] = rejected_candidates
    return summary


def _page_number_for_result(result: AmazonEsDiscoveryResult, *, default: int) -> int:
    from app.integrations.amazon_es_discovery import _infer_page_number  # local import avoids widening script surface

    return _infer_page_number(result.source_url) or default


def _normalize_page_url(url: str) -> str:
    from app.integrations.amazon_es_discovery import _normalize_page_url as normalize_page_url

    return normalize_page_url(url)


def _discover_source_candidate_pages(
    source_url: str,
    *,
    max_pages: int,
) -> list[AmazonEsCandidatePoolPage]:
    queue: list[str] = [source_url]
    visited_urls: set[str] = set()
    page_results: list[AmazonEsCandidatePoolPage] = []

    while queue and len(page_results) < max_pages:
        page_url = queue.pop(0)
        normalized_page_url = _normalize_page_url(page_url)
        if normalized_page_url in visited_urls:
            continue
        visited_urls.add(normalized_page_url)

        html = fetch_amazon_es_page(page_url)
        page_result = discover_candidate_pool_from_html(html, source_url=page_url)
        page_results.append(page_result)

        if page_result.candidate_count == 0:
            break

        for next_url in discover_pagination_urls_from_html(html, current_url=page_url):
            normalized_next_url = _normalize_page_url(next_url)
            if normalized_next_url in visited_urls or any(_normalize_page_url(item) == normalized_next_url for item in queue):
                continue
            queue.append(next_url)

    return page_results


def _merge_candidates_globally(
    page_results: list[AmazonEsCandidatePoolPage],
) -> tuple[list[AmazonEsCandidate], int]:
    merged_by_asin: dict[str, AmazonEsCandidate] = {}
    ordered_asins: list[str] = []
    raw_candidate_count = sum(page.raw_candidate_count for page in page_results)

    for page in page_results:
        for candidate in page.candidates:
            existing = merged_by_asin.get(candidate.asin)
            if existing is None:
                merged_by_asin[candidate.asin] = AmazonEsCandidate(
                    asin=candidate.asin,
                    title=candidate.title,
                    price_eur=candidate.price_eur,
                    product_url=candidate.product_url,
                    source_url=candidate.source_url,
                    source_type=candidate.source_type,
                    issues=list(candidate.issues),
                )
                ordered_asins.append(candidate.asin)
                continue
            if candidate.title and (existing.title is None or len(candidate.title) > len(existing.title)):
                existing.title = candidate.title
            if existing.price_eur is None and candidate.price_eur is not None:
                existing.price_eur = candidate.price_eur
            if existing.product_url is None and candidate.product_url is not None:
                existing.product_url = candidate.product_url

    return [merged_by_asin[asin] for asin in ordered_asins], raw_candidate_count


def _rejection_reason_counts(result: AmazonEsDiscoveryResult) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for candidate in result.rejected_candidates:
        counts[candidate.reason] += 1
    return dict(sorted(counts.items()))


def _issue_counts_for_pages(page_results: list[AmazonEsCandidatePoolPage]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for page in page_results:
        for issue in page.page_issues:
            counts[issue] += 1
    return dict(sorted(counts.items()))


def _assess_run_quality(
    source_summaries: list[dict[str, object]],
    *,
    failed_source_count: int,
) -> tuple[str, list[str]]:
    if not source_summaries:
        return "low_quality", ["no_successful_sources"]

    viable_sources = [
        summary
        for summary in source_summaries
        if str(summary.get("quality_status")) in {"healthy", "warning"}
    ]
    non_best_effort_sources = [
        summary for summary in source_summaries if str(summary.get("source_type")) not in BEST_EFFORT_SOURCE_TYPES
    ]
    viable_non_best_effort_sources = [
        summary for summary in viable_sources if str(summary.get("source_type")) not in BEST_EFFORT_SOURCE_TYPES
    ]

    reasons: list[str] = []
    if non_best_effort_sources and not viable_non_best_effort_sources:
        reasons.append("no_viable_primary_sources")
    if not viable_sources:
        reasons.append("all_sources_low_quality")
    if failed_source_count == len(source_summaries) + failed_source_count and failed_source_count > 0:
        reasons.append("all_sources_failed")

    if reasons:
        return "low_quality", reasons
    return "healthy", []


def main() -> int:
    args = parse_args()
    source_urls = load_source_urls(args)
    if not source_urls:
        raise SystemExit("At least one --url or --url-file entry is required.")
    if args.max_candidates <= 0:
        raise SystemExit("--max-candidates must be greater than zero.")

    source_summaries: list[dict[str, object]] = []
    all_page_results: list[AmazonEsCandidatePoolPage] = []
    failed_source_count = 0

    for source_url in source_urls:
        try:
            page_results = _discover_source_candidate_pages(
                source_url,
                max_pages=args.max_pages,
            )
        except Exception as exc:
            failed_source_count += 1
            print(
                json.dumps(
                    {
                        "event": "amazon_es_discovery_source_error",
                        "source_url": source_url,
                        "reason": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            )
            continue

        source_type = page_results[0].source_type if page_results else "unknown"
        source_unique_asins = {candidate.asin for page in page_results for candidate in page.candidates}
        source_unique_candidates, source_raw_asin_count = _merge_candidates_globally(page_results)
        source_issue_counts = _issue_counts_for_pages(page_results)
        source_filtered_result = filter_candidate_pool(
            source_unique_candidates,
            source_url=source_url,
            source_type=source_type,
            raw_candidate_count=source_raw_asin_count,
            page_issues=[],
            duplicate_rejections=[],
            max_candidates=None,
            max_recovered_missing_price_candidates=20,
        )
        source_quality = assess_discovery_quality(
            source_url=source_url,
            source_type=source_type,
            raw_candidate_count=source_raw_asin_count,
            unique_candidate_count=len(source_unique_asins),
            accepted_candidate_count=source_filtered_result.accepted_candidate_count,
            candidates_with_price_count=sum(
                1 for candidate in source_unique_candidates if candidate.price_eur is not None
            ),
            issue_counts=source_issue_counts,
        )
        source_summaries.append(
            {
                "source_url": source_url,
                "source_type": source_type,
                "fetched_page_count": len(page_results),
                "source_raw_asin_count": source_raw_asin_count,
                "source_unique_asin_count": len(source_unique_asins),
                "source_candidate_asins": [candidate.asin for candidate in source_unique_candidates],
                "accepted_count": source_filtered_result.accepted_candidate_count,
                "success_rate": round(source_quality.acceptance_rate, 4),
                "extraction_success_rate": round(source_quality.extraction_success_rate, 4),
                "price_coverage_rate": round(source_quality.price_coverage_rate, 4),
                "quality_status": source_quality.status,
                "quality_reasons": source_quality.reasons,
                "issue_counts": source_quality.issue_counts,
                "rejection_reasons_breakdown": _rejection_reason_counts(source_filtered_result),
            }
        )
        all_page_results.extend(page_results)
        print(
            json.dumps(
                {
                    "event": "amazon_es_discovery_source_summary",
                    "source_url": source_url,
                    "source_type": source_type,
                    "fetched_page_count": len(page_results),
                    "source_raw_asin_count": source_raw_asin_count,
                    "source_unique_asin_count": len(source_unique_asins),
                    "source_candidate_asins": [candidate.asin for candidate in source_unique_candidates],
                    "accepted_count": source_filtered_result.accepted_candidate_count,
                    "success_rate": round(source_quality.acceptance_rate, 4),
                    "extraction_success_rate": round(source_quality.extraction_success_rate, 4),
                    "price_coverage_rate": round(source_quality.price_coverage_rate, 4),
                    "quality_status": source_quality.status,
                    "quality_reasons": source_quality.reasons,
                    "issue_counts": source_quality.issue_counts,
                    "rejection_reasons_breakdown": _rejection_reason_counts(source_filtered_result),
                }
            )
        )
        for page in page_results:
            print(
                json.dumps(
                    {
                        "event": "amazon_es_discovery_page_summary",
                        "source_url": page.source_url,
                        "page_number": _page_number_for_result(page, default=1),
                        "raw_candidate_count": page.raw_candidate_count,
                        "candidate_count": page.candidate_count,
                        "candidate_asins": page.candidate_asins,
                        "page_issues": page.page_issues,
                    }
                )
            )

    merged_candidates, raw_candidate_count = _merge_candidates_globally(all_page_results)
    filtered_result = filter_candidate_pool(
        merged_candidates,
        source_url="merged://amazon-es-discovery",
        source_type="merged",
        raw_candidate_count=raw_candidate_count,
        page_issues=[],
        duplicate_rejections=[],
        max_candidates=args.max_candidates,
        max_recovered_missing_price_candidates=20,
    )
    summary = _aggregate_results(
        page_results=all_page_results,
        source_summaries=source_summaries,
        filtered_result=filtered_result,
        total_after_dedupe_count=len(merged_candidates),
        include_candidates=args.show_details,
    )
    run_quality_status, run_quality_reasons = _assess_run_quality(
        source_summaries,
        failed_source_count=failed_source_count,
    )
    overall_issue_counts = _issue_counts_for_pages(all_page_results)
    overall_extraction_opportunities = (
        raw_candidate_count
        + overall_issue_counts.get("missing_asin", 0)
        + overall_issue_counts.get("invalid_asin_pattern", 0)
    )
    summary["failed_source_count"] = failed_source_count
    summary["overall_extraction_success_rate"] = round(
        raw_candidate_count / overall_extraction_opportunities if overall_extraction_opportunities > 0 else 1.0,
        4,
    )
    summary["overall_acceptance_rate"] = round(
        filtered_result.accepted_candidate_count / len(merged_candidates) if merged_candidates else 0.0,
        4,
    )
    summary["quality_status"] = run_quality_status
    summary["quality_reasons"] = run_quality_reasons
    print(json.dumps(summary, indent=2))

    if run_quality_status == "low_quality":
        print(
            json.dumps(
                {
                    "event": "amazon_es_discovery_run_skipped",
                    "reason": "low_extraction_quality",
                    "quality_reasons": run_quality_reasons,
                    "failed_source_count": failed_source_count,
                    "source_count": len(source_summaries),
                }
            )
        )
        return LOW_QUALITY_EXIT_CODE

    accepted_asins = list(summary["accepted_asins"])
    if args.write_asins:
        output_path = Path(args.write_asins)
        output_path.write_text("\n".join(accepted_asins) + ("\n" if accepted_asins else ""))
        print(
            json.dumps(
                {
                    "event": "amazon_es_discovery_asins_written",
                    "path": str(output_path),
                    "accepted_asin_count": len(accepted_asins),
                }
            )
        )

    if args.run_keepa_bulk:
        print(
            json.dumps(
                {
                    "event": "amazon_es_discovery_keepa_handoff",
                    "accepted_asin_count": len(accepted_asins),
                    "accepted_asins": accepted_asins,
                    "domain_id": args.domain_id,
                    "api_base_url": args.api_base_url,
                }
            )
        )
        return ingest_keepa_bulk.run_bulk_ingest_for_asins(
            accepted_asins,
            api_base_url=args.api_base_url,
            domain_id=args.domain_id,
            source="discovery",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
