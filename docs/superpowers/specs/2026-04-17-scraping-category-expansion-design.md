# Scraping Category Expansion — Design

**Date:** 2026-04-17
**Goal:** Expand product ingestion beyond technology to cover all major consumer categories, targeting the top 50 best sellers per category from Amazon.es and complementary Portuguese-language SerpApi queries.

---

## Problem

Current ingestion is heavily skewed toward technology:
- `data/amazon_es_discovery_urls.txt` — 4 URLs, all tech (Electronics, Computing, Mobile, Movers&Shakers)
- `data/serpapi_queries.json` — 3 queries (wireless earbuds, air fryer, robot vacuum)
- `amazon_discovery_max_candidates = 60` — global cap too low for multi-category coverage

## Approach

**Option 2 selected:** Expand data files + add auto-pagination to `daily_amazon_discovery.py` using the already-existing `discover_pagination_urls_from_html` helper. No new integrations needed.

---

## Design

### 1. Amazon.es Category URLs (`data/amazon_es_discovery_urls.txt`)

Add 14 new non-tech categories. Keep the 4 existing tech URLs. Total: **18 category URLs**.

New categories to add:

| Category | URL slug |
|---|---|
| Hogar y cocina | `kitchen` |
| Moda (ropa y accesorios) | `apparel` |
| Belleza y cuidado personal | `beauty` |
| Salud y hogar | `hpc` |
| Deporte y aire libre | `sporting-goods` |
| Juguetes y juegos | `toys` |
| Alimentación y bebidas | `grocery` |
| Mascotas | `pet-supplies` |
| Bebé | `baby` |
| Coche y moto | `automotive` |
| Videojuegos | `videogames` |
| Bricolaje y herramientas | `tools` |
| Jardín | `lawn-garden` |
| Libros | `books` |

URL pattern: `https://www.amazon.es/gp/bestsellers/{slug}/`

### 2. Pagination in `daily_amazon_discovery.py`

Currently `_run_discovery()` fetches exactly one page per URL (no follow-through).

**Change:** After fetching each URL's HTML, call `discover_pagination_urls_from_html` and follow up to `max_pages_per_url` additional pages. This yields top 60 products per category (30 per page × 2 pages), covering the top 50 requirement with margin.

Add config:
```python
# app/core/config.py
amazon_discovery_max_pages_per_url: int = 2
```

Update `_run_discovery()` signature to accept and use `max_pages_per_url`. For each source URL, build a small queue of that URL + discovered pagination URLs, capped at `max_pages_per_url`.

### 3. Global candidate limit

Raise `amazon_discovery_max_candidates` from 60 → **700**.

Rationale: 18 categories × ~30 accepted per page × 2 pages ≈ 1080 raw candidates. After deduplication and price filtering we expect ~500–700 accepted. Setting 700 keeps a safe ceiling without being too restrictive.

### 4. SerpApi queries (`data/serpapi_queries.json`)

Replace the 3 existing tech-biased queries with ~50 Portuguese-language queries spread across all categories. Keep `limit: 5` per query (Google Shopping returns at most 10 per call; 5 avoids rate pressure).

Categories and example queries:

**Cozinha e lar:** "fritadeira de ar sem óleo", "máquina de café cápsulas", "robot de cozinha", "aspiradora robot", "purificador de ar"

**Moda e acessórios:** "ténis running mulher", "mochila escolar", "carteira homem couro", "relógio smartwatch"

**Beleza e cuidado:** "creme hidratante rosto", "sérum vitamina c", "champô anticaspa", "perfume feminino"

**Saúde:** "suplemento magnésio", "vitamina d3", "proteína whey", "tensiómetro de braço"

**Desporto:** "pesos kettlebell", "tapete yoga", "bicicleta estática", "corda de saltar"

**Brinquedos:** "lego criativo", "boneca barbie", "jogo de tabuleiro família", "drone criança"

**Alimentação:** "café em grão", "azeite extra virgem", "proteína vegetal", "chá verde"

**Animais:** "ração gato adulto", "ração cão adulto", "arranhador gato", "cama para cão"

**Bebé:** "carrinho de bebé", "fraldas recém-nascido", "monitor de bebé vídeo"

**Auto:** "dashcam 4k", "aspirador carro sem fio", "carregador sem fios carro"

**Videojogos:** "comando ps5", "headset gaming", "jogo ps5 ação"

**Bricolagem:** "berbequim sem fio", "fita métrica laser", "nível digital"

**Jardim:** "cortador de relva", "mangueira jardim", "kit jardinagem"

**Livros:** "romance português bestseller", "livro autoajuda", "livro infantil ilustrado"

---

## Data Flow (unchanged)

```
data/amazon_es_discovery_urls.txt (18 URLs)
  → daily_amazon_discovery.py
    → fetch page 1 + page 2 per URL (via discover_pagination_urls_from_html)
    → filter_candidate_pool (max 700)
    → Keepa enrichment → IngestionService

data/serpapi_queries.json (~50 queries)
  → daily_ingestion.py (_run_serpapi_batch)
    → SerpApi Google Shopping (Portugal, pt-pt)
    → IngestionService
```

---

## Files Changed

| File | Change |
|---|---|
| `data/amazon_es_discovery_urls.txt` | Add 14 new category URLs |
| `data/serpapi_queries.json` | Replace 3 queries with ~50 PT-language queries |
| `app/core/config.py` | Add `amazon_discovery_max_pages_per_url: int = 2`; raise `amazon_discovery_max_candidates` to 700 |
| `app/jobs/daily_amazon_discovery.py` | Update `_run_discovery()` to paginate up to `max_pages_per_url` per source URL |

---

## Out of Scope

- New data sources (Keepa category browse, SerpApi category API)
- Dynamic query generation
- Per-category candidate limits
- Changing scoring/ranking logic
