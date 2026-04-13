from __future__ import annotations

from pathlib import Path

from scripts import ingest_keepa_bulk


def test_bulk_script_maps_raw_keepa_products_into_ingestable_payload(monkeypatch, capsys) -> None:
    async def fake_fetch_batch(asins, *, domain_id):
        return {
            "products": [
                {
                    "asin": "B09G9FPGTN",
                    "title": "Echo Dot 5th Gen",
                    "brand": "Amazon",
                    "manufacturer": "Amazon",
                    "lastUpdate": 8000000,
                    "csv": [
                        [],
                        [7999800, 6999, 7999920, 4999],
                        [],
                        [],
                        [7999800, 7999],
                    ],
                }
            ]
        }

    ingested_payloads: list[dict] = []

    def fake_ingest_keepa_payload(payload, api_base_url):
        ingested_payloads.append(payload)
        return {"accepted": 1, "rejected": 0, "skipped_due_to_dedupe": 0}

    monkeypatch.setattr(ingest_keepa_bulk, "ensure_source", lambda domain_id: None)
    monkeypatch.setattr(
        ingest_keepa_bulk,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {"asins": ["B09G9FPGTN"], "asin_file": None, "api_base_url": "http://app:8000", "domain_id": 9},
        )(),
    )
    monkeypatch.setattr(ingest_keepa_bulk, "fetch_batch", fake_fetch_batch)
    monkeypatch.setattr(ingest_keepa_bulk, "ingest_keepa_payload", fake_ingest_keepa_payload)

    exit_code = ingest_keepa_bulk.main()

    captured = capsys.readouterr()
    product = ingested_payloads[0]["products"][0]

    assert exit_code == 0
    assert '"event": "asin_input_curation"' in captured.out
    assert '"event": "keepa_batch_plan"' in captured.out
    assert '"batch_size": 20' in captured.out
    assert '"total_batches": 1' in captured.out
    assert '"event": "keepa_batch_preflight"' in captured.out
    assert '"total_fetched_products": 1' in captured.out
    assert '"total_posted_products": 1' in captured.out
    assert '"total_skipped_products": 0' in captured.out
    assert '"total_accepted": 1' in captured.out
    assert '"total_rejected": 0' in captured.out
    assert '"skipped_due_to_dedupe": 0' in captured.out
    assert '"valid_and_enrichable": 1' in captured.out
    assert product["domainId"] == 9
    assert product["currency"] == "EUR"
    assert product["newPrice"] == 4999
    assert product["lastPrice"] == 4999
    assert product["listPrice"] == 7999
    assert product["productURL"] == "https://www.amazon.es/dp/B09G9FPGTN"


def test_bulk_script_skips_sparse_keepa_products_before_ingest(monkeypatch, capsys) -> None:
    async def fake_fetch_batch(asins, *, domain_id):
        return {
            "products": [
                {
                    "asin": "B09G9FPGTN",
                    "title": "Valid Product",
                    "brand": "Amazon",
                    "manufacturer": "Amazon",
                    "lastUpdate": 8000000,
                    "csv": [
                        [],
                        [7999800, 6999, 7999920, 4999],
                        [],
                        [],
                        [7999800, 7999],
                    ],
                },
                {
                    "asin": "B08N5WRWNW",
                    "currency": "EUR",
                    "domainId": 9,
                    "title": None,
                    "brand": None,
                    "csv": [None, None, None, None, None],
                },
            ]
        }

    ingested_payloads: list[dict] = []

    def fake_ingest_keepa_payload(payload, api_base_url):
        ingested_payloads.append(payload)
        return {"accepted": 1, "rejected": 0, "skipped_due_to_dedupe": 0}

    monkeypatch.setattr(ingest_keepa_bulk, "ensure_source", lambda domain_id: None)
    monkeypatch.setattr(
        ingest_keepa_bulk,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "asins": ["B09G9FPGTN", "B08N5WRWNW"],
                "asin_file": None,
                "api_base_url": "http://app:8000",
                "domain_id": 9,
            },
        )(),
    )
    monkeypatch.setattr(ingest_keepa_bulk, "fetch_batch", fake_fetch_batch)
    monkeypatch.setattr(ingest_keepa_bulk, "ingest_keepa_payload", fake_ingest_keepa_payload)

    exit_code = ingest_keepa_bulk.main()

    captured = capsys.readouterr()
    posted_products = ingested_payloads[0]["products"]

    assert exit_code == 0
    assert len(posted_products) == 1
    assert posted_products[0]["asin"] == "B09G9FPGTN"
    assert '"event": "keepa_batch_preflight"' in captured.out
    assert '"batch_size": 2' in captured.out
    assert '"total_batches": 1' in captured.out
    assert '"requested_asin": "B08N5WRWNW"' in captured.out
    assert '"outcome": "valid_but_incomplete"' in captured.out
    assert '"reason": "missing_title"' in captured.out
    assert '"total_fetched_products": 2' in captured.out
    assert '"total_posted_products": 1' in captured.out
    assert '"total_skipped_products": 1' in captured.out
    assert '"keepa_outcome_counts"' in captured.out


def test_bulk_script_reports_input_curation_issues(monkeypatch, tmp_path: Path, capsys) -> None:
    asin_file = tmp_path / "keepa_input.txt"
    asin_file.write_text(
        "\n".join(
            [
                "B09G9FPGTN",
                "https://www.amazon.es/dp/B09G9FPGTN",
                "https://www.amazon.es/dp/B08N5WRWNW",
                "not-an-asin",
            ]
        )
    )

    async def fake_fetch_batch(asins, *, domain_id):
        return {
            "products": [
                {
                    "asin": "B09G9FPGTN",
                    "domainId": 9,
                    "title": "Echo Dot 5th Gen",
                    "csv": [
                        [],
                        [7999800, 6999, 7999920, 4999],
                    ],
                },
                {
                    "asin": "B08N5WRWNW",
                    "domainId": 9,
                    "title": "Kindle",
                    "csv": [
                        [],
                        [7999800, 8999, 7999920, 7999],
                    ],
                },
            ]
        }

    ingested_payloads: list[dict] = []

    def fake_ingest_keepa_payload(payload, api_base_url):
        ingested_payloads.append(payload)
        return {"accepted": 2, "rejected": 0, "skipped_due_to_dedupe": 0}

    monkeypatch.setattr(ingest_keepa_bulk, "ensure_source", lambda domain_id: None)
    monkeypatch.setattr(
        ingest_keepa_bulk,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {"asins": [], "asin_file": str(asin_file), "api_base_url": "http://app:8000", "domain_id": 9},
        )(),
    )
    monkeypatch.setattr(ingest_keepa_bulk, "fetch_batch", fake_fetch_batch)
    monkeypatch.setattr(ingest_keepa_bulk, "ingest_keepa_payload", fake_ingest_keepa_payload)

    exit_code = ingest_keepa_bulk.main()

    captured = capsys.readouterr()

    assert exit_code == 0
    assert len(ingested_payloads[0]["products"]) == 2
    assert '"issue_counts_by_outcome": {"duplicate_requested_input": 1, "invalid_requested_input": 1}' in captured.out
    assert '"reason": "duplicate_asin"' in captured.out
    assert '"reason": "invalid_asin_or_amazon_url"' in captured.out
    assert '"accepted_asin_count": 2' in captured.out


def test_chunked_rebalances_small_tail_batches() -> None:
    values = [f"B0TEST{i:04d}" for i in range(25)]

    batches = ingest_keepa_bulk.chunked(values, 20)

    assert len(batches) == 2
    assert [len(batch) for batch in batches] == [13, 12]


def test_bulk_script_reports_batch_stats_for_multiple_batches(monkeypatch, capsys) -> None:
    fetch_calls: list[list[str]] = []

    async def fake_fetch_batch(asins, *, domain_id):
        fetch_calls.append(list(asins))
        return {
            "products": [
                {
                    "asin": asin,
                    "domainId": 9,
                    "title": f"Product {asin}",
                    "csv": [
                        [],
                        [7999800, 6999, 7999920, 4999],
                    ],
                }
                for asin in asins
            ]
        }

    def fake_ingest_keepa_payload(payload, api_base_url):
        return {"accepted": len(payload["products"]), "rejected": 0, "skipped_due_to_dedupe": 0}

    asins = [f"B0TEST{i:04d}" for i in range(25)]

    monkeypatch.setattr(ingest_keepa_bulk, "ensure_source", lambda domain_id: None)
    monkeypatch.setattr(
        ingest_keepa_bulk,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {"asins": asins, "asin_file": None, "api_base_url": "http://app:8000", "domain_id": 9},
        )(),
    )
    monkeypatch.setattr(ingest_keepa_bulk, "fetch_batch", fake_fetch_batch)
    monkeypatch.setattr(ingest_keepa_bulk, "ingest_keepa_payload", fake_ingest_keepa_payload)

    exit_code = ingest_keepa_bulk.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert [len(batch) for batch in fetch_calls] == [13, 12]
    assert '"event": "keepa_batch_plan"' in captured.out
    assert '"batch_size": 20' in captured.out
    assert '"total_batches": 2' in captured.out
    assert '"batch_sizes": [13, 12]' in captured.out


def test_load_asins_prefers_cli_then_file_then_defaults(tmp_path: Path) -> None:
    asin_file = tmp_path / "keepa_asins.txt"
    asin_file.write_text("b09b8v1lz3\nB09B94956P\n")

    cli_args = type(
        "Args",
        (),
        {"asins": ["b0cust1234"], "asin_file": str(asin_file), "api_base_url": "http://app:8000", "domain_id": 9},
    )()
    file_args = type(
        "Args",
        (),
        {"asins": [], "asin_file": str(asin_file), "api_base_url": "http://app:8000", "domain_id": 9},
    )()
    default_args = type(
        "Args",
        (),
        {"asins": [], "asin_file": None, "api_base_url": "http://app:8000", "domain_id": 9},
    )()

    assert ingest_keepa_bulk.load_asins(cli_args) == ["B0CUST1234"]
    assert ingest_keepa_bulk.load_asins(file_args) == ["B09B8V1LZ3", "B09B94956P"]
    assert ingest_keepa_bulk.load_asins(default_args) == ingest_keepa_bulk.DEFAULT_ASINS


def test_load_asins_supports_urls_comments_and_csv_tokens(tmp_path: Path) -> None:
    asin_file = tmp_path / "keepa_asins.txt"
    asin_file.write_text(
        "\n".join(
            [
                "# starter list",
                "B09B8V1LZ3, https://www.amazon.es/dp/B09B94956P",
                "invalid-value",
            ]
        )
    )

    args = type(
        "Args",
        (),
        {"asins": [], "asin_file": str(asin_file), "api_base_url": "http://app:8000", "domain_id": 9},
    )()

    assert ingest_keepa_bulk.load_asins(args) == ["B09B8V1LZ3", "B09B94956P"]
