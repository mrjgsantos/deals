from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.enums import AvailabilityStatus
from app.ingestion.exceptions import RecordRejectedError
from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.schemas import ParsedSourceRecord
from app.matching.feature_extraction import extract_title_normalization_features


def make_parsed_record(**overrides) -> ParsedSourceRecord:
    payload = {
        "external_id": "sku-1",
        "product_url": "https://example.com/p/1",
        "title": "Sample Product",
        "brand": None,
        "category": "Electronics",
        "description": "Sample",
        "image_url": "https://example.com/i.jpg",
        "merchant_name": "Example Store",
        "currency": "EUR",
        "current_price": Decimal("99.99"),
        "availability_status": AvailabilityStatus.IN_STOCK,
        "source_attributes": {},
        "raw_payload": {},
    }
    payload.update(overrides)
    return ParsedSourceRecord(**payload)


def test_extracts_iphone_style_title_features_conservatively() -> None:
    features = extract_title_normalization_features("iPhone 15 128 GB Black")

    assert features.normalized_title == "iphone 15 128 gb black"
    assert features.normalized_brand is None
    assert features.normalized_model == "iphone-15"
    assert features.normalized_color == "black"
    assert features.normalized_storage == "128gb"
    assert features.normalized_pack_count is None


def test_extracts_pack_count_from_common_patterns() -> None:
    features = extract_title_normalization_features("Dishwasher Tablets pack of 2")

    assert features.normalized_pack_count == 2


def test_keeps_ambiguous_titles_conservative() -> None:
    features = extract_title_normalization_features("Wireless Earbuds Black")

    assert features.normalized_model is None
    assert features.normalized_storage is None
    assert features.normalized_color == "black"


def test_normalizer_enriches_source_attributes_without_breaking_required_fields() -> None:
    normalizer = DefaultRecordNormalizer()

    record = make_parsed_record(
        title="iPhone 15 128 GB Black 2-pack",
        current_price=Decimal("799.00"),
    )
    normalized = normalizer.normalize(record)

    title_features = normalized.source_attributes["title_normalization"]
    assert title_features["normalized_model"] == "iphone-15"
    assert title_features["normalized_storage"] == "128gb"
    assert title_features["normalized_color"] == "black"
    assert title_features["normalized_pack_count"] == 2
    assert normalized.pack_count == 2
    assert normalized.color == "black"


def test_normalizer_keeps_required_validation_intact() -> None:
    normalizer = DefaultRecordNormalizer()

    with pytest.raises(RecordRejectedError, match="missing title"):
        normalizer.normalize(
            make_parsed_record(
                title=None,
            )
        )
