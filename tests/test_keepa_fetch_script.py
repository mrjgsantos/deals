from __future__ import annotations

from pathlib import Path

import pytest

from scripts import ingest_keepa


def test_fetch_keepa_payload_delegates_to_shared_client(monkeypatch) -> None:
    calls: list[tuple[list[str], int | None, float]] = []

    async def fake_fetch_products_by_asins(asins, *, domain_id=None, timeout=30.0):
        calls.append((asins, domain_id, timeout))
        return {"products": [{"asin": "B0TEST1234"}]}

    monkeypatch.setattr(ingest_keepa, "fetch_products_by_asins", fake_fetch_products_by_asins)

    payload = ingest_keepa.fetch_keepa_payload(["B0TEST1234", "B0TEST5678"], 3)

    assert payload["products"][0]["asin"] == "B0TEST1234"
    assert calls == [(["B0TEST1234", "B0TEST5678"], 3, 60.0)]


def test_fetch_keepa_payload_surfaces_client_errors(monkeypatch) -> None:
    async def fake_fetch_products_by_asins(asins, *, domain_id=None, timeout=30.0):
        raise ingest_keepa.KeepaClientError("keepa_empty_products")

    monkeypatch.setattr(ingest_keepa, "fetch_products_by_asins", fake_fetch_products_by_asins)

    with pytest.raises(SystemExit, match="keepa_empty_products"):
        ingest_keepa.fetch_keepa_payload(["B0TEST1234"], 1)


def test_load_asins_reads_json_array_file(tmp_path: Path) -> None:
    asin_file = tmp_path / "asins.json"
    asin_file.write_text('["b0test1234", "B0TEST5678"]')
    args = type("Args", (), {"asins": [], "asin_file": str(asin_file)})()

    asins = ingest_keepa.load_asins(args)

    assert asins == ["B0TEST1234", "B0TEST5678"]
