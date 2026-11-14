# Financial News Intelligence Pipeline

[![CI](https://github.com/vamsikrishna-garisapati/financial-news-intelligence-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/vamsikrishna-garisapati/financial-news-intelligence-pipeline/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)

**Financial News Intelligence Pipeline** is a self-hosted Python project that
collects stock market news with Apify, stores it in PostgreSQL, and exposes a
FastAPI news search and analytics API for tickers, categories, and sources.

It integrates the Apify Actor
[`vamsi-krishna/stock-market-news-collector`](https://apify.com/vamsi-krishna/stock-market-news-collector)
to ingest financial / ticker news, then normalizes, deduplicates, classifies, and
serves results for dashboards, alerts, and research workflows.

There is **no hosted backend** and **no account with us**. You clone the repo and
run it with your own `APIFY_TOKEN` and PostgreSQL database.

## Disclaimer

Sentiment labels and category tags are **best-effort triage signals only**.
They are **not** investment advice or verified financial signals. This project
does not generate trading recommendations.

## Security and cost notes

- Self-hosted only: use **your own** `APIFY_TOKEN` and PostgreSQL.
- Never commit `APIFY_TOKEN`, `.env`, or other secrets. See [SECURITY.md](SECURITY.md).
- Live Apify collection is **pay-per-event** (roughly ~$0.0025/article on the free tier). Keep `maxItems` small while testing.
- Local Docker Postgres uses demo credentials `fnip` / `fnip` — local development only.
- The HTTP API has **no built-in user authentication** (local MVP). Prefer binding to localhost.
- If you expose the API publicly, you must add **authentication**, **rate limiting**, **HTTPS**, and **access controls** yourself — see [SECURITY.md](SECURITY.md) and [Production deployment](#production-deployment).
- CORS defaults to local frontend origins only (`CORS_ORIGINS`). Do not use `*` in production.
- Retries resume an existing Apify run id when present to avoid duplicate paid Actor starts.

## Architecture

```mermaid
flowchart LR
  Client --> FastAPI
  FastAPI --> Postgres[(PostgreSQL)]
  JobWorker["InProcessJobWorker"] --> Postgres
  JobWorker --> CollectionService
  CollectionService --> ApifyClient
  ApifyClient --> Actor["stock-market-news-collector"]
  Actor --> Dataset
  CollectionService --> Processor
  Processor --> Classifier
  Processor --> Postgres
  FastAPI --> Repositories --> Postgres
```

### Collection sequence

```mermaid
sequenceDiagram
  participant Client
  participant API as FastAPI
  participant DB as PostgreSQL
  participant Worker as JobWorker
  participant Apify

  Client->>API: POST /collection-runs
  API->>DB: insert CollectionRun pending
  API-->>Client: 202 Accepted run id
  Worker->>DB: claim pending FOR UPDATE SKIP LOCKED
  alt no apify_run_id
    Worker->>Apify: start Actor
    Worker->>DB: persist apify_run_id immediately
    Worker->>Apify: wait + fetch dataset
  else apify_run_id exists
    Worker->>Apify: wait/fetch existing run only
  end
  Worker->>DB: mark succeeded or failed with retry
  Client->>API: GET /collection-runs/{id}
  API->>DB: load run
  API-->>Client: status + counters
```

### Runtime components

| Component | Role |
|---|---|
| FastAPI (`app/main.py`) | HTTP API, CORS, JSON logs, lifespan starts the job worker |
| Job worker (`app/services/job_worker.py`) | Polls Postgres, claims leases, recovers abandoned runs |
| Collection service | Starts/resumes Apify, normalizes items, upserts articles |
| Apify client | `start` → persist id → `wait` → `fetch` (no Redis/Celery) |
| PostgreSQL | Articles, companies, collection runs, lease/retry state |

## Features

- Postgres-backed collection jobs with claim/lease, retries, and abandoned-job recovery
- Apify start/resume split so retries do not accidentally start a second paid run
- Normalize, validate, and rule-classify news articles (`classification_method`)
- Deduplicate by canonical URL (Actor `dedupeKey`) with fingerprint fallback
- URL canonicalization: strip `www.`, default ports, tracking params; sort query keys
- Ticker validation + company mapping warnings; raw Actor `OUTPUT` stored on runs
- Search/filter news and analytics endpoints
- Structured JSON logging with secret redaction
- Docker Compose + Alembic migrations
- Pytest suite that mocks Apify (no paid Actor runs in automated tests)

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
  integrations/        # Apify client wrapper (start/wait/fetch)
  observability/       # JSON/text structured logging
  security/            # secret redaction helpers
  services/            # collection, job worker, processing, classification
alembic/               # database migrations
tests/                 # unit, API, job, security, observability tests
Dockerfile
docker-compose.yml
.env.example
```

## Public clone quickstart

```bash
git clone https://github.com/vamsikrishna-garisapati/financial-news-intelligence-pipeline.git
cd financial-news-intelligence-pipeline
cp .env.example .env
# set APIFY_TOKEN in .env for live collection

docker compose up --build
```

- API: [http://localhost:8000](http://localhost:8000)
- Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health: [http://localhost:8000/health](http://localhost:8000/health)

## Installation (local UV)

```bash
cp .env.example .env
# edit .env and set APIFY_TOKEN for live collection

uv sync
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | Environment label (`production` strips CORS `*`) |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed browser origins |
| `COLLECTION_MAX_ITEMS` | `500` | Max `maxItems` per request |
| `COLLECTION_MAX_TICKERS` | `20` | Max tickers per request |
| `COLLECTION_MAX_COMPANIES` | `20` | Max companies per request |
| `COLLECTION_MAX_SEARCH_QUERIES` | `10` | Max search queries per request |
| `COLLECTION_MAX_HOURS_BACK` | `720` | Max `hoursBack` per request |
| `JOB_WORKER_ENABLED` | `true` | In-process Postgres job worker |
| `JOB_POLL_INTERVAL_SECS` | `2` | Job poll interval |
| `JOB_LEASE_SECONDS` | `900` | Stale lease timeout |
| `JOB_MAX_ATTEMPTS` | `3` | Max attempts per collection run |
| `JOB_RETRY_DELAY_SECS` | `30` | Delay before retrying a failed run |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `DATABASE_URL` | `postgresql+psycopg://fnip:fnip@localhost:5433/fnip` | SQLAlchemy URL (host port **5433**) |
| `TEST_DATABASE_URL` | `.../fnip_test` | Pytest database URL |
| `APIFY_TOKEN` | _(empty)_ | Apify API token (required for live collection) |
| `APIFY_ACTOR_ID` | `vamsi-krishna/stock-market-news-collector` | Actor to run |
| `APIFY_TIMEOUT_SECS` | `300` | Actor run timeout |
| `APIFY_MAX_RETRIES` | `3` | Retries for transient Apify API failures |

### Setting `APIFY_TOKEN`

1. Create a token in [Apify Console → Integrations](https://console.apify.com/settings/integrations), **or**
2. If you already ran `apify login`, copy that token into `.env` as `APIFY_TOKEN`.

The Python Apify client needs an explicit token; it does not read the CLI keychain automatically.
Do not commit real tokens.

## Docker setup

PostgreSQL is published on **localhost:5433** only (`127.0.0.1:5433:5432`) so it
does not collide with a local Postgres on `5432` and is not exposed on all interfaces.

```bash
cp .env.example .env
# set APIFY_TOKEN in .env for live runs

docker compose up --build
```

This starts:

- `db` — PostgreSQL 16 (+ `fnip_test` created on first init)
- `api` — runs `alembic upgrade head`, then Uvicorn on `http://localhost:8000`

API-only against Compose DB:

```bash
docker compose up -d db
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Database migrations

Current head: `20260326_0003` (job leases + data-quality fields).

```bash
uv run alembic upgrade head
uv run alembic current
uv run alembic revision --autogenerate -m "describe change"
```

## How to run a collection

1. Ensure Postgres is up and migrations are applied.
2. Set `APIFY_TOKEN` in `.env` and restart the API.
3. Trigger a run (prefer `searchQueries` if Yahoo ticker feeds return 429):

```bash
curl -s -X POST http://localhost:8000/collection-runs \
  -H 'Content-Type: application/json' \
  -d '{
    "feedPreset": "us_markets",
    "tickers": ["MSFT", "TSLA", "NVDA"],
    "searchQueries": ["Microsoft stock", "Tesla stock"],
    "maxItems": 10,
    "hoursBack": 72,
    "useTickerFeeds": false,
    "includeKeywords": [],
    "enrichArticles": true
  }'
```

4. Poll status until `succeeded` or `failed`:

```bash
curl -s http://localhost:8000/collection-runs/<run_id>
```

`POST /collection-runs` returns **202** immediately. An in-process Postgres job
worker claims the pending row (no Redis/Celery). Status values:
`pending` → `running` → `succeeded` | `failed`.

### API authentication (this MVP)

There is **no application-level API key or user login**.

- Local use: call the API directly on `http://localhost:8000`.
- Shared/public use: put auth in front of the app (reverse proxy, API gateway, VPN).
  Example nginx sketch (operator-managed, not shipped here):

```nginx
# Illustrative only — configure TLS and secrets yourself
location / {
  auth_basic "FNIP";
  auth_basic_user_file /etc/nginx/.htpasswd;
  proxy_pass http://127.0.0.1:8000;
}
```

## API documentation

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness + DB check |
| `POST` | `/collection-runs` | Enqueue Apify collection (`202`) |
| `GET` | `/collection-runs/{run_id}` | Status, counters, `actor_output`, errors |
| `GET` | `/news` | Search/filter articles |
| `GET` | `/news/{article_id}` | Article detail (includes `classification_method`) |
| `GET` | `/companies/{ticker}/news` | News for a ticker |
| `GET` | `/analytics/news-volume` | Volume by `company`, `date`, or `source` |
| `GET` | `/analytics/categories` | Volume by pipeline category |

### Example: search news

```bash
curl -s 'http://localhost:8000/news?ticker=MSFT&limit=5'
```

### Example: analytics

```bash
curl -s 'http://localhost:8000/analytics/news-volume?group_by=company'
curl -s 'http://localhost:8000/analytics/news-volume?group_by=source&ticker=NVDA'
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
    "tickers": ["MSFT", "TSLA"],
    "maxItems": 10
  },
  "items_fetched": 10,
  "items_inserted": 8,
  "items_duplicated": 2,
  "items_invalid": 0,
  "actor_output": {"runStatus": "ok", "count": 10},
  "processing_errors": [],
  "error_message": null,
  "attempt_count": 1,
  "max_attempts": 3,
  "duration_ms": 4334,
  "started_at": "2026-03-26T12:00:00Z",
  "finished_at": "2026-03-26T12:00:05Z",
  "created_at": "2026-03-26T12:00:00Z"
}
```

### News item (detail fields)

```json
{
  "id": "7f1b0d2e-1111-2222-3333-444455556666",
  "headline": "Apple reports quarterly earnings beat and raises guidance",
  "source": "CNBC Investing",
  "published_at": "2026-10-09T15:00:00Z",
  "summary": "Apple Inc. posted stronger-than-expected EPS and lifted full-year guidance.",
  "original_url": "https://www.cnbc.com/2026/10/09/apple-earnings.html",
  "canonical_url": "https://cnbc.com/2026/10/09/apple-earnings.html",
  "categories": ["earnings"],
  "classification_method": "rules",
  "processing_error": null,
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

## Production deployment

This project is designed for **self-hosted** operation. It does not depend on a
vendor cloud, but you can deploy the same Compose stack (or equivalent) on any VM.

Minimum checklist before exposing beyond your laptop:

1. Change Postgres credentials; do not use `fnip`/`fnip`.
2. Keep `APIFY_TOKEN` in a secret store / env, never in git.
3. Set `APP_ENV=production` and an explicit `CORS_ORIGINS` allowlist (no `*`).
4. Terminate **HTTPS** at a reverse proxy.
5. Add **authentication** and **rate limiting** at the proxy/gateway (not built into the app).
6. Restrict network access (private VPC, firewall, VPN).
7. Set sensible collection ceilings (`COLLECTION_MAX_*`) and monitor JSON logs.
8. Run migrations (`alembic upgrade head`) before starting new API versions.
9. Prefer `JOB_LEASE_SECONDS` greater than `APIFY_TIMEOUT_SECS` so long Actor waits do not look abandoned mid-run.

Cloud-ready later: split the job worker into its own process/container using the
same Postgres lease tables — no Redis required for the current design.

## Testing

```bash
docker compose up -d db
uv run pytest --cov=app
uv run ruff check app tests
```

Pytest uses `TEST_DATABASE_URL` (default `fnip_test` on port 5433) so it does not
drop the main `fnip` schema. The Compose Postgres init script creates `fnip_test`
on first volume initialization.

Tests mock Apify responses and **never** execute paid Actor runs. Coverage includes
job claim/lease recovery, Apify resume-without-restart, analytics filters, CORS/limits,
structured logging, and Alembic revision chain checks. Coverage gate: **85%**.

## Assumptions

- Collection jobs use an in-process Postgres lease worker; abandoned leases are requeued
  or failed after max attempts; retries resume an existing `apify_run_id` when present.
- Yahoo ticker RSS feeds may return HTTP 429; `searchQueries` + `useTickerFeeds: false`
  is often more reliable for live smoke tests.
- Google News links may be redirect URLs; original URLs are preserved.
- Without `APIFY_TOKEN`, the API starts but collection runs fail with a clear error.
- This MVP has no user accounts; public exposure requires your own auth/rate limits/TLS.
- Actor RSS `categories` stay in `raw_payload`; pipeline categories are separate.

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `role "fnip" does not exist` on port 5432 | Hitting local Postgres instead of Compose | Use `DATABASE_URL=...@localhost:5433/fnip` |
| Collection fails with `APIFY_TOKEN is not configured` | Missing token | Set `APIFY_TOKEN` in `.env` and restart API/Compose |
| Run stuck in `pending` | Worker disabled | Ensure `JOB_WORKER_ENABLED=true` and API process is running |
| Run stuck in `running` then fails with abandoned lease | Process crashed mid-run | Wait for lease expiry (`JOB_LEASE_SECONDS`) or restart API; retry resumes `apify_run_id` if set |
| `actor_run_status=no_items` / empty inserts | Filters too strict or feed failures | Clear `includeKeywords`, widen `hoursBack`, add `searchQueries`, set `useTickerFeeds: false` |
| Yahoo feed `Status code 429` in `actor_output.failures` | Upstream rate limit | Avoid ticker feeds temporarily; rely on search queries / other presets |
| Duplicate paid Apify concern on retry | — | Pipeline resumes existing `apify_run_id`; check logs for `collection.resume` |
| Migration errors | DB not ready / drift | `docker compose ps`, then `uv run alembic upgrade head` |
| CORS errors from a local UI | Origin not allowlisted | Add the UI origin to `CORS_ORIGINS` |
| Port 8000 in use | Another process bound | `uvicorn ... --port 8001` |
| Logs hard to parse in Compose | JSON lines | Set `LOG_FORMAT=text` for local debugging |

### Inspecting a failed/partial run

```bash
curl -s http://localhost:8000/collection-runs/<run_id> | python3 -m json.tool
```

Check `status`, `error_message`, `processing_errors`, `actor_output.runStatus`,
`actor_output.failures`, and counters (`items_fetched` / `items_inserted` /
`items_duplicated` / `items_invalid`).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

No open-source license file is present yet. Treat the repository as source-available
for demonstration until a `LICENSE` is added (planned: MIT).
