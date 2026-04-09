from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.parsers.affiliate_feed import AffiliateFeedCSVParser
from app.ingestion.parsers.keepa import KeepaParser
from app.ingestion.service import IngestionService
from app.jobs.common import job_session, run_job
from app.matching.service import MatchingService


def main() -> int:
    args = _parse_args()

    def _runner(logger):
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


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-file")
    parser.add_argument("--source-slug")
    parser.add_argument("--parser")
    parser.add_argument("--payload-file")
    return parser.parse_args()


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


def _load_payload(payload_file: str, parser_name: str):
    raw_text = Path(payload_file).read_text()
    if parser_name == "affiliate_csv":
        return raw_text
    return json.loads(raw_text)


if __name__ == "__main__":
    raise SystemExit(main())
