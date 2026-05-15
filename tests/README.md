# Testing Strategy

This repository uses an explicit test pyramid with dedicated tooling and Docker workflows.

## Layers

- `stock/tests`, `wallet/tests`, `session/tests`
  Backend unit tests that stay close to each service. New tests should use Python `unittest`
  classes, run through `pytest` for discovery/reporting, and avoid real network calls.
- `next-ui/tests`
  Frontend unit tests for Next.js/React written in `Vitest` with React Testing Library.
- `tests/smoke_tests`
  Fast stack probes written in Robot Framework. Suite files live in `TestSuites/`, and
  Python-backed Robot keyword libraries live in `TestKeywords/`.
- `tests/functional_tests`
  Browser-level functional coverage written in Robot Framework with the Playwright-powered
  Browser library. Suite files live in `TestSuites/`, and Python-backed Robot keyword
  libraries live in `TestKeywords/`.
- `tests/component_tests`
  Public HTTP/component coverage written in `pytest`.
- `tests/integration_tests`
  Service integration and API-contract checks written in `pytest`.
- `tests/helpers`
  Shared pytest helpers and deterministic payload factories for cross-service tests.
- `tests/artifacts`
  Generated Robot and Allure outputs.

## Conventions

- Unit tests use deterministic factories and mocks instead of live dependencies.
- Component tests verify public routes, status codes, content types, redirects, and user-visible contract behavior.
- Integration tests verify service readiness, OpenAPI route contracts, database
  migrations, and real Docker dependencies.
- Functional tests use stable selectors, attach screenshots through Robot/Allure, and cover important UI journeys.
- Allure labels use `epic` for layer, `feature` for service/domain, `story` for behavior,
  `severity` for risk importance, `tag` for cross-cutting filters (e.g. `auth`, `money`,
  `financial-data`, `reports`, `ai`, `parsing`, `security`, `health`, `middleware`, `utils`),
  `link` for a jump to the GitHub project, and `description` for complex test classes.
- Functional tests attach a Playwright trace zip to Allure when the suite fails. Tracing
  is enabled by the Python keyword `Open Next Ui Browser`. The trace is saved
  automatically when the browser closes and attached by
  `tests/functional_tests/TestKeywords/allure_helper.py` if `${SUITE STATUS}` is `FAIL`.

## Commands

After changing Dockerfiles or test dependencies, rebuild the local stack:

```bash
make build
```

Run the suites:

```bash
make test-all
make unit-test
make coverage-unit
make quality-test
make unit-test-next-ui
make smoke-test
make functional-test
make component-test
make integration-test
```

`make unit-test-next-ui` refreshes `next-ui` container dependencies before running Vitest so the persisted `node_modules` volume does not lag behind `package.json`.

`make unit-test` and `make test-all` do not stop after the first failed suite. They continue through every configured batch, then generate Allure so you can inspect the full failure set in one report. The final command still exits with an error code if anything failed.

`make smoke-test`, `make functional-test`, `make component-test`, and
`make integration-test` run through `tests/docker/run_with_test_runtime.sh`. That wrapper
starts `session`, `wallet`, and `stock` against fresh test database volumes and removes
those test volumes after the command exits. The normal development database volumes are
not used as test fixtures. The wrapper uses a separate Docker Compose project named
`financialmanager_tests`, so service names such as `session-db`, `wallet-db`, and
`stock-db` resolve to test containers inside the test network instead of the local
development containers. The `test-runner` service also brings Traefik and the UI
services into the test project through Compose dependencies, so smoke and functional
tests exercise the same routed service boundary as a user-facing stack.

Before running system tests (`make smoke-test`, `make functional-test`,
`make component-test`, `make integration-test`, or `make test-all`), stop the normal
local development stack with `make down`. The current test runtime is isolated at the
database-volume level, but it is not intended to run in parallel with the dev stack.

`make coverage-unit` runs service-local Python unit tests with incremental coverage gates
and `next-ui` Vitest unit coverage as a reported frontend baseline. It writes HTML
coverage reports beside the Allure report. After `make coverage-unit` or `make allure-up`,
open `http://localhost:5252/coverage/`.

The coverage landing page shows three views of the same evidence:

- global service coverage for each measured service
- domain/module coverage by important path groups, such as `stock` equity reports,
  importers, API code, and persistence helpers
- changed-code coverage for executable lines added or modified in the current Git diff

For Python services, line and branch coverage come from `coverage.xml`. Function coverage
comes from the generated `coverage.py` function index, so it is visible in the combined
coverage overview instead of showing as `n/a`.

The service links on that page still open the raw `coverage.py` or Vitest HTML reports.

`make quality-test` runs Python compile checks and Next.js lint/typecheck checks.

`make functional-test` runs Robot Framework Browser tests against `next-ui` through Traefik.

`make test-all` runs unit, smoke, functional, component, and integration suites, then generates and serves one combined Allure report.

Generate and view the combined Allure report:

```bash
make allure-report
make allure-up
```

The Allure UI is served at `http://localhost:5252`.

GitHub Actions uploads the generated report as the `allure-evidence` artifact instead of
serving a browser-accessible container from the runner. Download and view the latest CI
report locally with:

```bash
make ci-allure-up
```

Pass `RUN_ID=<github-run-id>` to inspect a specific run. The script replaces
`tests/artifacts/ci-allure` on each download so old CI reports do not pile up in the
working tree.

## Reporting

- Unit tests write Allure results into each service:
  - `stock/tests/artifacts/allure-results`
  - `wallet/tests/artifacts/allure-results`
  - `session/tests/artifacts/allure-results`
  - `next-ui/tests/artifacts/allure-results`
- Root smoke/functional/component/integration suites write to `tests/artifacts/allure-results`
- `make allure-report` aggregates every result directory into one HTML report

## Coverage Gates

Coverage gates are intentionally incremental, but the mature target is 90% line and
90% branch coverage for production service code. In this context, branch coverage means
decision-path coverage inside code, such as `if/else` and `try/except` paths; it does not
mean Git branches. This project can still use a single `main` branch. The current Stage 1
gates use branch coverage and exclude generated, boilerplate, configuration-only, and
mostly declarative framework files through each service `.coveragerc`. The Python
service configs use explicit `source` scopes so untested behavior-bearing modules still
appear as 0% instead of disappearing from the report. This keeps import side effects from
making coverage look healthier than the behavior tests really prove.

Current Stage 1 thresholds:

- `stock`: 55%
- `wallet`: 8%
- `session`: 25%
- `next-ui`: reported only until a meaningful frontend baseline is accepted

Planned ratchet path:

- Stage 2: `stock` 70%, `wallet` 25%, `session` 40%
- Stage 3: `stock` 80%, `wallet` 60%, `session` 65%
- Stage 4: all services 90% line and 90% branch coverage

Raise these thresholds when a domain receives meaningful tests, especially auth, transactions,
holdings, quotes, report generation, and security-sensitive flows.
