# Stock Agent Guide

Follow the root `AGENTS.md` first. This file adds service-specific rules for `stock`.

## Scope

`stock` is a FastAPI service responsible for instruments, quotes, market data parsing,
historical data, report snapshots, equity reports, AI prompt construction, sanitization,
cache behavior, scraping/browser integrations, CRUD modules, validators, schemas, and
market-data APIs.

## Risk Profile

Treat `stock` changes as data-quality and reporting-risk changes. Incorrect behavior can
produce misleading reports, invalid market data, broken dashboards, or unsafe AI prompts.

Critical areas:

- instruments and quote APIs
- parser behavior and malformed market data
- report builder/service logic
- AI prompt construction and sanitization
- cache behavior
- scraping/browser failure modes
- API response contracts used by `next-ui`
- migrations affecting market/report data

## Working Rules

- Do not use real network calls in unit tests.
- Use deterministic fixtures for instruments, quotes, market data rows, report snapshots,
  and web-source inputs.
- Parser tests should include malformed, missing, empty, and locale-specific data where
  applicable.
- Report tests should verify meaningful output fields, not only that a report object
  exists.
- AI/report changes must preserve sanitization and avoid leaking unsafe or irrelevant
  prompt content.
- Scraper/browser failure modes should return controlled errors instead of unexpected
  exceptions where applicable.
- Preserve API contracts unless the user explicitly requests a contract change.

## Test Expectations

High-risk changes should consider:

- valid and invalid instrument symbols
- missing latest quotes
- malformed numeric/date fields
- empty parser input
- cache hit and miss behavior
- report builder success and failure paths
- prompt/sanitization edge cases
- browser scraping timeout or unavailable-page behavior

## Verification

Use the smallest relevant command:

```bash
make unit-test-stock
make coverage-unit-stock
```

For public API behavior or cross-service assumptions:

```bash
make component-test
make integration-test
```
