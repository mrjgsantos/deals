from __future__ import annotations

import argparse

from app.jobs.daily_ai_drafts import main as ai_main
from app.jobs.daily_auto_publish import main as auto_publish_main
from app.jobs.daily_ingestion import main as ingestion_main
from app.jobs.daily_scoring import main as scoring_main
from app.jobs.daily_stats_recompute import main as stats_main
from app.jobs.common import run_job


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    def _runner(logger):
        logger.info("starting daily job sequence")
        step_results: list[tuple[str, int]] = []
        if args.include_ingestion:
            step_results.append(("ingestion", ingestion_main([])))
        step_results.append(("stats_recompute", stats_main()))
        step_results.append(("scoring", scoring_main()))
        step_results.append(("auto_publish", auto_publish_main()))
        step_results.append(("ai_drafts", ai_main()))

        failed_steps = [name for name, exit_code in step_results if exit_code != 0]
        logger.info("daily job sequence complete failed_steps=%s", ",".join(failed_steps) or "none")
        return 1 if failed_steps else 0

    return run_job("run_daily", _runner)


def _parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-ingestion", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
