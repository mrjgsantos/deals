from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.parsers.affiliate_feed import AffiliateFeedCSVParser
from app.ingestion.parsers.keepa import KeepaParser
from app.ingestion.service import IngestionService
from app.jobs.common import job_session, run_job
from app.matching.service import MatchingService
from scripts.ingest_serpapi_google_shopping import ingest_csv_direct, run_serpapi_ingestion_query


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    def _runner(logger):
        if _should_run_serpapi_batch(args):
            if not settings.serpapi_enabled:
                logger.info("serpapi_ingestion_skipped reason=serpapi_disabled")
                return 0
            summary = _run_serpapi_batch(logger, args)
            logger.info(
                "serpapi_batch_complete total_queries=%s successful_queries=%s failed_queries=%s total_fetched=%s total_mapped=%s total_accepted=%s total_rejected=%s",
                summary["total_queries"],
                summary["successful_queries"],
                summary["failed_queries"],
                summary["total_fetched_results"],
                summary["total_mapped_results"],
                summary["total_accepted"],
                summary["total_rejected"],
            )
            return 1 if summary["failed_queries"] else 0

        manifests = _load_manifests(args)
        parser_map = {
            "keepa": KeepaParser(),
            "affiliate_csv": AffiliateFeedCSVParser(),
        }

        with job_session() as db:
            for manifest in manifests:
                try:
                    with db.begin_nested():
                        parser = parser_map[manifest["parser"]]
                        payload = _load_payload(manifest["payload_file"], manifest["parser"])
                        service = IngestionService(
                            parser=parser,
                            normalizer=DefaultRecordNormalizer(),
                            matcher=MatchingService(),
                        )
                        result = service.ingest(db, source_slug=manifest["source_slug"], payload=payload)
                    logger.info(
                        "ingestion_complete source=%s parser=%s processed=%s accepted=%s rejected=%s",
                        result.source_slug,
                        result.parser_name,
                        result.processed,
                        result.accepted,
                        result.rejected,
                    )
                except Exception:
                    logger.exception(
                        "ingestion_manifest_failed source=%s parser=%s payload_file=%s",
                        manifest.get("source_slug"),
                        manifest.get("parser"),
                        manifest.get("payload_file"),
                    )
        return 0

    return run_job("daily_ingestion", _runner)


def _parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-file")
    parser.add_argument("--source-slug")
    parser.add_argument("--parser")
    parser.add_argument("--payload-file")
    parser.add_argument("--serpapi-queries-file", default=settings.serpapi_queries_file)
    parser.add_argument("--default-query-limit", type=int, default=settings.serpapi_query_limit)
    return parser.parse_args(argv)


def _load_manifests(args) -> list[dict[str, str]]:
    if args.manifest_file:
        return json.loads(Path(args.manifest_file).read_text())
    if args.source_slug and args.parser and args.payload_file:
        return [
            {
                "source_slug": args.source_slug,
                "parser": args.parser,
                "payload_file": args.payload_file,
            }
        ]
    raise ValueError("provide --manifest-file or --source-slug/--parser/--payload-file")


def _should_run_serpapi_batch(args) -> bool:
    return not any([args.manifest_file, args.source_slug, args.parser, args.payload_file])


def _load_serpapi_queries(path: str, *, default_limit: int) -> list[dict[str, object]]:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, list):
        raise ValueError("serpapi queries file must contain a list")

    queries: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, str):
            query = item.strip()
            if not query:
                raise ValueError("serpapi query entries must not be empty")
            queries.append({"query": query, "limit": default_limit, "enabled": True})
            continue
        if not isinstance(item, dict):
            raise ValueError("serpapi query entries must be strings or objects")

        query = str(item.get("query") or "").strip()
        if not query:
            raise ValueError("serpapi query object is missing query")

        enabled = bool(item.get("enabled", True))
        limit = int(item.get("limit", default_limit))
        if limit <= 0:
            raise ValueError("serpapi query limit must be positive")

        queries.append({"query": query, "limit": limit, "enabled": enabled})
    return queries


def _run_serpapi_batch(logger, args) -> dict[str, object]:
    queries = _load_serpapi_queries(args.serpapi_queries_file, default_limit=args.default_query_limit)
    enabled_queries = [query for query in queries if query["enabled"]]
    results: list[dict[str, object]] = []

    for item in enabled_queries:
        query = str(item["query"])
        limit = int(item["limit"])
        try:
            result = run_serpapi_ingestion_query(
                query,
                limit,
                ingest_runner=ingest_csv_direct,
            )
            ingest_result = result["ingest_result"]
            results.append(
                {
                    "query": query,
                    "status": "success",
                    "fetched_results": result["fetched_results"],
                    "mapped_results": result["mapped_results"],
                    "accepted": ingest_result["accepted"],
                    "rejected": ingest_result["rejected"],
                }
            )
            logger.info(
                "serpapi_query_complete query=%s fetched=%s mapped=%s accepted=%s rejected=%s",
                query,
                result["fetched_results"],
                result["mapped_results"],
                ingest_result["accepted"],
                ingest_result["rejected"],
            )
        except Exception as exc:
            results.append(
                {
                    "query": query,
                    "status": "failed",
                    "error": str(exc),
                    "fetched_results": 0,
                    "mapped_results": 0,
                    "accepted": 0,
                    "rejected": 0,
                }
            )
            logger.exception("serpapi_query_failed query=%s limit=%s", query, limit)

    return _summarize_serpapi_results(results)


def _summarize_serpapi_results(results: list[dict[str, object]]) -> dict[str, object]:
    return {
        "total_queries": len(results),
        "successful_queries": sum(1 for result in results if result["status"] == "success"),
        "failed_queries": sum(1 for result in results if result["status"] == "failed"),
        "total_fetched_results": sum(int(result["fetched_results"]) for result in results),
        "total_mapped_results": sum(int(result["mapped_results"]) for result in results),
        "total_accepted": sum(int(result["accepted"]) for result in results),
        "total_rejected": sum(int(result["rejected"]) for result in results),
        "queries": results,
    }


def _load_payload(payload_file: str, parser_name: str):
    raw_text = Path(payload_file).read_text()
    if parser_name == "affiliate_csv":
        return raw_text
    return json.loads(raw_text)


if __name__ == "__main__":
    raise SystemExit(main())
