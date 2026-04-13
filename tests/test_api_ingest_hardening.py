from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.ingestion.exceptions import PayloadValidationError, SourceNotFoundError
from app.ingestion.schemas import IngestionBatchResult, IngestionRecordResult
from app.main import app


def override_db():
    class FakeDB:
        def commit(self):
            pass

        def rollback(self):
            pass

    yield FakeDB()


class FakeIngestionService:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error

    def ingest(self, db, source_slug, payload):
        if self.error is not None:
            raise self.error
        return self.result


def test_ingest_run_returns_200_with_serialized_success_body(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.ingest.get_ingestion_service",
        lambda parser_name: FakeIngestionService(
            result=IngestionBatchResult(
                source_slug="amazon-keepa",
                parser_name="keepa",
                processed=1,
                accepted=1,
                rejected=0,
                records=[
                    IngestionRecordResult(
                        raw_ingestion_record_id="raw-1",
                        product_source_record_id="psr-1",
                        price_observation_id="po-1",
                        status="accepted",
                        rejection_reason=None,
                    )
                ],
            )
        ),
    )
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingest/run",
        json={
            "source_slug": "amazon-keepa",
            "parser": "keepa",
            "payload": {"products": [{"asin": "B0CCEXAMPLE"}]},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "source_slug": "amazon-keepa",
        "parser_name": "keepa",
        "processed": 1,
        "accepted": 1,
        "rejected": 0,
        "skipped_due_to_dedupe": 0,
        "records": [
            {
                "raw_ingestion_record_id": "raw-1",
                "product_source_record_id": "psr-1",
                "price_observation_id": "po-1",
                "status": "accepted",
                "rejection_reason": None,
            }
        ],
    }
    app.dependency_overrides.clear()


def test_ingest_run_returns_404_for_missing_source(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.ingest.get_ingestion_service",
        lambda parser_name: FakeIngestionService(error=SourceNotFoundError("missing")),
    )
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingest/run",
        json={"source_slug": "missing-source", "parser": "keepa", "payload": {"products": []}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "source_not_found"
    app.dependency_overrides.clear()


def test_ingest_run_returns_400_for_payload_validation_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.ingest.get_ingestion_service",
        lambda parser_name: FakeIngestionService(error=PayloadValidationError("parser returned too many records")),
    )
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingest/run",
        json={"source_slug": "source-a", "parser": "keepa", "payload": {"products": []}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "parser returned too many records"
    app.dependency_overrides.clear()


def test_ingest_run_rejects_oversized_list_payload() -> None:
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingest/run",
        json={
            "source_slug": "source-a",
            "parser": "keepa",
            "payload": [{} for _ in range(5001)],
        },
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_ingest_run_returns_400_for_unsupported_parser() -> None:
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingest/run",
        json={
            "source_slug": "source-a",
            "parser": "unknown_parser",
            "payload": {"products": [{"asin": "B0CCEXAMPLE"}]},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported_parser"
    app.dependency_overrides.clear()


def test_ingest_run_returns_500_for_unhandled_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.ingest.get_ingestion_service",
        lambda parser_name: FakeIngestionService(error=RuntimeError("boom")),
    )
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingest/run",
        json={
            "source_slug": "source-a",
            "parser": "keepa",
            "payload": {"products": [{"asin": "B0CCEXAMPLE"}]},
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "ingestion_failed"
    app.dependency_overrides.clear()
