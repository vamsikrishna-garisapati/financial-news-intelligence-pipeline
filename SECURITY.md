# Security Policy

## Supported use

This repository is a **local / demo** financial news pipeline. It is not a
hardened multi-tenant hosted service. Do not expose the API or database to the
public internet without authentication, TLS, and your own hardening.

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

## Known intentional limitations

- The HTTP API is **unauthenticated** in this MVP.
- Local Docker Postgres uses demo credentials (`fnip` / `fnip`) for development only.
- Apify collection runs incur **pay-per-event** charges when a real `APIFY_TOKEN` is used.
