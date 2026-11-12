# Contributing

Thanks for your interest in improving this project.

## Development setup

```bash
cp .env.example .env
docker compose up -d db
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

## Before opening a pull request

1. Keep Apify Actor input/output fields aligned with the published Actor schema.
   Do not invent Actor parameters or dataset fields.
2. Add or update tests for behavior changes.
3. Run:

```bash
uv run ruff check app tests
uv run pytest
```

4. Never commit secrets (`.env`, tokens, credentials, private keys).

## Pull request process

1. Fork the repository (or create a branch from `main`).
2. Make focused changes with a clear description.
3. Open a PR against `main` and wait for CI to pass.

## Scope notes

- Sentiment and category labels are best-effort triage signals, not investment advice.
- Prefer simple, production-conscious changes over new infrastructure unless needed.
