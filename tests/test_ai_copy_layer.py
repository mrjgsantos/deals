from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal

import pytest

from app.ai.prompt_builder import build_copy_prompt
from app.ai.response_parser import parse_copy_response
from app.ai.schemas import DealCopyOutput, StructuredDealCopyInput
from app.ai.service import sanitize_for_json
from app.ai.validator import validate_copy_output


def make_input(**overrides) -> StructuredDealCopyInput:
    data = {
        "deal_id": "00000000-0000-0000-0000-000000000001",
        "product_name": "Royal Canin Mini Adult 2x8kg",
        "merchant_name": "Example Store",
        "brand": "Royal Canin",
        "category": "Pet Food",
        "current_price": Decimal("59.99"),
        "previous_price": Decimal("79.99"),
        "currency": "EUR",
        "savings_amount": Decimal("20.00"),
        "savings_percent": Decimal("25.00"),
        "quality_score": 88,
        "business_score": 20,
        "promotable": True,
        "fake_discount": False,
        "days_at_current_price": 2,
        "avg_30d": Decimal("74.99"),
        "avg_90d": Decimal("76.49"),
        "min_90d": Decimal("59.99"),
        "all_time_min": Decimal("59.99"),
        "variant_summary": "2-pack, 8kg bags",
    }
    data.update(overrides)
    return StructuredDealCopyInput(**data)


def test_prompt_builder_uses_structured_input_only() -> None:
    prompt = build_copy_prompt(make_input())

    assert "INPUT_JSON" in prompt
    assert "Royal Canin Mini Adult 2x8kg" in prompt
    assert "raw_payload" not in prompt
    assert "source junk" not in prompt


def test_response_parser_reads_json_output() -> None:
    parsed = parse_copy_response(
        json.dumps(
            {
                "title": "Royal Canin Mini Adult 2x8kg for EUR 59.99",
                "summary": "EUR 59.99 at Example Store. Matches the observed 90-day low.",
                "verdict": "strong_value",
                "tags": ["pet-food", "dog-food", "value"],
            }
        )
    )

    assert parsed.title == "Royal Canin Mini Adult 2x8kg for EUR 59.99"
    assert parsed.verdict == "strong_value"


def test_validator_accepts_supported_copy() -> None:
    validated = validate_copy_output(
        DealCopyOutput(
            title="Royal Canin Mini Adult 2x8kg for EUR 59.99",
            summary="EUR 59.99 at Example Store. This matches the observed 90-day low.",
            verdict="strong_value",
            tags=["pet-food", "dog-food", "value"],
        ),
        make_input(),
    )

    assert validated.output.verdict == "strong_value"


def test_validator_rejects_marketing_fluff() -> None:
    with pytest.raises(ValueError, match="unsupported claim detected"):
        validate_copy_output(
            DealCopyOutput(
                title="Unbeatable deal on Royal Canin",
                summary="Best deal with free shipping. Hurry before it sells out.",
                verdict="strong_value",
                tags=["pet-food"],
            ),
            make_input(),
        )


def test_validator_rejects_inconsistent_percent_claim() -> None:
    with pytest.raises(ValueError, match="percentage claim inconsistent"):
        validate_copy_output(
            DealCopyOutput(
                title="Royal Canin Mini Adult 2x8kg for EUR 59.99",
                summary="Now 40% off at Example Store.",
                verdict="strong_value",
                tags=["pet-food", "value"],
            ),
            make_input(),
        )


def test_validator_rejects_workflow_decision_language() -> None:
    with pytest.raises(ValueError, match="workflow decision language"):
        validate_copy_output(
            DealCopyOutput(
                title="Royal Canin Mini Adult 2x8kg for EUR 59.99",
                summary="Reject this deal because the discount is weak.",
                verdict="weak_value",
                tags=["pet-food", "dry-food"],
            ),
            make_input(),
        )


def test_validator_requires_not_supported_verdict_for_fake_discount() -> None:
    with pytest.raises(ValueError, match="fake discount copy must use not_supported verdict"):
        validate_copy_output(
            DealCopyOutput(
                title="Royal Canin Mini Adult 2x8kg for EUR 59.99",
                summary="EUR 59.99 at Example Store.",
                verdict="fair_price",
                tags=["pet-food"],
            ),
            make_input(fake_discount=True, promotable=False),
        )


# --- sanitize_for_json ---


def test_sanitize_for_json_converts_top_level_decimal() -> None:
    assert sanitize_for_json(Decimal("59.99")) == "59.99"


def test_sanitize_for_json_converts_decimal_in_dict() -> None:
    result = sanitize_for_json({"price": Decimal("59.99"), "label": "sale"})
    assert result == {"price": "59.99", "label": "sale"}


def test_sanitize_for_json_converts_decimal_in_list() -> None:
    result = sanitize_for_json([Decimal("10.00"), Decimal("20.50"), "unchanged"])
    assert result == ["10.00", "20.50", "unchanged"]


def test_sanitize_for_json_handles_nested_structures() -> None:
    obj = {
        "prices": [Decimal("59.99"), Decimal("79.99")],
        "meta": {"avg_30d": Decimal("74.99"), "label": "deal"},
    }
    result = sanitize_for_json(obj)
    assert result == {
        "prices": ["59.99", "79.99"],
        "meta": {"avg_30d": "74.99", "label": "deal"},
    }


def test_sanitize_for_json_preserves_none_and_primitives() -> None:
    obj = {"a": None, "b": 42, "c": True, "d": "text"}
    assert sanitize_for_json(obj) == obj


def test_sanitize_for_json_on_ai_draft_input_payload_is_json_serializable() -> None:
    # Mirrors exactly what generate_and_persist writes to metadata_json.
    # If any Decimal slips through, json.dumps raises TypeError.
    payload = sanitize_for_json({
        "input": asdict(make_input()),
        "warnings": [],
    })
    # Must not raise
    serialized = json.dumps(payload)
    loaded = json.loads(serialized)
    assert loaded["input"]["current_price"] == "59.99"
    assert loaded["input"]["savings_percent"] == "25.00"
    assert loaded["input"]["avg_30d"] == "74.99"
