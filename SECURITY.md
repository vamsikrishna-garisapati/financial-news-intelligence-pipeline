# Security Policy

## Supported use

This repository is an **open-source, self-hosted** financial news pipeline. Developers
clone it and run it locally (or on their own infrastructure) with:

- their own Apify API token (`APIFY_TOKEN`)
- their own PostgreSQL database (`DATABASE_URL`)

There is **no hosted backend**, **no user registration**, and **no account with us**.
The HTTP API is intended for local development at `http://localhost:8000`.

## Reporting a vulnerability

Please report security issues privately. Do not open a public GitHub issue for
vulnerabilities that could expose credentials, data, or remote abuse paths.

Preferred contact: open a private security advisory on the GitHub repository, or
email the repository owner listed on the GitHub profile.

Include:

- A short description of the issue
- Steps to reproduce
- Impact assessment (if known)
- Any suggested fix

## Secrets

- Never commit `.env`, API tokens, private keys, or production credentials.
- Use `.env.example` as a template only.
- Rotate any token that may have been exposed.
- The app redacts `APIFY_TOKEN` from log records when configured; still avoid printing
  secrets in custom code or shell history.

## Local defaults

- CORS allows only configured origins (`CORS_ORIGINS`), defaulting to local frontends
  (`http://localhost:3000`, `http://127.0.0.1:3000`). Do **not** set `CORS_ORIGINS=*`
  for any shared or production deployment (`APP_ENV=production` strips `*`).
- Collection inputs are validated against configurable ceilings
  (`COLLECTION_MAX_ITEMS`, `COLLECTION_MAX_TICKERS`, etc.).
- Local Docker Postgres uses demo credentials (`fnip` / `fnip`) for development only.
- Apify collection runs incur **pay-per-event** charges when a real `APIFY_TOKEN` is used.
  Retries resume an existing Apify run id when possible to avoid duplicate paid starts.

## If you expose the API beyond localhost

This MVP does **not** ship user authentication or rate limiting. Anyone who can reach
`POST /collection-runs` can trigger paid Apify work with **your** token.

Before binding the API to a public interface you **must** configure, at minimum:

1. **Authentication** (API gateway, reverse-proxy auth, VPN, or similar)
2. **Rate limiting** (proxy or WAF)
3. **HTTPS / TLS** termination
4. **Network access controls** (firewall, private network, allowlists)
5. Non-default database credentials and secret management

## Known intentional limitations

- No built-in user accounts or API-key auth in this MVP.
- No built-in request rate limiter (document and enforce at the edge if public).
- Local Docker demo credentials are not production-safe.
