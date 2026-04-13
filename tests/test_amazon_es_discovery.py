from __future__ import annotations

from decimal import Decimal

from app.integrations.amazon_es_discovery import (
    classify_amazon_es_source_type,
    discover_candidates_from_html,
    discover_pagination_urls_from_html,
    discover_source_with_pagination,
)


def test_discovery_extracts_asin_from_canonical_dp_link() -> None:
    html = """
    <div class="zg-grid-general-faceout">
      <a href="/dp/B09G9FPGTN" aria-label="Echo Dot 5th Gen">
        Echo Dot 5th Gen
      </a>
      <span>29,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.source_type == "best_sellers"
    assert result.raw_candidate_count == 1
    assert result.accepted_asins == ["B09G9FPGTN"]
    assert result.accepted_candidates[0].title == "Echo Dot 5th Gen"
    assert result.accepted_candidates[0].price_eur == Decimal("29.99")
    assert result.accepted_candidates[0].issues == []


def test_discovery_extracts_asin_from_gp_product_link() -> None:
    html = """
    <div>
      <a href="/gp/product/B08N5WRWNW" title="Kindle Paperwhite"></a>
      <span>149,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/movers-and-shakers/",
    )

    assert result.source_type == "movers_and_shakers"
    assert result.accepted_asins == ["B08N5WRWNW"]
    assert result.accepted_candidates[0].title == "Kindle Paperwhite"
    assert result.accepted_candidates[0].price_eur == Decimal("149.99")


def test_discovery_classifies_new_releases_source() -> None:
    html = """
    <div>
      <a href="/dp/B0C1234XYZ" aria-label="Smart plug WiFi">Smart plug WiFi</a>
      <span>24,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/new-releases/",
    )

    assert result.source_type == "new_releases"
    assert result.accepted_asins == ["B0C1234XYZ"]


def test_discovery_classifies_most_wished_for_source() -> None:
    html = """
    <div>
      <a href="/dp/B0C5678XYZ" aria-label="Robot aspirador">Robot aspirador</a>
      <span>199,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/most-wished-for/",
    )

    assert result.source_type == "most_wished_for"
    assert result.accepted_asins == ["B0C5678XYZ"]


def test_discovery_detects_pagination_urls_for_best_sellers() -> None:
    html = """
    <div class="zg_paginationWrapper">
      <a href="/gp/bestsellers/?pg=2">2</a>
      <a href="/gp/bestsellers/?pg=3">3</a>
    </div>
    """

    result = discover_pagination_urls_from_html(
        html,
        current_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result == [
        "https://www.amazon.es/gp/bestsellers/?pg=2",
        "https://www.amazon.es/gp/bestsellers/?pg=3",
    ]


def test_discovery_detects_pagination_urls_for_new_releases() -> None:
    html = """
    <div class="zg_paginationWrapper">
      <a href="/gp/new-releases/?pg=2">2</a>
      <a href="/gp/new-releases/?pg=3">3</a>
    </div>
    """

    result = discover_pagination_urls_from_html(
        html,
        current_url="https://www.amazon.es/gp/new-releases/",
    )

    assert result == [
        "https://www.amazon.es/gp/new-releases/?pg=2",
        "https://www.amazon.es/gp/new-releases/?pg=3",
    ]


def test_paginated_discovery_dedupes_across_pages_and_stops_when_no_new_asins(monkeypatch) -> None:
    html_by_url = {
        "https://www.amazon.es/gp/bestsellers/": """
            <a href="/dp/B09G9FPGTN" aria-label="Echo Dot">Echo Dot</a>
            <span>39,99 €</span>
            <a href="/gp/bestsellers/?pg=2">2</a>
        """,
        "https://www.amazon.es/gp/bestsellers/?pg=2": """
            <a href="/dp/B09G9FPGTN" aria-label="Echo Dot duplicate">Echo Dot duplicate</a>
            <span>39,99 €</span>
            <a href="/gp/bestsellers/?pg=3">3</a>
        """,
    }

    monkeypatch.setattr(
        "app.integrations.amazon_es_discovery.fetch_amazon_es_page",
        lambda url, **kwargs: html_by_url[url],
    )

    result = discover_source_with_pagination("https://www.amazon.es/gp/bestsellers/", max_pages=5)

    assert result.fetched_page_count == 2
    assert result.total_unique_asin_count == 1
    assert result.accepted_asins == ["B09G9FPGTN"]
    assert result.page_results[0].accepted_asins == ["B09G9FPGTN"]
    assert result.page_results[1].accepted_asins == []
    assert result.page_results[1].counts_by_reason["duplicate_asin"] == 1


def test_discovery_extracts_price_from_realistic_p13n_price_markup() -> None:
    html = """
    <div>
      <a href="/luz-led-escritorio/dp/B08CC9JM62/ref=zg_bs_c_lawn-garden_d_sccl_2">
        Luz LED de escritorio
      </a>
      <div class="a-row">
        <span class="a-size-base a-color-price">
          <span class="_cDEzb_p13n-sc-price_3mJ9Z">5,99&nbsp;€</span>
        </span>
      </div>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_candidate_count == 0
    assert result.rejected_candidate_count == 1
    assert result.rejected_candidates[0].reason == "price_below_threshold"
    assert result.rejected_candidates[0].price_eur == Decimal("5.99")


def test_discovery_extracts_price_from_whole_fraction_markup() -> None:
    html = """
    <div>
      <a href="/dp/B08QRQQ53T" aria-label="Tapo L530E"></a>
      <span class="a-price">
        <span class="a-price-whole">19</span>
        <span class="a-price-decimal">,</span>
        <span class="a-price-fraction">99</span>
        <span class="a-price-symbol">€</span>
      </span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/movers-and-shakers/",
    )

    assert result.accepted_asins == ["B08QRQQ53T"]
    assert result.accepted_candidates[0].price_eur == Decimal("19.99")


def test_discovery_ignores_offer_from_prices_when_filtering() -> None:
    html = """
    <div>
      <a href="/dp/B09B8X9RGM" aria-label="Sony WH-1000XM5">Sony WH-1000XM5</a>
      <span>3 ofertas desde <span class="p13n-sc-price">4,95&nbsp;€</span></span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_asins == ["B09B8X9RGM"]
    assert result.accepted_candidates[0].price_eur is None
    assert result.accepted_candidates[0].issues == ["price_missing_recovered"]


def test_discovery_deduplicates_repeated_asins() -> None:
    html = """
    <div>
      <a href="/dp/B09G9FPGTN" aria-label="Echo Dot 5th Gen">Echo Dot</a>
      <span>29,99 €</span>
    </div>
    <div>
      <a href="/gp/product/B09G9FPGTN" title="Echo Dot Duplicate">Echo Dot Duplicate</a>
      <span>30,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.raw_candidate_count == 2
    assert result.accepted_asins == ["B09G9FPGTN"]
    assert result.rejected_candidate_count == 1
    assert result.rejected_candidates[0].reason == "duplicate_asin"
    assert result.counts_by_reason["duplicate_asin"] == 1


def test_discovery_accepts_prices_at_new_threshold() -> None:
    html = """
    <div>
      <a href="/dp/B09B94956P" aria-label="Budget headphones">Budget headphones</a>
      <span>12,00 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/movers-and-shakers/",
    )

    assert result.accepted_asins == ["B09B94956P"]
    assert result.accepted_candidates[0].price_eur == Decimal("12.00")
    assert result.accepted_candidates[0].issues == []
    assert result.accepted_borderline_count == 0


def test_discovery_flags_borderline_prices_between_10_and_12_eur() -> None:
    html = """
    <div>
      <a href="/dp/B09B94956P" aria-label="Budget headphones">Budget headphones</a>
      <span>10,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/movers-and-shakers/",
    )

    assert result.accepted_asins == ["B09B94956P"]
    assert result.accepted_candidates[0].price_eur == Decimal("10.99")
    assert result.accepted_candidates[0].issues == ["borderline_price"]
    assert result.accepted_borderline_count == 1


def test_discovery_rejects_prices_below_10_eur() -> None:
    html = """
    <div>
      <a href="/dp/B09B94956P" aria-label="Budget headphones">Budget headphones</a>
      <span>9,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/movers-and-shakers/",
    )

    assert result.accepted_candidate_count == 0
    assert result.rejected_candidate_count == 1
    assert result.rejected_candidates[0].reason == "price_below_threshold"


def test_discovery_keeps_missing_price_candidates_with_issue() -> None:
    html = """
    <div>
      <a href="/dp/B0BLS3K8DT" aria-label="Logitech MX Master 3S">Logitech MX Master 3S</a>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_asins == ["B0BLS3K8DT"]
    assert result.accepted_candidates[0].price_eur is None
    assert result.accepted_candidates[0].issues == ["price_missing_recovered"]
    assert result.counts_by_reason["price_missing_recovered"] == 1


def test_discovery_filters_low_signal_supplement_candidates() -> None:
    html = """
    <div>
      <a href="/dp/B07M7L3J7Y" aria-label="Citrato de Magnesio 1545mg">Citrato de Magnesio 1545mg</a>
      <span>18,91 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_candidate_count == 0
    assert result.rejected_candidate_count == 1
    assert result.rejected_candidates[0].reason == "category_filtered_low_signal"
    assert result.rejected_candidates[0].price_eur == Decimal("18.91")


def test_discovery_allows_basic_apparel_candidates_after_denylist_narrowing() -> None:
    html = """
    <div>
      <a href="/camiseta-paquete-hombre/dp/B0C5D6ZDFZ" aria-label="Camiseta paquete de 5 para hombre">
        Camiseta paquete de 5 para hombre
      </a>
      <span>24,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_asins == ["B0C5D6ZDFZ"]
    assert result.accepted_candidates[0].price_eur == Decimal("24.99")


def test_discovery_does_not_overfilter_non_basic_sportswear_titles() -> None:
    html = """
    <div>
      <a href="/pantalon-corto-deportivo-hombre/dp/B06Y68XBHF" aria-label="Pantalón corto deportivo hombre">
        Pantalón corto deportivo hombre
      </a>
      <span>19,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_asins == ["B06Y68XBHF"]
    assert result.accepted_candidates[0].price_eur == Decimal("19.99")


def test_discovery_keeps_useful_electronics_candidates() -> None:
    html = """
    <div>
      <a href="/dp/B09B8X9RGM" aria-label="Echo Dot última generación">Echo Dot última generación</a>
      <span>39,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_asins == ["B09B8X9RGM"]
    assert result.accepted_candidates[0].price_eur == Decimal("39.99")
    assert result.accepted_candidates[0].issues == []


def test_discovery_recovers_limited_missing_price_candidates_with_strong_device_signal() -> None:
    html = """
    <div>
      <a href="/logitech-mx-master-3s/dp/B09B8X9RGM" aria-label="Logitech MX Master 3S">
        Logitech MX Master 3S
      </a>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_asins == ["B09B8X9RGM"]
    assert result.accepted_candidates[0].price_eur is None
    assert result.accepted_candidates[0].issues == ["price_missing_recovered"]
    assert result.accepted_price_missing_recovered_count == 1


def test_discovery_recovers_missing_price_candidate_with_electronics_category_url() -> None:
    html = """
    <div>
      <a href="/electronica/monitores/dp/B08TEST123" aria-label="Pantalla 27 pulgadas">
        Pantalla 27 pulgadas
      </a>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/new-releases/",
    )

    assert result.accepted_asins == ["B08TEST123"]
    assert result.accepted_candidates[0].issues == ["price_missing_recovered"]


def test_discovery_rejects_missing_price_noise_without_recovery() -> None:
    html = """
    <div>
      <a href="/magnesio-bisglicinato/dp/B07M7L3J7Y" aria-label="Magnesio bisglicinato">
        Magnesio bisglicinato
      </a>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_candidate_count == 0
    assert result.rejected_candidate_count == 1
    assert result.rejected_candidates[0].reason == "category_filtered_low_signal"


def test_discovery_caps_missing_price_recovery_per_source() -> None:
    product_blocks: list[str] = []
    for index in range(21):
        asin = f"B0TEST{index:04d}"
        product_blocks.append(
            f'<div><a href="/logitech-accesorio-{index}/dp/{asin}" aria-label="Logitech accesorio {index}">Logitech accesorio {index}</a></div>'
        )
    html = "\n".join(product_blocks)

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_candidate_count == 20
    assert result.accepted_price_missing_recovered_count == 20
    assert result.rejected_candidate_count == 1
    assert result.rejected_candidates[0].reason == "price_missing"


def test_discovery_ignores_non_product_links_and_marks_page_issue() -> None:
    html = """
    <div>
      <a href="/gp/help/customer/display.html">Customer help</a>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.raw_candidate_count == 0
    assert result.accepted_candidate_count == 0
    assert result.counts_by_reason["non_amazon_product_link"] == 1


def test_discovery_handles_mixed_html_fragments_safely() -> None:
    html = """
    <div data-asin="B09B8V1LZ3">
      <span aria-label="Featured product">Featured product</span>
      <span>59,95 €</span>
    </div>
    <div data-asin="BAD-ASIN">
      <a href="/gp/cart/view.html">Cart</a>
    </div>
    <div>
      <a href="/dp/B09B94956P" aria-label="Affordable earbuds">Affordable earbuds</a>
      <span>12,99 €</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/deals",
    )

    assert result.source_type == "deals"
    assert result.accepted_asins == ["B09B94956P", "B09B8V1LZ3"]
    assert result.accepted_candidates[0].price_eur == Decimal("12.99")
    assert result.accepted_candidates[1].price_eur == Decimal("59.95")
    assert result.rejected_candidates == []
    assert result.counts_by_reason["invalid_asin_pattern"] == 1
    assert result.counts_by_reason["non_amazon_product_link"] == 1


def test_discovery_prefers_richer_duplicate_metadata_for_titles_and_prices() -> None:
    html = """
    <div data-asin="B08QRQQ53T"></div>
    <div>
      <a href="/Tapo-L530E-bombilla-inteligente/dp/B08QRQQ53T/ref=zg_bs">
        Tapo L530E bombilla inteligente
      </a>
      <span class="_cDEzb_p13n-sc-price_3mJ9Z">19,99&nbsp;€</span>
    </div>
    """

    result = discover_candidates_from_html(
        html,
        source_url="https://www.amazon.es/gp/bestsellers/",
    )

    assert result.accepted_asins == ["B08QRQQ53T"]
    assert result.accepted_candidates[0].title == "Tapo L530E bombilla inteligente"
    assert result.accepted_candidates[0].price_eur == Decimal("19.99")
    assert result.rejected_candidate_count == 1
    assert result.rejected_candidates[0].reason == "duplicate_asin"


def test_classify_source_type_prioritizes_best_sellers_and_movers() -> None:
    assert classify_amazon_es_source_type("https://www.amazon.es/gp/bestsellers/") == "best_sellers"
    assert (
        classify_amazon_es_source_type("https://www.amazon.es/gp/movers-and-shakers/")
        == "movers_and_shakers"
    )
    assert classify_amazon_es_source_type("https://www.amazon.es/gp/new-releases/") == "new_releases"
    assert classify_amazon_es_source_type("https://www.amazon.es/gp/most-wished-for/") == "most_wished_for"
    assert classify_amazon_es_source_type("https://www.amazon.es/deals") == "deals"
    assert classify_amazon_es_source_type("https://www.example.com/products") == "unknown"
