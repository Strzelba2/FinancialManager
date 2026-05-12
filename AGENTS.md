# Repository Agent Guide

This file defines the working rules for coding agents in the FinancialManager repository.
Follow these instructions before making changes, running tests, or updating documentation.

## Project Context

FinancialManager is a web-based financial management application composed of:

- `session`: Django-based authentication/session service.
- `wallet`: FastAPI-based financial domain service for wallets, accounts, transactions,
  holdings, brokerage flows, goals, debts, alerts, and related money logic.
- `stock`: FastAPI-based market data, quotes, instruments, reports, parsers, and equity
  report logic.
- `next-ui`: Next.js frontend.
- `tests`: repository-level component, integration, smoke, and functional test suites.
- Docker Compose and Traefik for local service orchestration.
- Allure for test reporting and coverage report publishing.

The project uses a single Git branch named `main`. Do not introduce a multi-branch
workflow unless explicitly requested.

## Instruction Hierarchy

This root `AGENTS.md` contains repository-wide rules. Directory-specific instructions add
service context and should be followed when working under that directory:

- `next-ui/AGENTS.md`
- `wallet/AGENTS.md`
- `session/AGENTS.md`
- `stock/AGENTS.md`

If instructions conflict, prefer the more specific file for the files being changed while
still preserving the repository-wide safety, test integrity, and documentation rules.

## General Working Rules

- Inspect the existing code and tests before editing.
- Keep changes scoped to the user request.
- Do not revert unrelated changes in the working tree.
- Do not run destructive commands such as deleting volumes, resetting Git state, or
  removing generated data unless explicitly requested.
- Prefer existing project patterns over new abstractions.
- Do not introduce real external network calls into unit tests.
- Do not add secrets, tokens, passwords, or production-like credentials.
- When changing documentation, avoid overclaiming. Distinguish strategy, implemented
  behavior, and planned work clearly.
- Use ASCII text unless the edited file already uses another character set for a clear
  reason.

## Agent Role Behavior

Agents working in this repository should choose the correct behavior for the task.

The active repository guidance is this `AGENTS.md` file. The TOML files below are
reusable role prompt templates. They document how a Developer, Tester, or DevOps-oriented
agent should behave, but this repository does not assume that the local Codex runtime will
automatically load them as separate callable agents.

- `.codex/agents/developer-agent.toml`
- `.codex/agents/tester-agent.toml`
- `.codex/agents/devops-agent.toml`

## Repository Skills

Repo-local skills are stored under `.agents/skills/`. Use them for repeatable workflows
that need more specific procedure than the general agent rules:

- `financial-domain-rules`: financial behavior, wallet state, money calculations,
  transactions, brokerage, holdings, gains, debts, and goals.
- `test-strategy-check`: test strategy, coverage policy, risk-based testing, evidence,
  and documentation review.
- `api-contract-review`: API status codes, request/response shape, error payloads, auth,
  ownership, and `next-ui` compatibility.
- `backend-test-design`: backend unit/component/integration test design, fixtures,
  factories, and deterministic test data.
- `ci-cd-quality-review`: Make targets, GitHub Actions, Docker, Allure, coverage
  artifacts, and quality gates.

### Developer Behavior

When implementing or refactoring code:

- Understand the existing service structure before changing code.
- Keep changes small and focused.
- Preserve public API contracts unless the user explicitly asks to change them.
- Update tests when behavior changes.
- Avoid adding abstractions before they are needed.
- Do not change financial calculations without checking related tests.
- Do not change authentication, authorization, session, or ownership logic without
  considering negative tests.
- Explain important design decisions in the final response.

### Tester Behavior

When reviewing or adding tests:

- Use `docs/testing-strategy.md` as the source of truth.
- Identify the risk area touched by the change.
- Select the smallest useful test level.
- Prefer meaningful behavior coverage over percentage-only coverage.
- Check positive and negative paths for high-risk behavior.
- Verify that test data is deterministic and readable.
- Require dedicated test databases or disposable test volumes for `stock` and `wallet`
  component, integration, and functional tests that read or mutate persisted data.
  Do not point those suites at local development databases used for manual work or
  backup/restore workflows.
- Check whether Allure and coverage evidence are affected.
- Apply Allure markers to new tests. Required on every test class:
  `@allure.epic`, `@allure.feature`, `@allure.story`, `@allure.severity`,
  `@allure.tag`, `@allure.link`.
  Add `@allure.description` for complex test classes where the test name
  alone does not convey the business scenario or invariant being verified.
  Use the metadata rules from `docs/testing-strategy.md` Section 10.
- Do not weaken a test only to make it pass.

### DevOps Behavior

When changing CI/CD, Docker, Make targets, reports, or runtime configuration:

- Keep local Make targets and GitHub Actions aligned.
- Avoid duplicating commands directly inside workflows when a Make target exists.
- Preserve Allure and coverage artifact generation.
- Avoid destructive Docker or volume commands unless explicitly requested.
- Do not expose secrets in logs, reports, screenshots, or artifacts.
- Make failures diagnosable through logs, reports, or artifacts.

## Risk-Based Change Rules

Changes in FinancialManager are not all equal. The amount of testing depends on product
risk.

Critical areas:

- authentication
- authorization
- ownership checks
- session verification
- cookies and HMAC handling
- money calculations
- transaction lifecycle
- brokerage buy/sell flows
- holdings and gains
- sensitive financial data handling
- database migrations affecting financial data

For critical areas:

- A positive test is not enough.
- Add negative tests where practical.
- Check ownership and cross-user access where applicable.
- Check boundary values for money-related behavior.
- Verify persisted state when the operation changes financial data.
- Update API/component or integration tests when endpoint behavior changes.

For low-risk UI or documentation changes, use the smallest useful verification.

## Financial Domain Rules

Financial behavior must be tested with clear input and expected output.

For money, transaction, brokerage, holdings, gains, debts, goals, and account logic,
tests should make the business scenario visible.

Where applicable, tests should define:

- currency
- opening balance
- transaction amount
- transaction type
- expected cash effect
- expected final balance
- expected holdings change
- expected realized or unrealized gain
- expected rounding behavior

Important edge cases:

- zero amount
- negative amount
- decimal precision
- rounding boundaries
- same-day transactions
- empty account
- insufficient cash
- partial sale of holdings
- duplicate import rows
- missing or malformed input

Do not rely only on HTTP status code checks when the operation changes financial state.
A test should verify the resulting financial state.

## API Contract Rules

When changing API behavior, check the contract between backend services and `next-ui`.

API-related changes should consider:

- HTTP status code
- request payload
- response shape
- error payload
- authentication requirement
- authorization and ownership rules
- content type
- backward compatibility with frontend API clients

Do not silently rename response fields, change error formats, or change status codes
without updating related tests and frontend usage.

For API changes, prefer component/API tests that verify public behavior from the outside.

## Standard Commands

Use Make targets as the main project interface.

Build and runtime:

```bash
make build
make up
make down
```

Quality and tests:

```bash
make unit-test
make unit-test-next-ui
make coverage-unit
make quality-test
make smoke-test
make functional-test
make component-test
make integration-test
make test-all
```

Reports:

```bash
make allure-report
make allure-up
```

Allure is served locally at:

```text
http://localhost:5252
```

Coverage reports are served beside Allure at:

```text
http://localhost:5252/coverage/
```

## Testing Strategy

The repository follows the testing strategy documented in:

```text
docs/testing-strategy.md
```

Use the strategy as the source of truth for:

- test levels
- risk priorities
- evidence expectations
- coverage policy
- reporting expectations
- CI/CD quality workflow

Backend service-local tests live in:

- `stock/tests`
- `wallet/tests`
- `session/tests`

Repository-level tests live in:

- `tests/component_tests`
- `tests/integration_tests`
- `tests/smoke_tests`
- `tests/functional_tests`

Frontend unit tests live in:

- `next-ui/tests`

## Test Integrity Rules

Do not modify tests only to make the suite pass. A failing test is evidence that must be
analyzed before changing either production code or the test.

When a test fails:

- Reproduce or inspect the failure.
- Identify the behavioral contract being tested.
- Decide whether the production code is wrong, the test expectation is wrong, or the
  test setup is incomplete.
- Prefer fixing production code when the test describes the intended behavior.
- Change the test only when the test is outdated, incorrect, ambiguous, or testing an
  implementation detail instead of the public behavior.

When changing a test, explain the reason clearly in the final response. Include:

- what behavior the test verifies
- the relevant input data or setup
- the expected output or observable result
- why the previous expectation was incorrect or incomplete
- whether production behavior changed or only the test was corrected

Reliable test maintenance means preserving trust in the suite. Passing tests are not the
goal by themselves; meaningful tests that protect intended behavior are the goal.

### Flaky Test Handling

A test that fails intermittently without a code change is a flaky test.

When a test is flaky:

- Do not re-run it silently or ignore the failure.
- Mark it with `@pytest.mark.skip(reason="flaky: <brief description>")` or the
  Vitest `skip` equivalent.
- Add a comment referencing a GitHub issue or describing the investigation needed.
- Do not delete a flaky test — fix it or keep it quarantined with an explanation.
- Report the quarantine in the final response when it affects a high-risk area.

## Agent Anti-Patterns

Do not take these shortcuts, even when under pressure to make tests pass or CI green:

- Do not add `# type: ignore`, `# noqa`, or inline lint disables to silence errors
  instead of fixing the underlying problem.
- Do not use `time.sleep()` in tests. Use explicit waits, polling, or mock time.
- Do not write empty test bodies or `assert True` to inflate coverage numbers.
- Do not disable coverage for a line or branch only to meet a gate threshold.
- Do not rename or rewrite a test only to make it pass without understanding the failure.
- Do not add a new dependency without checking existing project patterns and updating
  the relevant requirements file or `package.json`.

## Coverage Rules

Python coverage is measured with `pytest-cov`, using `coverage.py` underneath.

Coverage commands use:

- `--cov`
- `--cov-config=.coveragerc`
- `--cov-branch`
- XML reports
- HTML reports
- service-level fail-under gates

Current Stage 1 coverage gates:

- `stock`: 50%
- `wallet`: 2%
- `session`: 15%

These are starting gates, not final quality targets. The mature target is 90% line
coverage and 90% branch coverage for production code, excluding generated and boilerplate
files where appropriate.

Branch coverage means decision-path coverage inside code, not Git branches.

## Backend Guidance

Use the local service structure and existing patterns:

- `session` is Django-based.
- `wallet` and `stock` are FastAPI-based.
- Prefer deterministic fixtures and factories.
- Keep unit tests isolated from real external systems.
- For HTTP client mocking, use `responses` for `requests`-based clients and
  `respx` for `httpx`-based clients. Use `pytest-mock` for internal boundaries.
  Do not introduce other HTTP mocking libraries without a clear reason.
- Use service-local `.coveragerc` files for coverage scope and exclusions.
- Add tests near the service/domain being changed.
- For financial logic, test success paths, validation failures, boundary values, and
  error paths.

High-risk backend areas:

- authentication and session verification
- authorization and ownership checks
- HMAC/session cookies
- money calculations
- transaction lifecycle
- brokerage buy/sell cash effects
- holdings and gains
- quotes, instruments, parsers, and report generation

## Frontend Guidance

For files under `next-ui`, also follow:

```text
next-ui/AGENTS.md
```

Frontend tests use Vitest and React Testing Library. Keep UI tests focused on behavior
that matters to users:

- forms
- route guards
- API client behavior
- empty/loading/error states
- money/date formatting
- dashboard and report behavior
- accessibility-relevant behavior such as focus and labels

## Documentation Guidance

Documentation should be confident, precise, and project-scale appropriate.

Use this language style:

- "standards-informed testing model"
- "repository-based traceability"
- "evidence expected from the testing process"
- "CI/CD quality workflow" when describing the intended GitHub Actions flow
- "implemented CI/CD workflow" only when the workflow file and jobs already exist

Avoid language that sounds like marketing, self-promotion, or false compliance claims:

- Do not claim formal certification.
- Do not claim full ISO, ASVS, WCAG, or NIST compliance.
- Do not describe planned tools as current tooling.

## Architecture And Design Documentation Rules

Architecture and detailed design documentation should be updated when a change affects
system structure, service responsibility, data flow, API contracts, financial rules,
security behavior, or CI/CD quality workflow.

Use Markdown files under:

- `docs/architecture/` for system-level architecture
- `docs/design/` for detailed design of important features or flows
- `docs/adr/` for important technical decisions

Use Mermaid diagrams where a flow, dependency, or architecture view is easier to
understand visually. Mermaid diagrams should be kept simple enough to render clearly in
GitHub.

Create or update detailed design when a change affects:

- authentication
- authorization
- session verification
- ownership checks
- money calculations
- transaction lifecycle
- brokerage buy/sell flows
- holdings and gains
- sensitive financial data handling
- API contracts used by `next-ui`
- database migrations affecting financial data
- CI/CD quality workflow

Do not create detailed design documents for small cosmetic changes, simple refactors, or
low-risk implementation details unless the design helps explain important behavior.

A detailed design document should explain:

- purpose
- scope
- business rules
- main flow
- error handling
- API contract where applicable
- data model impact where applicable
- security considerations
- test expectations
- evidence expected from the testing process

## Definition Of Done For Agent Changes

A change is considered complete when:

- the requested behavior is implemented or reviewed
- related tests are added or updated where needed
- the selected verification command was run, or the reason for not running it is explained
- coverage impact is considered for backend changes
- Allure or test evidence is preserved where applicable
- documentation is updated if behavior, commands, or strategy changed
- risks, gaps, or skipped checks are clearly mentioned in the final response

For high-risk changes, the final response should explicitly mention:

- what risk area was touched
- what tests were added or updated
- what verification was run
- what remains unverified, if anything

## Verification Expectations

Choose the smallest useful verification for the change:

- Documentation-only changes: inspect the rendered Markdown or relevant file section.
- Python service changes: run the relevant service unit tests.
- Coverage or test strategy changes: run `make coverage-unit` when Docker is available.
- Frontend changes: run `make unit-test-next-ui` or `make quality-test-next-ui`.
- Cross-service changes: run component/integration tests when the Docker stack is needed.

If a verification command cannot be run, record the reason in the final response.
