# Deals

Internal ops app for ingesting price data, detecting candidate deals, reviewing them, and publishing approved deals.

## Stack

- FastAPI backend under [app/](/Users/jorgesantos/Documents/GitHub/Deals/app)
- PostgreSQL + SQLAlchemy + Alembic
- React + Vite frontend under [frontend/](/Users/jorgesantos/Documents/GitHub/Deals/frontend)
- Real source integrations:
  - SerpApi Google Shopping via [scripts/ingest_serpapi_google_shopping.py](/Users/jorgesantos/Documents/GitHub/Deals/scripts/ingest_serpapi_google_shopping.py)
  - Keepa via [scripts/ingest_keepa.py](/Users/jorgesantos/Documents/GitHub/Deals/scripts/ingest_keepa.py)

## Bootstrap

1. Copy env defaults:

```bash
cp .env.example .env
```

2. Start the database and apply migrations:

```bash
docker compose up -d db
docker compose run --rm app alembic upgrade head
docker compose run --rm app python scripts/seed_source.py
```

3. Start the backend:

```bash
docker compose up -d app
```

4. Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Keepa notes:
- Set `KEEPA_API_KEY` in `.env` before running any Keepa fetch path.
- Set `KEEPA_DOMAIN_ID` to the Amazon market you want to query, for example `9` for Spain.
- Automatic Keepa enrichment during ingestion is best-effort and only runs when ASIN + Amazon relevance are present and local history is still shallow.

## Core Operational Commands

### Health

```bash
curl "http://127.0.0.1:8000/api/v1/health"
```

### Ingest

SerpApi query:

```bash
docker compose run --rm app python scripts/ingest_serpapi_google_shopping.py "wireless earbuds" --limit 5 --api-base-url http://app:8000
```

Keepa by ASIN:

```bash
docker compose run --rm app python scripts/ingest_keepa.py B0CCEXAMPLE --api-base-url http://app:8000
```

Keepa bulk refresh for real tracked ASINs:

```bash
docker compose run --rm app python scripts/ingest_keepa_bulk.py
```

Recurring/batch ingestion from [data/serpapi_queries.json](/Users/jorgesantos/Documents/GitHub/Deals/data/serpapi_queries.json):

```bash
docker compose run --rm app python -m app.jobs.daily_ingestion
```

Daily sequence with ingestion:

```bash
docker compose run --rm app python -m app.jobs.run_daily --include-ingestion
```

Background Keepa refresher on app boot:

```bash
ENABLE_BACKGROUND_JOBS=true
docker compose up -d app
tail -f logs/jobs/background_keepa_scheduler.log
```

### Review

Pending review queue:

```bash
curl "http://127.0.0.1:8000/api/v1/review/pending"
```

Approve one review:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/review/<review-id>/approve"
```

Reject one review:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/review/<review-id>/reject"
```

### Publication

All deals:

```bash
curl "http://127.0.0.1:8000/api/v1/deals"
```

Mark an approved deal as published:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/deals/<deal-id>/publish"
```

Published deals:

```bash
curl "http://127.0.0.1:8000/api/v1/published-deals"
curl "http://127.0.0.1:8000/api/v1/published-deals/feed?limit=10"
```

### Metrics

```bash
curl "http://127.0.0.1:8000/api/v1/metrics/overview"
```

### Tests

Full suite:

```bash
docker compose run --rm app pytest -q
```

API contract checks:

```bash
docker compose run --rm app pytest -q tests/test_api_workflow.py
```

Jobs:

```bash
docker compose run --rm app pytest -q tests/test_daily_ingestion_job.py tests/test_run_daily_job.py
```

## Current API Surfaces

- `/api/v1/deals`
- `/api/v1/review`
- `/api/v1/published-deals`
- `/api/v1/metrics`
- `/api/v1/ingest`

## Operational Notes

- Published feeds only include deals with `status=approved` and `published_at` set.
- Matching stays conservative: exact first, hybrid fallback second.
- Job logs are written under `logs/jobs`.
- There is no auth layer in this phase.
