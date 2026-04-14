# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Internal ops app for ingesting price data, detecting candidate deals, reviewing them, and publishing approved deals.

- FastAPI backend (`app/`)
- PostgreSQL + SQLAlchemy (psycopg3 driver) + Alembic migrations
- React + Vite frontend (`frontend/`)
- External integrations: SerpApi (Google Shopping) and Keepa (Amazon price history)

## Development Commands

### Backend (via Docker)

```bash
# Start DB and apply migrations
docker compose up -d db
docker compose run --rm app alembic upgrade head
docker compose run --rm app python scripts/seed_source.py

# Start the app
docker compose up -d app

# Run all tests
docker compose run --rm app pytest -q

# Run a single test file
docker compose run --rm app pytest -q tests/test_deal_scoring.py

# Run a specific test
docker compose run --rm app pytest -q tests/test_deal_scoring.py::test_name
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Jobs

```bash
# Full daily sequence (without ingestion)
docker compose run --rm app python -m app.jobs.run_daily

# With ingestion
docker compose run --rm app python -m app.jobs.run_daily --include-ingestion

# Individual ingestion
docker compose run --rm app python scripts/ingest_serpapi_google_shopping.py "query" --limit 5 --api-base-url http://app:8000
docker compose run --rm app python scripts/ingest_keepa.py B0CCEXAMPLE --api-base-url http://app:8000
docker compose run --rm app python scripts/ingest_keepa_bulk.py
```

Job logs are written to `logs/jobs/`.

## Architecture

### Data Flow

```
SerpApi / Keepa scripts
  → POST /api/v1/ingest
    → app/ingestion/service.py       # normalize, deduplicate, upsert ProductSourceRecord
    → app/matching/                  # match to existing Product/ProductVariant
    → PriceObservation saved
  → app/jobs/daily_scoring.py        # score candidate deals from PriceObservations
  → Deal created (status=pending_review)
  → app/jobs/daily_auto_publish.py   # auto-approve high-confidence deals
  → Manual review via /api/v1/review
  → Deal status=approved → published_at set → appears in feed
```

### Key Modules

- **`app/ingestion/`** — normalization pipeline: raw payload → `NormalizedRecord` → `ProductSourceRecord`. `variant_parser.py` and `variant_helpers.py` extract structured variant attributes (size, color, pack count, etc.) from raw titles.

- **`app/matching/`** — two-phase matching: exact (`service.py` → `repository.py`) first, then hybrid fuzzy (`hybrid.py` + `hybrid_service.py`) as fallback. `scoring.py` assigns confidence scores; `decision.py` decides match/no-match. `feature_extraction.py` builds feature vectors.

- **`app/pricing/`** — `aggregation.py` computes `PriceStatistic` windows; `scoring.py` scores deals by comparing current price vs. historical stats; `fake_discount.py` detects inflated list prices.

- **`app/integrations/`** — `keepa_client.py` wraps Keepa API; `keepa_fetch_policy.py` enforces rate-limit and freshness rules (only fetches when ASIN is present and local history is shallow); `keepa_history.py` / `keepa_curation.py` process and store Keepa price history.

- **`app/jobs/`** — daily pipeline sequence orchestrated by `run_daily.py`: `daily_ingestion` → `daily_stats_recompute` → `daily_scoring` → `daily_auto_publish` → `daily_ai_drafts`. `background_keepa_scheduler.py` runs async in-process when `ENABLE_BACKGROUND_JOBS=true`.

- **`app/services/`** — business logic layer consumed by API routes. Notable: `deal_generation_service.py` creates Deal records; `review_service.py` manages review queue; `personalization.py` and `user_preferences_service.py` handle user affinity signals.

- **`app/ai/`** — AI copy generation (stub by default; configure `ai_copy_model_name` to enable real model).

- **`app/db/models.py`** — single file with all SQLAlchemy ORM models. Core entities: `Source`, `Product`, `ProductVariant`, `ProductSourceRecord`, `PriceObservation`, `PriceStatistic`, `Deal`, `ReviewQueue`, `AICopyDraft`, `User`.

### Configuration

All config via `app/core/config.py` (`Settings` with pydantic-settings). `.env` file at repo root. Key env vars:

- `DATABASE_URL` — full override (production). Falls back to `POSTGRES_*` vars for local Docker.
- `KEEPA_API_KEY`, `KEEPA_DOMAIN_ID` — required for Keepa enrichment (domain 9 = Spain, 1 = US).
- `SERPAPI_API_KEY` — required for SerpApi ingestion.
- `ENABLE_BACKGROUND_JOBS=true` — activates in-process Keepa scheduler on app boot.
- `GOOGLE_CLIENT_ID` — for Google OAuth login.

### API Routes

All routes under `/api/v1/`:
- `ingest` — accept raw product payloads
- `deals` — list/publish deals
- `review` — pending queue, approve/reject
- `published-deals` — public feed
- `metrics` — overview stats
- `auth`, `me`, `preferences` — user auth and personalization

### Database Migrations

```bash
# Create new migration after model changes
docker compose run --rm app alembic revision --autogenerate -m "description"

# Apply
docker compose run --rm app alembic upgrade head
```
