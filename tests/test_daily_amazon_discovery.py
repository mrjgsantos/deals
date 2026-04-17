from __future__ import annotations

import logging
from decimal import Decimal

import pytest

from app.integrations.amazon_es_discovery import AmazonEsCandidate, AmazonEsCandidatePoolPage
from app.jobs.daily_amazon_discovery import _run_discovery


def _make_page(
    source_url: str,
    asins: list[str],
    *,
    source_type: str = "best_sellers",
) -> AmazonEsCandidatePoolPage:
    candidates = [
        AmazonEsCandidate(
            asin=asin,
            title=f"Product {asin}",
            price_eur=Decimal("19.99"),
            product_url=f"https://www.amazon.es/dp/{asin}",
            source_url=source_url,
            source_type=source_type,
            issues=[],
        )
        for asin in asins
    ]
    return AmazonEsCandidatePoolPage(
        source_url=source_url,
        source_type=source_type,
        raw_candidate_count=len(candidates),
        candidates=candidates,
        rejected_candidates=[],
        page_issues=[],
    )


def test_run_discovery_fetches_single_page_when_max_pages_is_one(monkeypatch) -> None:
    """With max_pages_per_url=1, only the initial URL is fetched (no pagination follow-through)."""
    source_url = "https://www.amazon.es/gp/bestsellers/kitchen/"
    page1 = _make_page(source_url, ["B001ASIN01", "B001ASIN02"])

    fetch_calls: list[str] = []

    def fake_fetch(url: str) -> str:
        fetch_calls.append(url)
        return "<html>page</html>"

    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.fetch_amazon_es_page", fake_fetch
    )
    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.discover_candidate_pool_from_html",
        lambda html, *, source_url: page1,
    )
    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.discover_pagination_urls_from_html",
        lambda html, *, current_url: ["https://www.amazon.es/gp/bestsellers/kitchen/?pg=2"],
    )

    candidates, stats = _run_discovery(
        [source_url],
        logging.getLogger("test"),
        max_candidates=100,
        max_pages_per_url=1,
    )

    assert fetch_calls == [source_url]
    assert stats["pages_fetched"] == 1
    assert [c.asin for c in candidates] == ["B001ASIN01", "B001ASIN02"]


def test_run_discovery_follows_pagination_when_max_pages_is_two(monkeypatch) -> None:
    """With max_pages_per_url=2, fetches page 1 and follows the discovered page 2 URL."""
    source_url = "https://www.amazon.es/gp/bestsellers/kitchen/"
    page2_url = "https://www.amazon.es/gp/bestsellers/kitchen/?pg=2"

    page1 = _make_page(source_url, ["B001ASIN01", "B001ASIN02"])
    page2 = _make_page(page2_url, ["B001ASIN03", "B001ASIN04"])

    fetch_calls: list[str] = []

    def fake_fetch(url: str) -> str:
        fetch_calls.append(url)
        return "<html>page</html>"

    def fake_pool_v2(html: str, *, source_url: str) -> AmazonEsCandidatePoolPage:
        if "pg=2" in source_url:
            return page2
        return page1

    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.fetch_amazon_es_page", fake_fetch
    )
    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.discover_candidate_pool_from_html",
        fake_pool_v2,
    )
    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.discover_pagination_urls_from_html",
        lambda html, *, current_url: [page2_url] if "pg=2" not in current_url else [],
    )

    candidates, stats = _run_discovery(
        [source_url],
        logging.getLogger("test"),
        max_candidates=100,
        max_pages_per_url=2,
    )

    assert fetch_calls == [source_url, page2_url]
    assert stats["pages_fetched"] == 2
    assert {c.asin for c in candidates} == {"B001ASIN01", "B001ASIN02", "B001ASIN03", "B001ASIN04"}


def test_run_discovery_does_not_revisit_already_fetched_url(monkeypatch) -> None:
    """If pagination returns the current URL again, it is not fetched twice."""
    source_url = "https://www.amazon.es/gp/bestsellers/kitchen/"
    page1 = _make_page(source_url, ["B001ASIN01"])

    fetch_calls: list[str] = []

    def fake_fetch(url: str) -> str:
        fetch_calls.append(url)
        return "<html>page</html>"

    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.fetch_amazon_es_page", fake_fetch
    )
    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.discover_candidate_pool_from_html",
        lambda html, *, source_url: page1,
    )
    monkeypatch.setattr(
        "app.jobs.daily_amazon_discovery.discover_pagination_urls_from_html",
        lambda html, *, current_url: [source_url],  # returns the same URL
    )

    candidates, stats = _run_discovery(
        [source_url],
        logging.getLogger("test"),
        max_candidates=100,
        max_pages_per_url=2,
    )

    assert fetch_calls == [source_url]
    assert stats["pages_fetched"] == 1
