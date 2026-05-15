---
name: test-strategy-check
description: Use when reviewing a change against docs/testing-strategy.md, selecting the right test level, checking risk coverage, coverage policy, evidence, or release readiness.
---

# Test Strategy Check

Use `docs/testing-strategy.md` as the source of truth.

For every relevant change, identify:

- service or area affected
- risk area affected
- test level required
- expected evidence
- coverage impact
- whether Allure or coverage reports are affected
- whether GitHub Actions or Make targets are affected

Risk areas to check first:

- authentication
- authorization
- ownership checks
- session verification
- cookies and HMAC
- 2FA flows (high-risk area in `session`)
- money calculations
- transaction lifecycle
- brokerage buy/sell flows
- holdings and gains
- sensitive financial data handling
- database migrations affecting financial data
- API contracts used by `next-ui`

Select the smallest useful test level:

- unit test for isolated logic
- API/component test for endpoint behavior
- integration test for real dependencies or persisted state
- smoke test for basic system availability — use Robot Framework, not pytest
- functional test for critical browser journeys — use Robot Framework, not pytest
- security test for misuse, ownership, auth, and sensitive data risks
- accessibility test for WCAG compliance where applicable (see `docs/testing-strategy.md` section 5.8)
- performance test for latency and load where applicable (see `docs/testing-strategy.md` section 5.9)

Database isolation:

- `session`, `stock`, and `wallet` component, integration, and functional tests that read
  or mutate persisted data must use the test-runtime-managed database volumes.
- Migration checks are integration tests, not unit tests.

Coverage gates (enforced via `.coveragerc`):

- `wallet` ≥ 2% (lowest coverage, highest financial risk — priority target)
- `session` ≥ 15%
- `stock` ≥ 50%

Do not recommend tests only to increase coverage percentage. Recommend tests that protect real behavior.

Allure evidence checklist for new or changed tests:

- `@allure.epic`, `@allure.feature`, `@allure.story` — present on every test class.
- `@allure.severity` — assigned using risk: `BLOCKER` for money/auth, `CRITICAL` for
  transactions/reports/brokerage, `NORMAL` for important non-critical behavior, `MINOR` for
  utilities and formatting.
- `@allure.tag` — at least one cross-cutting label: `auth`, `security`, `money`,
  `financial-data`, `reports`, `ai`, `parsing`, `middleware`, `health`, `utils`.
- `@allure.link` — GitHub project link on every class.
- `@allure.description` — for complex classes where the story line is not self-explanatory.
- Functional Robot Framework suites should use `Open Next Ui Browser` and
  `Close Browser And Keep Failure Artifacts` from
  `tests/functional_tests/TestKeywords/browser_keywords.py` so failed suites attach a
  Playwright trace to Allure.
