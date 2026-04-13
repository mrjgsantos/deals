from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.integrations.amazon_es_discovery import AmazonEsCandidate, AmazonEsCandidatePoolPage
from scripts import discover_amazon_asins


def _page_pool(
    *,
    source_url: str,
    source_type: str,
    candidates: list[AmazonEsCandidate],
    raw_candidate_count: int | None = None,
    page_issues: list[str] | None = None,
) -> AmazonEsCandidatePoolPage:
    return AmazonEsCandidatePoolPage(
        source_url=source_url,
        source_type=source_type,
        raw_candidate_count=raw_candidate_count if raw_candidate_count is not None else len(candidates),
        candidates=candidates,
        rejected_candidates=[],
        page_issues=list(page_issues or []),
    )


def test_discovery_script_writes_accepted_asins(monkeypatch, tmp_path: Path, capsys) -> None:
    output_file = tmp_path / "asins.txt"

    monkeypatch.setattr(
        discover_amazon_asins,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "urls": ["https://www.amazon.es/gp/bestsellers/"],
                "url_file": None,
                "max_candidates": 100,
                "max_pages": 5,
                "write_asins": str(output_file),
                "run_keepa_bulk": False,
                "api_base_url": "http://app:8000",
                "domain_id": 9,
                "show_details": False,
            },
        )(),
    )
    monkeypatch.setattr(
        discover_amazon_asins,
        "_discover_source_candidate_pages",
        lambda source_url, max_pages=5: [
            _page_pool(
                source_url=source_url,
                source_type="best_sellers",
                candidates=[
                    AmazonEsCandidate(
                        asin="B09G9FPGTN",
                        title="Echo Dot 5th Gen",
                        price_eur=Decimal("29.99"),
                        product_url="https://www.amazon.es/dp/B09G9FPGTN",
                        source_url=source_url,
                        source_type="best_sellers",
                        issues=[],
                    )
                ],
            )
        ],
    )

    exit_code = discover_amazon_asins.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert output_file.read_text() == "B09G9FPGTN\n"
    assert '"event": "amazon_es_discovery_summary"' in captured.out
    assert '"total_raw_asin_count": 1' in captured.out
    assert '"total_after_dedupe_count": 1' in captured.out
    assert '"accepted_candidate_count": 1' in captured.out
    assert '"source_raw_asin_count": 1' in captured.out
    assert '"source_unique_asin_count": 1' in captured.out
    assert '"accepted_count": 1' in captured.out
    assert '"rejection_reasons_breakdown": {}' in captured.out
    assert '"event": "amazon_es_discovery_page_summary"' in captured.out
    assert '"event": "amazon_es_discovery_asins_written"' in captured.out


def test_discovery_script_hands_off_only_filtered_accepted_asins(monkeypatch, capsys) -> None:
    handed_off: list[str] = []

    monkeypatch.setattr(
        discover_amazon_asins,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "urls": [
                    "https://www.amazon.es/gp/bestsellers/",
                    "https://www.amazon.es/gp/movers-and-shakers/",
                ],
                "url_file": None,
                "max_candidates": 100,
                "max_pages": 5,
                "write_asins": None,
                "run_keepa_bulk": True,
                "api_base_url": "http://app:8000",
                "domain_id": 9,
                "show_details": False,
            },
        )(),
    )

    def fake_discover(source_url: str, max_pages: int = 5) -> list[AmazonEsCandidatePoolPage]:
        source_type = "best_sellers" if "bestsellers" in source_url else "movers_and_shakers"
        asin = "B09G9FPGTN" if "bestsellers" in source_url else "B08N5WRWNW"
        return [
            _page_pool(
                source_url=source_url,
                source_type=source_type,
                candidates=[
                    AmazonEsCandidate(
                        asin=asin,
                        title="Sony Headphones" if "bestsellers" in source_url else "Logitech Mouse",
                        price_eur=None,
                        product_url=None,
                        source_url=source_url,
                        source_type=source_type,
                        issues=["price_missing"],
                    )
                ],
            )
        ]

    monkeypatch.setattr(discover_amazon_asins, "_discover_source_candidate_pages", fake_discover)
    monkeypatch.setattr(
        discover_amazon_asins.ingest_keepa_bulk,
        "run_bulk_ingest_for_asins",
        lambda asins, *, api_base_url, domain_id, source: handed_off.extend(asins) or 0,
    )

    exit_code = discover_amazon_asins.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert handed_off == ["B09G9FPGTN", "B08N5WRWNW"]
    assert '"accepted_candidate_count": 2' in captured.out
    assert '"accepted_price_missing_recovered_count": 2' in captured.out
    assert '"recovered_asin_count": 2' in captured.out
    assert '"recovered_asins": [' in captured.out
    assert '"accepted_count": 1' in captured.out
    assert '"rejection_reasons_breakdown": {}' in captured.out
    assert '"event": "amazon_es_discovery_keepa_handoff"' in captured.out


def test_discovery_script_dedupes_globally_before_filtering(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        discover_amazon_asins,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "urls": [
                    "https://www.amazon.es/gp/new-releases/",
                    "https://www.amazon.es/gp/most-wished-for/",
                ],
                "url_file": None,
                "max_candidates": 100,
                "max_pages": 5,
                "write_asins": None,
                "run_keepa_bulk": False,
                "api_base_url": "http://app:8000",
                "domain_id": 9,
                "show_details": False,
            },
        )(),
    )

    def fake_discover(source_url: str, max_pages: int = 5) -> list[AmazonEsCandidatePoolPage]:
        source_type = "new_releases" if "new-releases" in source_url else "most_wished_for"
        return [
            _page_pool(
                source_url=source_url,
                source_type=source_type,
                raw_candidate_count=2,
                candidates=[
                    AmazonEsCandidate(
                        asin="B09G9FPGTN",
                        title="Shared candidate",
                        price_eur=Decimal("29.99"),
                        product_url=source_url,
                        source_url=source_url,
                        source_type=source_type,
                        issues=[],
                    ),
                    AmazonEsCandidate(
                        asin="B08N5WRWNW" if "new-releases" in source_url else "B0BLS3K8DT",
                        title="Unique candidate",
                        price_eur=Decimal("39.99"),
                        product_url=source_url,
                        source_url=source_url,
                        source_type=source_type,
                        issues=[],
                    ),
                ],
            )
        ]

    monkeypatch.setattr(discover_amazon_asins, "_discover_source_candidate_pages", fake_discover)

    exit_code = discover_amazon_asins.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"total_raw_asin_count": 4' in captured.out
    assert '"total_after_dedupe_count": 3' in captured.out
    assert '"accepted_candidate_count": 3' in captured.out
    assert '"source_raw_asin_count": 2' in captured.out
    assert '"source_unique_asin_count": 2' in captured.out
    assert '"accepted_count": 2' in captured.out
    assert '"source_type": "new_releases"' in captured.out
    assert '"source_type": "most_wished_for"' in captured.out


def test_discovery_script_reports_borderline_counts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        discover_amazon_asins,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "urls": ["https://www.amazon.es/gp/bestsellers/"],
                "url_file": None,
                "max_candidates": 100,
                "max_pages": 5,
                "write_asins": None,
                "run_keepa_bulk": False,
                "api_base_url": "http://app:8000",
                "domain_id": 9,
                "show_details": False,
            },
        )(),
    )
    monkeypatch.setattr(
        discover_amazon_asins,
        "_discover_source_candidate_pages",
        lambda source_url, max_pages=5: [
            _page_pool(
                source_url=source_url,
                source_type="best_sellers",
                raw_candidate_count=3,
                candidates=[
                    AmazonEsCandidate(
                        asin="B09G9FPGTN",
                        title="Standard",
                        price_eur=Decimal("29.99"),
                        product_url=None,
                        source_url=source_url,
                        source_type="best_sellers",
                        issues=[],
                    ),
                    AmazonEsCandidate(
                        asin="B08N5WRWNW",
                        title="Borderline",
                        price_eur=Decimal("10.99"),
                        product_url=None,
                        source_url=source_url,
                        source_type="best_sellers",
                        issues=["price_missing"],
                    ),
                ],
            )
        ],
    )

    exit_code = discover_amazon_asins.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"accepted_candidate_count": 2' in captured.out
    assert '"borderline_candidate_count": 1' in captured.out
    assert '"accepted_standard_count": 1' in captured.out
    assert '"rejection_reasons_breakdown": {}' in captured.out


def test_discovery_script_respects_max_candidates_after_global_dedupe(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_discover(source_url: str, max_pages: int = 5) -> list[AmazonEsCandidatePoolPage]:
        calls.append(source_url)
        source_type = "best_sellers" if "bestsellers" in source_url else "movers_and_shakers"
        if "bestsellers" in source_url:
            candidates = [
                AmazonEsCandidate(
                    asin="B09G9FPGTN",
                    title="One",
                    price_eur=Decimal("25.99"),
                    product_url=None,
                    source_url=source_url,
                    source_type=source_type,
                    issues=[],
                ),
                AmazonEsCandidate(
                    asin="B08N5WRWNW",
                    title="Two",
                    price_eur=Decimal("35.99"),
                    product_url=None,
                    source_url=source_url,
                    source_type=source_type,
                    issues=[],
                ),
            ]
        else:
            candidates = [
                AmazonEsCandidate(
                    asin="B0BLS3K8DT",
                    title="Three",
                    price_eur=Decimal("45.99"),
                    product_url=None,
                    source_url=source_url,
                    source_type=source_type,
                    issues=[],
                )
            ]
        return [_page_pool(source_url=source_url, source_type=source_type, candidates=candidates)]

    monkeypatch.setattr(
        discover_amazon_asins,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "urls": [
                    "https://www.amazon.es/gp/bestsellers/",
                    "https://www.amazon.es/gp/movers-and-shakers/",
                ],
                "url_file": None,
                "max_candidates": 2,
                "max_pages": 5,
                "write_asins": None,
                "run_keepa_bulk": False,
                "api_base_url": "http://app:8000",
                "domain_id": 9,
                "show_details": False,
            },
        )(),
    )
    monkeypatch.setattr(discover_amazon_asins, "_discover_source_candidate_pages", fake_discover)

    exit_code = discover_amazon_asins.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [
        "https://www.amazon.es/gp/bestsellers/",
        "https://www.amazon.es/gp/movers-and-shakers/",
    ]
    assert '"total_after_dedupe_count": 3' in captured.out
    assert '"accepted_candidate_count": 2' in captured.out
    assert '"total_unique_asin_count": 2' in captured.out
    assert '"accepted_count": 2' in captured.out


def test_discovery_script_continues_when_one_source_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        discover_amazon_asins,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "urls": [
                    "https://www.amazon.es/gp/bestsellers/",
                    "https://www.amazon.es/gp/movers-and-shakers/",
                ],
                "url_file": None,
                "max_candidates": 100,
                "max_pages": 5,
                "write_asins": None,
                "run_keepa_bulk": False,
                "api_base_url": "http://app:8000",
                "domain_id": 9,
                "show_details": False,
            },
        )(),
    )

    def fake_discover(source_url: str, max_pages: int = 5) -> list[AmazonEsCandidatePoolPage]:
        if "bestsellers" in source_url:
            raise RuntimeError("temporary_amazon_failure")
        return [
            _page_pool(
                source_url=source_url,
                source_type="movers_and_shakers",
                raw_candidate_count=2,
                candidates=[
                    AmazonEsCandidate(
                        asin="B08N5WRWNW",
                        title="Logitech Mouse",
                        price_eur=Decimal("39.99"),
                        product_url=source_url,
                        source_url=source_url,
                        source_type="movers_and_shakers",
                        issues=[],
                    ),
                    AmazonEsCandidate(
                        asin="B0BLS3K8DT",
                        title="Sony Headphones",
                        price_eur=Decimal("59.99"),
                        product_url=source_url,
                        source_url=source_url,
                        source_type="movers_and_shakers",
                        issues=[],
                    ),
                ],
            )
        ]

    monkeypatch.setattr(discover_amazon_asins, "_discover_source_candidate_pages", fake_discover)

    exit_code = discover_amazon_asins.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"event": "amazon_es_discovery_source_error"' in captured.out
    assert '"temporary_amazon_failure"' in captured.out
    assert '"failed_source_count": 1' in captured.out
    assert '"accepted_candidate_count": 2' in captured.out
    assert '"quality_status": "healthy"' in captured.out


def test_discovery_script_skips_low_quality_run(monkeypatch, capsys) -> None:
    handoff_calls: list[list[str]] = []

    monkeypatch.setattr(
        discover_amazon_asins,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "urls": ["https://www.amazon.es/gp/bestsellers/"],
                "url_file": None,
                "max_candidates": 100,
                "max_pages": 5,
                "write_asins": None,
                "run_keepa_bulk": True,
                "api_base_url": "http://app:8000",
                "domain_id": 9,
                "show_details": False,
            },
        )(),
    )
    monkeypatch.setattr(
        discover_amazon_asins,
        "_discover_source_candidate_pages",
        lambda source_url, max_pages=5: [
            _page_pool(
                source_url=source_url,
                source_type="best_sellers",
                raw_candidate_count=1,
                page_issues=["missing_asin"] * 12,
                candidates=[
                    AmazonEsCandidate(
                        asin="B09G9FPGTN",
                        title="Example",
                        price_eur=Decimal("29.99"),
                        product_url=source_url,
                        source_url=source_url,
                        source_type="best_sellers",
                        issues=[],
                    )
                ],
            )
        ],
    )
    monkeypatch.setattr(
        discover_amazon_asins.ingest_keepa_bulk,
        "run_bulk_ingest_for_asins",
        lambda asins, *, api_base_url, domain_id, source: handoff_calls.append(asins) or 0,
    )

    exit_code = discover_amazon_asins.main()
    captured = capsys.readouterr()

    assert exit_code == discover_amazon_asins.LOW_QUALITY_EXIT_CODE
    assert handoff_calls == []
    assert '"quality_status": "low_quality"' in captured.out
    assert '"low_asin_extraction_rate"' in captured.out
    assert '"event": "amazon_es_discovery_run_skipped"' in captured.out
