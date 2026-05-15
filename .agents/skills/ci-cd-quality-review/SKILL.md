---
name: ci-cd-quality-review
description: Use when reviewing or changing Docker, Docker Compose, Make targets, GitHub Actions, Allure reports, coverage artifacts, CI/CD gates, or runtime quality workflows.
---

# CI/CD Quality Review

Use Make targets as the main command interface.

GitHub Actions should execute the same quality flow that is available locally through Make targets. The CI/CD workflow file is `.github/workflows/quality.yml`.

Available Make targets:

- `make unit-test` — all unit tests across services
- `make unit-test-stock` / `make unit-test-wallet` / `make unit-test-session` / `make unit-test-next-ui` — per-service unit tests
- `make coverage-unit` — coverage for all services
- `make coverage-unit-stock` / `make coverage-unit-wallet` / `make coverage-unit-session` — per-service coverage
- `make component-test` — component and API tests
- `make integration-test` — integration tests
- `make smoke-test` — Robot Framework smoke tests
- `make functional-test` — Robot Framework functional tests
- `make quality-test` — full quality gate (Python + Next UI)
- `make quality-test-python` / `make quality-test-next-ui` — per-stack quality checks
- `make allure-report` — generate Allure report
- `make test-all` — all test levels

Check:

- Make target exists for the quality action
- GitHub Actions uses the Make target where practical
- Allure results are generated
- coverage reports are generated
- artifacts are uploaded where applicable with intentional retention configuration
- failure logs are available
- browser or Robot Framework failure artifacts are preserved where applicable
- secrets are not exposed
- destructive Docker commands are not used without explicit request
- TypeScript typecheck (`tsc --noEmit`) and ESLint pass for `next-ui` on push to main

Rules:

- Do not duplicate long commands inside GitHub Actions if a Make target exists.
- Do not weaken quality gates without documenting the reason and risk.
- Do not remove Allure, coverage, Robot Framework, or failure artifacts without explaining why.
- Do not make CI green by skipping meaningful tests without documenting the risk.
- Keep local and CI/CD workflows aligned.
- Configure artifact retention duration intentionally — do not leave it at runtime default without justification.
- Keep stateful `session`, `stock`, and `wallet` system tests on fresh test-runtime
  database volumes; do not point those suites at development database volumes used for
  manual work or backups.
- Keep the test-runtime stack in the isolated `financialmanager_tests` Docker Compose
  project so it does not recreate or replace the developer's local service containers.
