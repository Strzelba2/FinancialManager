---
name: backend-test-design
description: Use when creating or reviewing backend tests for FinancialManager services, including unittest unit tests, pytest component/API/integration tests, fixtures, mocks, coverage, and Allure evidence.
---

# Backend Test Design

Backend testing rules:

- Use `unittest` style for backend Python unit tests where the service already follows that pattern.
- Use `unittest.mock` for unit-test patching and dependency replacement.
- Use `pytest` mainly for component, API, and integration tests.
- Use `pytest` fixtures for reusable component/API/integration setup.
- Use `pytest-cov` for line and branch coverage.

Unit tests should:

- be isolated
- avoid real network calls
- avoid real external services
- use deterministic input data
- test success paths, validation failures, boundary values, and error paths
- focus on behavior, not implementation details

API/component tests should verify:

- status code
- response shape
- content type
- validation errors
- authentication behavior
- authorization and ownership behavior
- expected error responses

Integration tests should verify:

- database connectivity
- migrations
- persisted state
- service readiness
- routing assumptions
- cross-service behavior where needed

For `session`, `stock`, and `wallet`, database-backed component and integration tests
should use the test runtime's fresh database volumes. Migration behavior belongs in
integration tests, not unit tests.

Do not create tests that only increase coverage without protecting meaningful behavior.

Allure metadata:

- Add Allure metadata to every test class. All six decorators are required:
  - `@allure.epic` — service or quality area (e.g. `Wallet`, `Session`, `Stock`, `Unit Tests`).
  - `@allure.feature` — tested domain (e.g. `Transactions`, `Authentication`, `Quotes`).
  - `@allure.story` — tested behavior in one sentence.
  - `@allure.severity` — risk-based importance: `BLOCKER` for money/auth, `CRITICAL` for
    transactions/reports, `NORMAL` for important non-critical behavior, `MINOR` for utilities.
  - `@allure.tag` — one or more cross-cutting labels for filtering:
    `auth`, `security`, `money`, `financial-data`, `reports`, `ai`, `parsing`,
    `middleware`, `health`, `utils`.
  - `@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")` — gives QA
    a direct link to the repository when investigating a failure.
- Add `@allure.description` when the class name and story alone do not capture the business
  scenario or the key invariant being verified (e.g. multi-step financial calculations,
  AI retry strategies, sanitizer fallback logic).

Coverage:

- Coverage gates are enforced via `.coveragerc` per service.
- Current gates: `wallet` ≥ 2%, `session` ≥ 15%, `stock` ≥ 50%.
- Do not lower a coverage gate without documenting the reason.
- `wallet` has the lowest coverage but the highest financial risk — treat it as the highest-priority coverage target.

Scope note:

- This skill covers `unittest` and `pytest` backend tests only.
- Smoke and functional tests use Robot Framework and are outside the scope of this skill.
