from __future__ import annotations

import argparse

from app.jobs.daily_ai_drafts import main as ai_main
from app.jobs.daily_ingestion import main as ingestion_main
from app.jobs.daily_scoring import main as scoring_main
from app.jobs.daily_stats_recompute import main as stats_main
from app.jobs.common import run_job


def main() -> int:
    args = _parse_args()

    def _runner(logger):
        logger.info("starting daily job sequence")
        if args.include_ingestion:
            ingestion_main()
        stats_main()
        scoring_main()
        ai_main()
        logger.info("daily job sequence complete")
        return 0

    return run_job("run_daily", _runner)


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-ingestion", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
