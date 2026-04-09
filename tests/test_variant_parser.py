from app.ingestion.variant_parser import (
    detect_variant_conflicts,
    has_critical_variant_conflict,
    parse_variant_attributes,
)


def test_parse_weight_single_unit() -> None:
    result = parse_variant_attributes("Royal Canin Mini Adult 8kg")

    assert result.attributes.pack_count is None
    assert str(result.attributes.weight) == "8"
    assert result.attributes.weight_unit == "kg"
    assert result.attributes.is_bundle is False
    assert result.confidence > 0


def test_parse_pack_x_weight() -> None:
    result = parse_variant_attributes("Royal Canin Mini Adult 2x8kg")

    assert result.attributes.pack_count == 2
    assert str(result.attributes.weight) == "8"
    assert result.attributes.weight_unit == "kg"
    assert result.variant_key() == "pack:2|weight:8:kg|bundle:false"


def test_parse_size_dimension() -> None:
    result = parse_variant_attributes("Le Creuset Signature Round Dutch Oven 24cm")

    assert result.attributes.size == "24cm"
    assert result.attributes.weight is None
    assert result.attributes.volume is None


def test_parse_single_unit_phrase() -> None:
    result = parse_variant_attributes("Dishwasher Tablet single unit")

    assert result.attributes.pack_count == 1


def test_parse_pack_phrase() -> None:
    result = parse_variant_attributes("Dishwasher Tablet 3-pack")

    assert result.attributes.pack_count == 3


def test_parse_bundle_phrase() -> None:
    result = parse_variant_attributes("Camera bundle with accessory")

    assert result.attributes.is_bundle is True


def test_parse_color_and_material() -> None:
    result = parse_variant_attributes("Travel mug stainless steel black 500ml")

    assert result.attributes.material == "stainless-steel"
    assert result.attributes.color == "black"
    assert str(result.attributes.volume) == "500"
    assert result.attributes.volume_unit == "ml"


def test_critical_conflict_pack_weight() -> None:
    left = parse_variant_attributes("Royal Canin Mini Adult 8kg")
    right = parse_variant_attributes("Royal Canin Mini Adult 2x8kg")

    conflicts = detect_variant_conflicts(left, right)

    assert has_critical_variant_conflict(left, right) is True
    assert any(conflict.field == "pack_count" for conflict in conflicts)


def test_critical_conflict_size() -> None:
    left = parse_variant_attributes("Le Creuset 24cm")
    right = parse_variant_attributes("Le Creuset 28cm")

    assert has_critical_variant_conflict(left, right) is True
    assert any(conflict.field == "size" and conflict.critical for conflict in detect_variant_conflicts(left, right))


def test_critical_conflict_bundle_vs_standalone() -> None:
    left = parse_variant_attributes("Phone bundle with accessory")
    right = parse_variant_attributes("Phone standalone")

    assert has_critical_variant_conflict(left, right) is True


def test_non_critical_conflict_color() -> None:
    left = parse_variant_attributes("T-shirt red size l")
    right = parse_variant_attributes("T-shirt blue size l")

    conflicts = detect_variant_conflicts(left, right)

    assert any(conflict.field == "color" for conflict in conflicts)
    assert all(conflict.field != "size" for conflict in conflicts)
    assert has_critical_variant_conflict(left, right) is False
