from __future__ import annotations

from app.jobs import run_daily


class FakeLogger:
    def __init__(self) -> None:
        self.info_messages: list[str] = []

    def info(self, message: str, *args) -> None:
        self.info_messages.append(message % args if args else message)


def test_run_daily_includes_ingestion_without_reparsing_parent_args(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    def fake_run_job(job_name, callback):
        assert job_name == "run_daily"
        return callback(FakeLogger())

    def fake_ingestion_main(argv=None):
        calls.append(("ingestion", argv))
        return 0

    monkeypatch.setattr(run_daily, "run_job", fake_run_job)
    monkeypatch.setattr(run_daily, "ingestion_main", fake_ingestion_main)
    monkeypatch.setattr(run_daily, "stats_main", lambda: calls.append(("stats", None)) or 0)
    monkeypatch.setattr(run_daily, "scoring_main", lambda: calls.append(("scoring", None)) or 0)
    monkeypatch.setattr(run_daily, "ai_main", lambda: calls.append(("ai", None)) or 0)

    result = run_daily.main(["--include-ingestion"])

    assert result == 0
    assert calls == [
        ("ingestion", []),
        ("stats", None),
        ("scoring", None),
        ("ai", None),
    ]


def test_run_daily_returns_non_zero_when_any_step_fails(monkeypatch) -> None:
    def fake_run_job(job_name, callback):
        return callback(FakeLogger())

    monkeypatch.setattr(run_daily, "run_job", fake_run_job)
    monkeypatch.setattr(run_daily, "ingestion_main", lambda argv=None: 0)
    monkeypatch.setattr(run_daily, "stats_main", lambda: 0)
    monkeypatch.setattr(run_daily, "scoring_main", lambda: 1)
    monkeypatch.setattr(run_daily, "ai_main", lambda: 0)

    result = run_daily.main([])

    assert result == 1
