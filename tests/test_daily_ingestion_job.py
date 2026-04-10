from __future__ import annotations

from types import SimpleNamespace

from app.jobs import daily_ingestion


class FakeLogger:
    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.exception_messages: list[str] = []

    def info(self, message: str, *args) -> None:
        self.info_messages.append(message % args if args else message)

    def exception(self, message: str, *args) -> None:
        self.exception_messages.append(message % args if args else message)


def test_run_serpapi_batch_continues_on_per_query_failure(monkeypatch, tmp_path) -> None:
    queries_file = tmp_path / "queries.json"
    queries_file.write_text('["good query", "bad query"]')

    def fake_run_serpapi_ingestion_query(query, limit, *, ingest_runner):
        if query == "bad query":
            raise RuntimeError("boom")
        return {
            "query": query,
            "fetched_results": 6,
            "mapped_results": 4,
            "ingest_result": {
                "accepted": 3,
                "rejected": 1,
            },
        }

    monkeypatch.setattr(daily_ingestion, "run_serpapi_ingestion_query", fake_run_serpapi_ingestion_query)
    monkeypatch.setattr(daily_ingestion, "ingest_csv_direct", lambda payload: {})
    logger = FakeLogger()
    args = SimpleNamespace(
        serpapi_queries_file=str(queries_file),
        default_query_limit=5,
    )

    summary = daily_ingestion._run_serpapi_batch(logger, args)

    assert summary["total_queries"] == 2
    assert summary["successful_queries"] == 1
    assert summary["failed_queries"] == 1
    assert summary["total_fetched_results"] == 6
    assert summary["total_mapped_results"] == 4
    assert summary["total_accepted"] == 3
    assert summary["total_rejected"] == 1
    assert any("serpapi_query_complete" in message for message in logger.info_messages)
    assert any("serpapi_query_failed" in message for message in logger.exception_messages)


def test_summarize_serpapi_results_builds_final_totals() -> None:
    summary = daily_ingestion._summarize_serpapi_results(
        [
            {
                "query": "wireless earbuds",
                "status": "success",
                "fetched_results": 10,
                "mapped_results": 6,
                "accepted": 4,
                "rejected": 2,
            },
            {
                "query": "robot vacuum",
                "status": "failed",
                "fetched_results": 0,
                "mapped_results": 0,
                "accepted": 0,
                "rejected": 0,
            },
        ]
    )

    assert summary == {
        "total_queries": 2,
        "successful_queries": 1,
        "failed_queries": 1,
        "total_fetched_results": 10,
        "total_mapped_results": 6,
        "total_accepted": 4,
        "total_rejected": 2,
        "queries": [
            {
                "query": "wireless earbuds",
                "status": "success",
                "fetched_results": 10,
                "mapped_results": 6,
                "accepted": 4,
                "rejected": 2,
            },
            {
                "query": "robot vacuum",
                "status": "failed",
                "fetched_results": 0,
                "mapped_results": 0,
                "accepted": 0,
                "rejected": 0,
            },
        ],
    }
