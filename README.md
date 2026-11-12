# Financial News Intelligence Pipeline

[![CI](https://github.com/vamsikrishna-garisapati/financial-news-intelligence-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/vamsikrishna-garisapati/financial-news-intelligence-pipeline/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)

**Financial News Intelligence Pipeline** is a Python data-engineering project that
collects stock market news with Apify, stores it in PostgreSQL, and exposes a
FastAPI news search and analytics API for tickers, categories, and sources.

It integrates the Apify Actor
[`vamsi-krishna/stock-market-news-collector`](https://apify.com/vamsi-krishna/stock-market-news-collector)
to ingest financial / ticker news, then normalizes, deduplicates, classifies, and
serves results for dashboards, alerts, and research workflows.

## Disclaimer

Sentiment labels and category tags are **best-effort triage signals only**.
They are **not** investment advice or verified financial signals. This project
does not generate trading recommendations.

## Security and cost notes

- Never commit `APIFY_TOKEN`, `.env`, or other secrets. See [SECURITY.md](SECURITY.md).
- Live Apify collection is **pay-per-event** (roughly ~$0.0025/article on the free tier). Keep `maxItems` small while testing.
- Local Docker Postgres uses demo credentials `fnip` / `fnip` — local development only.
- The HTTP API is **unauthenticated**. Do not expose it on a public network without your own auth and TLS.

## Architecture

```mermaid
flowchart LR
  Client --> FastAPI
  FastAPI --> CollectionService
  CollectionService --> ApifyClient
  ApifyClient --> Actor["stock-market-news-collector"]
  Actor --> Dataset
  CollectionService --> Processor
  Processor --> Classifier
  Processor --> Postgres[(PostgreSQL)]
  FastAPI --> Repositories --> Postgres
```

## Features

- Trigger Apify Actor runs with documented inputs only
- Normalize, validate, and classify news articles
- Deduplicate by canonical URL (Actor `dedupeKey`) with fingerprint fallback
- Persist articles, companies, and collection-run metadata in PostgreSQL
- Search/filter news and query analytics endpoints
- Docker Compose deployment with Alembic migrations
- Pytest suite that mocks Apify (no paid Actor runs in tests)

## Prerequisites

- Python 3.12+
- [UV](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- Apify account + API token for **live** collection runs

## Project layout

```text
app/
  api/                 # FastAPI routes and schemas
  db/                  # SQLAlchemy models, session, repositories
  integrations/        # Apify client wrapper
  services/            # collection, processing, dedupe, classification
alembic/               # database migrations
tests/                 # unit, API, DB, and Apify mock tests
Dockerfile
docker-compose.yml
.env.example
```

## Public clone quickstart

```bash
git clone https://github.com/vamsikrishna-garisapati/financial-news-intelligence-pipeline.git
cd financial-news-intelligence-pipeline
cp .env.example .env
# optional: set APIFY_TOKEN in .env for live collection

docker compose up --build
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Installation (local UV)

```bash
cp .env.example .env
# edit .env and set APIFY_TOKEN for live collection

uv sync
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | Application environment label |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DATABASE_URL` | `postgresql+psycopg://fnip:fnip@localhost:5433/fnip` | SQLAlchemy URL (host port **5433**, localhost-bound) |
| `APIFY_TOKEN` | _(empty)_ | Apify API token (required for live collection) |
| `APIFY_ACTOR_ID` | `vamsi-krishna/stock-market-news-collector` | Actor to run |
| `APIFY_TIMEOUT_SECS` | `300` | Actor run timeout |
| `APIFY_MAX_RETRIES` | `3` | Retries for transient Apify API failures |

### Setting `APIFY_TOKEN`

1. Create a token in [Apify Console → Integrations](https://console.apify.com/settings/integrations), **or**
2. If you already ran `apify login`, copy that token into `.env` as `APIFY_TOKEN`.

The Python Apify client needs an explicit token; it does not read the CLI keychain automatically.

Compose reads `APIFY_TOKEN` (and related vars) from your shell environment or from a local `.env` file Docker Compose auto-loads for variable substitution. Do not commit real tokens.

## Docker setup

PostgreSQL is published on **localhost:5433** only (`127.0.0.1:5433:5432`) so it
does not collide with a local Postgres on `5432` and is not exposed on all interfaces.

```bash
cp .env.example .env
# set APIFY_TOKEN in .env for live runs

docker compose up --build
```

This starts:

- `db` — PostgreSQL 16
- `api` — runs `alembic upgrade head`, then Uvicorn on `http://localhost:8000`

API-only against Compose DB:

```bash
docker compose up -d db
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

## Database migrations

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

## How to run a collection

1. Ensure Postgres is up and migrations are applied.
2. Set `APIFY_TOKEN` in `.env` (or export it in your shell for Compose).
3. Start the API.
4. Trigger a run:

```bash
curl -s -X POST http://localhost:8000/collection-runs \
  -H 'Content-Type: application/json' \
  -d '{
    "feedPreset": "us_markets",
    "tickers": ["AAPL", "NVDA"],
    "maxItems": 10,
    "hoursBack": 24,
    "includeKeywords": [],
    "enrichArticles": true
  }'
```

5. Poll status:

```bash
curl -s http://localhost:8000/collection-runs/<run_id>
```

`POST /collection-runs` returns `202` immediately. Collection continues in a
FastAPI background task (no Redis/Celery in this MVP).

## API documentation

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness + DB check |
| `POST` | `/collection-runs` | Start Apify collection |
| `GET` | `/collection-runs/{run_id}` | Collection status/counters |
| `GET` | `/news` | Search/filter articles |
| `GET` | `/news/{article_id}` | Article detail |
| `GET` | `/companies/{ticker}/news` | News for a ticker |
| `GET` | `/analytics/news-volume` | Volume by `company`, `date`, or `source` |
| `GET` | `/analytics/categories` | Volume by pipeline category |

### Example: search news

```bash
curl -s 'http://localhost:8000/news?ticker=AAPL&limit=5'
```

### Example: analytics

```bash
curl -s 'http://localhost:8000/analytics/news-volume?group_by=company'
curl -s 'http://localhost:8000/analytics/news-volume?group_by=source'
curl -s 'http://localhost:8000/analytics/categories'
```

## Sample JSON output

### Collection run

```json
{
  "id": "2a86c95c-2a80-47cc-a0ff-f0937ec9faa6",
  "status": "succeeded",
  "apify_run_id": "apify-run-1",
  "apify_dataset_id": "dataset-1",
  "actor_run_status": "ok",
  "input_payload": {
    "feedPreset": "us_markets",
    "tickers": ["AAPL", "NVDA"],
    "maxItems": 10
  },
  "items_fetched": 3,
  "items_inserted": 3,
  "items_duplicated": 0,
  "items_invalid": 0,
  "error_message": null,
  "started_at": "2026-03-26T12:00:00Z",
  "finished_at": "2026-03-26T12:00:05Z",
  "created_at": "2026-03-26T12:00:00Z"
}
```

### News item

```json
{
  "id": "7f1b0d2e-1111-2222-3333-444455556666",
  "headline": "Apple reports quarterly earnings beat and raises guidance",
  "source": "CNBC Investing",
  "published_at": "2026-10-09T15:00:00Z",
  "summary": "Apple Inc. posted stronger-than-expected EPS and lifted full-year guidance.",
  "original_url": "https://www.cnbc.com/2026/10/09/apple-earnings.html",
  "categories": ["earnings"],
  "companies": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "exchange": "NASDAQ",
      "sector": "Technology"
    }
  ],
  "sentiment_label": "positive"
}
```

## Classification categories

Rule-based pipeline categories (also mapped from Actor `eventTypes` when present):

- `earnings`
- `mergers_and_acquisitions`
- `leadership_changes`
- `regulatory_updates`
- `product_launches`
- `market_updates` (fallback)

Optional AI classification lives in `app/services/classification/optional_ai.py`
and is disabled by default.

## Testing

```bash
docker compose up -d db
uv run pytest
uv run ruff check app tests
```

Pytest uses `TEST_DATABASE_URL` (default `fnip_test` on port 5433) so it does not
drop the main `fnip` schema. The Compose Postgres init script creates `fnip_test`
on first volume initialization.

Tests mock Apify responses and **never** execute paid Actor runs.

## Assumptions

- Collection jobs are in-process background tasks; a process restart can leave a
  run stuck in `running`.
- Google News links may be redirect URLs; original URLs are preserved.
- Without `APIFY_TOKEN`, the API starts but collection runs fail with a clear error.
- Actor RSS `categories` are kept in `raw_payload`; pipeline categories are separate.

## Troubleshooting

| Problem | Fix |
|---|---|
| `role "fnip" does not exist` on port 5432 | Use Compose DB on **5433** (`DATABASE_URL=...@localhost:5433/fnip`) |
| Collection fails with `APIFY_TOKEN is not configured` | Set `APIFY_TOKEN` in `.env` and restart the API |
| Empty Apify results | Check Actor `runStatus` (`no_items`, `no_new_items`, …); clear strict `includeKeywords` or widen `hoursBack` |
| Migration errors | Ensure DB is healthy: `docker compose ps`, then `uv run alembic upgrade head` |
| Port 8000 in use | Run Uvicorn with `--port 8001` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

No open-source license is granted. This repository is published for demonstration
and portfolio viewing. All rights reserved unless a license is added later.
