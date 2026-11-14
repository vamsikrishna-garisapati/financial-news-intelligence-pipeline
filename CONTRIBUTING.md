# Contributing

Thanks for your interest in improving this project.

## Development setup

```bash
cp .env.example .env
# optional: APIFY_TOKEN for manual live smoke tests only

docker compose up -d db
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://localhost:8000/docs

## Architecture reminders

- Collection execution uses a **Postgres-backed in-process job worker** (leases + retries).
  Do not reintroduce fire-and-forget `BackgroundTasks` for paid Apify runs.
- Retries must **resume** an existing `apify_run_id` instead of starting a new Actor run.
- Keep Apify Actor input/output fields aligned with the published Actor schema.
  Do not invent Actor parameters or dataset fields.
- The HTTP API has **no built-in auth** in this MVP; document any public-exposure changes in `SECURITY.md`.

## Before opening a pull request

1. Add or update tests for behavior changes (mock Apify; never start paid runs in CI).
2. Run:

```bash
uv run ruff check app tests
uv run pytest --cov=app
```

3. Update README / SECURITY docs when behavior or env vars change.
4. Never commit secrets (`.env`, tokens, credentials, private keys).

## Issues and pull requests

- Use the GitHub issue templates for bugs and feature requests.
- Security issues: follow [SECURITY.md](SECURITY.md) (private advisory), not public issues.
- PRs should follow `.github/PULL_REQUEST_TEMPLATE.md` and wait for CI (Ruff, Alembic smoke, pytest coverage).

## Pull request process

1. Fork the repository (or create a branch from `main`).
2. Make focused changes with a clear description.
3. Open a PR against `main` and wait for CI to pass.

## Scope notes

- Sentiment and category labels are best-effort triage signals, not investment advice.
- Prefer simple, production-conscious changes over new infrastructure unless needed.
- Redis/Celery is intentionally out of scope while Postgres leases remain sufficient.
