from __future__ import annotations

from app.integrations.keepa_curation import (
    curate_asin_candidates,
    extract_asin_candidates_from_text,
    preflight_keepa_batch_for_bulk_ingest,
)


def test_extract_asin_candidates_from_text_supports_json_and_raw_tokens() -> None:
    assert extract_asin_candidates_from_text('["B09B8V1LZ3", "https://www.amazon.es/dp/B09B94956P"]') == [
        "B09B8V1LZ3",
        "https://www.amazon.es/dp/B09B94956P",
    ]
    assert extract_asin_candidates_from_text(
        "# comment\nB09B8V1LZ3, https://www.amazon.es/dp/B09B94956P\nB08N5WRWNW"
    ) == [
        "B09B8V1LZ3",
        "https://www.amazon.es/dp/B09B94956P",
        "B08N5WRWNW",
    ]


def test_curate_asin_candidates_normalizes_urls_and_reports_invalids() -> None:
    curated = curate_asin_candidates(
        [
            "b09b8v1lz3",
            "https://www.amazon.es/dp/B09B8V1LZ3",
            "https://www.amazon.es/dp/B09B94956P",
            "invalid-value",
        ],
        source="file",
    )

    assert curated.accepted_asins == ["B09B8V1LZ3", "B09B94956P"]
    assert curated.counts_by_outcome == {
        "duplicate_requested_input": 1,
        "invalid_requested_input": 1,
    }
    assert curated.counts_by_reason == {
        "duplicate_asin": 1,
        "invalid_asin_or_amazon_url": 1,
    }


def test_preflight_keepa_batch_classifies_payload_outcomes() -> None:
    payload = {
        "products": [
            {
                "asin": "B09VALID01",
                "domainId": 9,
                "title": "Valid ES product",
                "csv": [
                    [],
                    [7999800, 6999, 7999920, 4999],
                ],
            },
            {
                "asin": "B09INCOMP1",
                "domainId": 9,
                "title": "",
                "csv": [
                    [],
                    [7999800, 6999, 7999920, 4999],
                ],
            },
            {
                "asin": "B09WRONG01",
                "domainId": 1,
                "title": "Wrong marketplace product",
                "csv": [
                    [],
                    [7999800, 6999, 7999920, 4999],
                ],
            },
            {
                "asin": "B09VALID01",
                "domainId": 9,
                "title": "Duplicate payload copy",
                "csv": [
                    [],
                    [7999800, 6999, 7999920, 4999],
                ],
            },
            {
                "asin": "B09EXTRA01",
                "domainId": 9,
                "title": "Unexpected extra product",
                "csv": [
                    [],
                    [7999800, 6999, 7999920, 4999],
                ],
            },
            {
                "asin": "",
                "domainId": 9,
                "title": "Broken payload product",
            },
        ]
    }

    result = preflight_keepa_batch_for_bulk_ingest(
        payload,
        requested_asins=["B09VALID01", "B09INCOMP1", "B09WRONG01", "B09MISS001"],
        domain_id=9,
    )

    posted_products = result.payload["products"]

    assert result.fetched_products == 6
    assert [product["asin"] for product in posted_products] == ["B09VALID01"]
    assert result.counts_by_outcome == {
        "duplicate_payload_product": 1,
        "invalid_keepa_payload_product": 1,
        "not_found": 1,
        "unexpected_payload_product": 1,
        "valid_and_enrichable": 1,
        "valid_but_incomplete": 1,
        "wrong_marketplace": 1,
    }
    assert any(outcome.reason == "missing_title" for outcome in result.outcomes)
    assert any(outcome.reason == "requested_asin_not_returned" for outcome in result.outcomes)
    assert any(outcome.reason == "keepa_returned_duplicate_asin" for outcome in result.outcomes)
    assert any(outcome.reason == "returned_asin_not_requested" for outcome in result.outcomes)
