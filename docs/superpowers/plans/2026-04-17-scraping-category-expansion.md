# Scraping Category Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand product ingestion from 4 tech-only Amazon.es categories to 18 diverse categories with automatic top-50 pagination, and replace 3 tech-biased SerpApi queries with ~50 Portuguese-language queries across all categories.

**Architecture:** Data files (`amazon_es_discovery_urls.txt`, `serpapi_queries.json`) drive what gets scraped with zero code changes for categories/queries. The only code change is adding automatic pagination to `daily_amazon_discovery.py`'s `_run_discovery()` — it gains a `max_pages_per_url` parameter and follows `discover_pagination_urls_from_html` (already exists in the integration module) to fetch up to 2 pages per category URL.

**Tech Stack:** Python, existing `app.integrations.amazon_es_discovery` helpers (`discover_pagination_urls_from_html`, `fetch_amazon_es_page`, `discover_candidate_pool_from_html`), pytest, pydantic-settings.

---

## Files

| File | Change |
|---|---|
| `data/amazon_es_discovery_urls.txt` | Add 14 new category URLs |
| `data/serpapi_queries.json` | Replace 3 queries with 50 PT-language queries |
| `app/core/config.py` | Add `amazon_discovery_max_pages_per_url: int = 2`; raise `amazon_discovery_max_candidates` to `700` |
| `app/jobs/daily_amazon_discovery.py` | Import `discover_pagination_urls_from_html`; add pagination loop to `_run_discovery()`; pass new setting in `main()` |
| `tests/test_daily_amazon_discovery.py` | New: tests for pagination behaviour in `_run_discovery()` |

---

## Task 1: Expand Amazon.es category URLs

**Files:**
- Modify: `data/amazon_es_discovery_urls.txt`

- [ ] **Step 1: Replace the file content**

Replace the full contents of `data/amazon_es_discovery_urls.txt` with:

```
# Amazon.es category pages used for daily ASIN discovery.
# One URL per line. Lines starting with # are ignored.
#
# Fetched once per day by app/jobs/daily_amazon_discovery.py.
# Accepted ASINs are enriched via Keepa and ingested as amazon-keepa source records.
# Add or remove URLs here without any code changes.

# --- Tecnología ---
# Electronics best sellers — primary signal source
https://www.amazon.es/gp/bestsellers/electronics/

# Computing best sellers
https://www.amazon.es/gp/bestsellers/computers/

# Mobile phones & accessories
https://www.amazon.es/gp/bestsellers/ce-de-ec/

# Movers and shakers (fast-rising products)
https://www.amazon.es/gp/movers-and-shakers/electronics/

# --- Hogar y cocina ---
https://www.amazon.es/gp/bestsellers/kitchen/

# --- Moda ---
https://www.amazon.es/gp/bestsellers/apparel/

# --- Belleza y cuidado personal ---
https://www.amazon.es/gp/bestsellers/beauty/

# --- Salud y cuidado del hogar ---
https://www.amazon.es/gp/bestsellers/hpc/

# --- Deporte y aire libre ---
https://www.amazon.es/gp/bestsellers/sporting-goods/

# --- Juguetes y juegos ---
https://www.amazon.es/gp/bestsellers/toys/

# --- Alimentación y bebidas ---
https://www.amazon.es/gp/bestsellers/grocery/

# --- Mascotas ---
https://www.amazon.es/gp/bestsellers/pet-supplies/

# --- Bebé ---
https://www.amazon.es/gp/bestsellers/baby/

# --- Coche y moto ---
https://www.amazon.es/gp/bestsellers/automotive/

# --- Videojuegos ---
https://www.amazon.es/gp/bestsellers/videogames/

# --- Bricolaje y herramientas ---
https://www.amazon.es/gp/bestsellers/tools/

# --- Jardín ---
https://www.amazon.es/gp/bestsellers/lawn-garden/

# --- Libros ---
https://www.amazon.es/gp/bestsellers/books/
```

- [ ] **Step 2: Verify the file loads correctly (dry-run)**

```bash
python -c "
lines = open('data/amazon_es_discovery_urls.txt').readlines()
urls = [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]
print(f'{len(urls)} URLs loaded')
for u in urls: print(' ', u)
"
```

Expected output: `18 URLs loaded` followed by all 18 URLs.

- [ ] **Step 3: Commit**

```bash
git add data/amazon_es_discovery_urls.txt
git commit -m "data: expand amazon.es discovery to 18 categories"
```

---

## Task 2: Expand SerpApi queries to Portuguese

**Files:**
- Modify: `data/serpapi_queries.json`

- [ ] **Step 1: Replace the file content**

Replace the full contents of `data/serpapi_queries.json` with:

```json
[
  {"query": "fritadeira de ar sem óleo", "limit": 5, "enabled": true},
  {"query": "máquina de café cápsulas", "limit": 5, "enabled": true},
  {"query": "robot de cozinha", "limit": 5, "enabled": true},
  {"query": "aspirador robot", "limit": 5, "enabled": true},
  {"query": "purificador de ar", "limit": 5, "enabled": true},
  {"query": "panela de pressão elétrica", "limit": 5, "enabled": true},
  {"query": "máquina de lavar loiça", "limit": 5, "enabled": true},
  {"query": "ténis running mulher", "limit": 5, "enabled": true},
  {"query": "mochila escolar", "limit": 5, "enabled": true},
  {"query": "smartwatch desporto", "limit": 5, "enabled": true},
  {"query": "creme hidratante rosto", "limit": 5, "enabled": true},
  {"query": "sérum vitamina c", "limit": 5, "enabled": true},
  {"query": "champô anticaspa", "limit": 5, "enabled": true},
  {"query": "perfume feminino popular", "limit": 5, "enabled": true},
  {"query": "proteína whey", "limit": 5, "enabled": true},
  {"query": "suplemento magnésio", "limit": 5, "enabled": true},
  {"query": "vitamina d3", "limit": 5, "enabled": true},
  {"query": "tensiómetro de braço digital", "limit": 5, "enabled": true},
  {"query": "pesos kettlebell", "limit": 5, "enabled": true},
  {"query": "tapete yoga", "limit": 5, "enabled": true},
  {"query": "bicicleta estática", "limit": 5, "enabled": true},
  {"query": "corda de saltar", "limit": 5, "enabled": true},
  {"query": "lego criativo", "limit": 5, "enabled": true},
  {"query": "boneca barbie", "limit": 5, "enabled": true},
  {"query": "jogo de tabuleiro família", "limit": 5, "enabled": true},
  {"query": "drone para crianças", "limit": 5, "enabled": true},
  {"query": "café em grão", "limit": 5, "enabled": true},
  {"query": "azeite extra virgem", "limit": 5, "enabled": true},
  {"query": "proteína vegetal pó", "limit": 5, "enabled": true},
  {"query": "chá verde matcha", "limit": 5, "enabled": true},
  {"query": "ração gato adulto", "limit": 5, "enabled": true},
  {"query": "ração cão adulto", "limit": 5, "enabled": true},
  {"query": "arranhador gato", "limit": 5, "enabled": true},
  {"query": "cama para cão", "limit": 5, "enabled": true},
  {"query": "carrinho de bebé", "limit": 5, "enabled": true},
  {"query": "monitor de bebé vídeo", "limit": 5, "enabled": true},
  {"query": "fraldas recém-nascido", "limit": 5, "enabled": true},
  {"query": "dashcam 4k", "limit": 5, "enabled": true},
  {"query": "aspirador carro sem fio", "limit": 5, "enabled": true},
  {"query": "carregador sem fios carro", "limit": 5, "enabled": true},
  {"query": "comando ps5", "limit": 5, "enabled": true},
  {"query": "headset gaming", "limit": 5, "enabled": true},
  {"query": "berbequim sem fio", "limit": 5, "enabled": true},
  {"query": "nível laser", "limit": 5, "enabled": true},
  {"query": "mangueira jardim extensível", "limit": 5, "enabled": true},
  {"query": "kit jardinagem", "limit": 5, "enabled": true},
  {"query": "romance bestseller português", "limit": 5, "enabled": true},
  {"query": "livro autoajuda", "limit": 5, "enabled": true},
  {"query": "auriculares bluetooth", "limit": 5, "enabled": true},
  {"query": "powerbank portátil", "limit": 5, "enabled": true}
]
```

- [ ] **Step 2: Verify it parses correctly**

```bash
python -c "
import json
queries = json.load(open('data/serpapi_queries.json'))
enabled = [q for q in queries if q.get('enabled')]
print(f'{len(queries)} total queries, {len(enabled)} enabled')
"
```

Expected: `50 total queries, 50 enabled`

- [ ] **Step 3: Commit**

```bash
git add data/serpapi_queries.json
git commit -m "data: replace serpapi queries with 50 portuguese-language queries across all categories"
```

---

## Task 3: Update config settings

**Files:**
- Modify: `app/core/config.py:55-57`

- [ ] **Step 1: Update the three settings**

In `app/core/config.py`, find the block:

```python
    amazon_discovery_urls_file: str = "data/amazon_es_discovery_urls.txt"
    amazon_discovery_max_candidates: int = 60
    amazon_discovery_domain_id: int = 9  # 9 = amazon.es
```

Replace with:

```python
    amazon_discovery_urls_file: str = "data/amazon_es_discovery_urls.txt"
    amazon_discovery_max_candidates: int = 700
    amazon_discovery_max_pages_per_url: int = 2
    amazon_discovery_domain_id: int = 9  # 9 = amazon.es
```

- [ ] **Step 2: Verify settings load**

```bash
docker compose run --rm app python -c "
from app.core.config import settings
print('max_candidates:', settings.amazon_discovery_max_candidates)
print('max_pages_per_url:', settings.amazon_discovery_max_pages_per_url)
print('domain_id:', settings.amazon_discovery_domain_id)
"
```

Expected:
```
max_candidates: 700
max_pages_per_url: 2
domain_id: 9
```

- [ ] **Step 3: Commit**

```bash
git add app/core/config.py
git commit -m "config: raise amazon discovery candidate limit to 700, add max_pages_per_url=2"
```

---

## Task 4: Add pagination to daily_amazon_discovery job (TDD)

**Files:**
- Modify: `app/jobs/daily_amazon_discovery.py`
- Create: `tests/test_daily_amazon_discovery.py`

### Step 1: Write the failing tests

- [ ] **Create `tests/test_daily_amazon_discovery.py`**

```python
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

    def fake_pool(html: str, *, source_url: str) -> AmazonEsCandidatePoolPage:
        return page1 if source_url == source_url and "pg=2" not in source_url else page2

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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
docker compose run --rm app pytest -q tests/test_daily_amazon_discovery.py
```

Expected: 3 errors — `_run_discovery() got an unexpected keyword argument 'max_pages_per_url'` (or similar), plus `discover_pagination_urls_from_html` not importable from the job module.

### Step 2: Implement the changes

- [ ] **Step 3: Update imports in `app/jobs/daily_amazon_discovery.py`**

Find:
```python
from app.integrations.amazon_es_discovery import (
    AmazonEsCandidate,
    AmazonEsCandidatePoolPage,
    assess_discovery_quality,
    discover_candidate_pool_from_html,
    fetch_amazon_es_page,
    filter_candidate_pool,
)
```

Replace with:
```python
from app.integrations.amazon_es_discovery import (
    AmazonEsCandidate,
    AmazonEsCandidatePoolPage,
    assess_discovery_quality,
    discover_candidate_pool_from_html,
    discover_pagination_urls_from_html,
    fetch_amazon_es_page,
    filter_candidate_pool,
)
```

- [ ] **Step 4: Update `_run_discovery()` signature and body**

Find the entire `_run_discovery` function (lines ~125–192) and replace it with:

```python
def _run_discovery(
    source_urls: list[str],
    logger: logging.Logger,
    *,
    max_candidates: int,
    max_pages_per_url: int = 2,
) -> tuple[list[AmazonEsCandidate], dict[str, int]]:
    pages: list[AmazonEsCandidatePoolPage] = []
    raw_count = 0

    for source_url in source_urls:
        url_queue: list[str] = [source_url]
        visited: set[str] = set()
        pages_fetched_for_source = 0

        while url_queue and pages_fetched_for_source < max_pages_per_url:
            current_url = url_queue.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                html = fetch_amazon_es_page(current_url)
                page = discover_candidate_pool_from_html(html, source_url=current_url)
                pages.append(page)
                raw_count += page.raw_candidate_count
                pages_fetched_for_source += 1
                logger.info(
                    "amazon_discovery_page_fetched url=%s source_type=%s raw=%s candidates=%s issues=%s",
                    current_url,
                    page.source_type,
                    page.raw_candidate_count,
                    page.candidate_count,
                    page.page_issues or "none",
                )

                if pages_fetched_for_source < max_pages_per_url:
                    for next_url in discover_pagination_urls_from_html(html, current_url=current_url):
                        if next_url not in visited:
                            url_queue.append(next_url)

            except Exception:
                logger.exception("amazon_discovery_page_failed url=%s", current_url)

    if not pages:
        return [], {"pages_fetched": 0, "raw_count": 0}

    merged = _merge_page_candidates(pages)
    primary_source_type = pages[0].source_type

    filtered = filter_candidate_pool(
        merged,
        source_url="merged://amazon-es-discovery",
        source_type=primary_source_type,
        raw_candidate_count=raw_count,
        page_issues=[],
        duplicate_rejections=[],
        max_candidates=max_candidates,
        max_recovered_missing_price_candidates=10,
    )

    quality = assess_discovery_quality(
        source_url="merged://amazon-es-discovery",
        source_type=primary_source_type,
        raw_candidate_count=raw_count,
        unique_candidate_count=len(merged),
        accepted_candidate_count=filtered.accepted_candidate_count,
        candidates_with_price_count=sum(1 for c in merged if c.price_eur is not None),
        issue_counts={},
    )
    logger.info(
        "amazon_discovery_quality status=%s reasons=%s accepted=%s rejected=%s",
        quality.status,
        quality.reasons or "none",
        filtered.accepted_candidate_count,
        filtered.rejected_candidate_count,
    )

    if quality.status == "low_quality":
        logger.warning(
            "amazon_discovery_skipping_ingest reason=low_quality quality_reasons=%s",
            quality.reasons,
        )
        return [], {"pages_fetched": len(pages), "raw_count": raw_count}

    return filtered.accepted_candidates, {"pages_fetched": len(pages), "raw_count": raw_count}
```

- [ ] **Step 5: Update `main()` to pass the new setting**

Find in `main()`:
```python
        candidates, page_stats = _run_discovery(
            source_urls,
            logger,
            max_candidates=settings.amazon_discovery_max_candidates,
        )
```

Replace with:
```python
        candidates, page_stats = _run_discovery(
            source_urls,
            logger,
            max_candidates=settings.amazon_discovery_max_candidates,
            max_pages_per_url=settings.amazon_discovery_max_pages_per_url,
        )
```

- [ ] **Step 6: Run the new tests — expect all pass**

```bash
docker compose run --rm app pytest -q tests/test_daily_amazon_discovery.py
```

Expected: `3 passed`

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
docker compose run --rm app pytest -q
```

Expected: all existing tests pass.

- [ ] **Step 8: Commit**

```bash
git add app/jobs/daily_amazon_discovery.py tests/test_daily_amazon_discovery.py
git commit -m "feat: add per-url pagination to amazon discovery job (top 50 per category)"
```
