# FinancialManager Test Strategy

## Document Overview

FinancialManager is a web-based financial management system composed of backend
services, a Next.js frontend, Docker-based local infrastructure, and automated test
reporting through Allure.

This document describes how testing is organized for the project. It defines the main
test levels, quality priorities, automation scope, coverage expectations, reporting
evidence, and the roadmap for improving confidence in the most important product areas.

The strategy is designed for a GitHub-based development workflow. Professional testing
and security references are used as guidance, but the goal is practical, maintainable
evidence rather than formal certification.

## 1. Purpose

The purpose of this test strategy is to define a clear and repeatable testing approach for
FinancialManager.

The strategy explains how the project is tested across backend services, frontend
components, API behavior, Docker-based infrastructure, and end-to-end user journeys. It
also defines how test results, coverage, and quality evidence are collected and reviewed.

The main testing focus is placed on areas where defects would have the highest impact:
authentication, authorization, financial data integrity, money calculations, transaction
lifecycle, API contracts, and core UI flows.

The document does not define a formal certification process. Instead, it defines a
practical quality workflow that can be implemented and maintained directly in the GitHub
repository using automated tests, Make targets, Allure reports, coverage reports, GitHub
issues, and future GitHub Actions checks.

## 2. Standards And Frameworks

FinancialManager uses selected testing, quality, security, and accessibility references
as guidance for building a practical test strategy. These references help define what
should be tested, how risks should be prioritized, and what kind of evidence should exist
in the repository.

The project does not claim formal certification or full compliance with these standards.
They are used to keep the testing approach structured, risk-based, and technically
reasonable.

| Reference | How It Is Used In This Project | Expected Evidence |
| --- | --- | --- |
| ISO/IEC/IEEE 29119 | Used as a general reference for test process structure, test levels, test documentation, entry and exit criteria, and reporting. | Test strategy, test levels, Make targets, Allure reports, coverage reports, and test backlog. |
| ISO/IEC 25010:2023 | Used as a quality model for defining what product quality means for FinancialManager. | Quality goals covering functionality, reliability, security, usability, maintainability, performance, compatibility, and portability. |
| OWASP ASVS | Used as a security verification reference for authentication, session handling, authorization, input validation, and sensitive data handling. | Security-focused automated tests, API misuse tests, auth/session tests, and documented security exceptions. |
| OWASP WSTG | Used as a practical source of web and API security test ideas. | Security test charters, exploratory security checks, and automated tests for selected high-risk areas. |
| WCAG 2.2 AA | Used as an accessibility target for core user journeys. | Keyboard navigation checks, focus visibility, form labels, error messages, contrast checks, and future axe-based automation. |
| NIST SSDF | Used as a secure development reference for planning security-related quality activities. | Dependency scanning plan, static analysis plan, security backlog items, and documented risk acceptance. |

The references are applied only where they provide practical value for the project. The
main goal is not to satisfy a checklist, but to make testing decisions traceable,
repeatable, and based on real product risk.

## 3. Product Quality Goals

FinancialManager quality is defined by the risks and behavior of the application, not only
by test coverage numbers. The goal of testing is to build confidence that the system works
correctly, protects user data, handles financial calculations safely, and remains
maintainable as the project grows.

The quality goals below are based on the ISO/IEC 25010 quality model and adapted to the
actual scope of FinancialManager.

| Quality Attribute | FinancialManager Goal | Evidence Approach |
| --- | --- | --- |
| Functional suitability | Core financial workflows behave correctly and match API/UI contracts. | Unit, component/API, integration, and functional tests. |
| Reliability | Services start, migrate, recover, and expose readiness consistently. | Smoke tests, readiness checks, migration checks, retry scenarios, and error-path tests. |
| Security | Authentication, session handling, authorization, input validation, and sensitive data handling are verified against the selected OWASP risks. | Auth/session tests, API misuse tests, security charters, ASVS checklist, and dependency/static analysis. |
| Usability | Key flows are understandable, stable, and resilient to empty, error, and loading states. | Frontend unit tests, component tests, functional journeys, and exploratory review. |
| Accessibility | Core UI journeys follow WCAG 2.2 AA expectations where applicable. | Keyboard checks, focus behavior, form labels, error messages, contrast checks, and axe automation. |
| Maintainability | Tests are layered, deterministic, readable, and tied to risk. | Factories, fixtures, clear suite structure, coverage gates, lint/typecheck, and Allure metadata. |
| Performance efficiency | Core API and UI journeys stay within defined local performance budgets. | Smoke performance checks, focused load/performance tests, and budget tracking for high-risk flows. |
| Compatibility | The application works through Docker, Traefik, supported browsers, and responsive layouts. | Docker integration tests, Robot Browser tests, and responsive UI checks. |
| Portability | The quality workflow is reproducible from the repository. | Make targets, Docker Compose, generated Allure reports, and generated coverage reports. |

These goals are used to decide which tests should be automated first. Areas connected to
security, financial data integrity, and money calculations have higher priority than
low-risk UI or formatting behavior.

## 4. Scope

This strategy covers testing activities for the main parts of FinancialManager and the
quality workflow used to verify them.

The scope includes:

- `session`: registration, login, session verification, cookies, HMAC handling, user
  blocking, 2FA, logout, and admin/security-related paths.
- `wallet`: wallets, accounts, transactions, brokerage flows, holdings, gains, alerts,
  recurring expenses, debts, goals, and money-related calculations.
- `stock`: instruments, quotes, market data parsing, report generation, AI report support,
  caching, and scraping failure handling.
- `next-ui`: forms, route protection, dashboards, reports, charts, API clients, formatting,
  loading states, error states, empty states, and responsive behavior.
- Local runtime and test infrastructure: Docker Compose, Traefik routing, service
  readiness, database migrations, Allure reporting, and coverage reports.
- CI/CD quality checks in GitHub Actions, using the same Make targets that are available
  for local execution.

The strategy focuses on areas that have the highest impact on product correctness, data
integrity, security, and user trust. This includes authentication, authorization, money
calculations, transaction lifecycle, API contracts, financial reports, and core user
journeys.

The same test flow should be executable locally and in GitHub Actions. Local Make targets
define the commands, while CI/CD provides repeatable execution, reporting, and artifact
collection for the repository.

### Out Of Scope

The following areas are not part of the current testing strategy:

- formal certification or external audit process
- production monitoring and incident response
- full external penetration testing
- production-level load testing
- formal test-management tooling outside GitHub
- full consumer-driven contract testing between services
- production-grade CI/CD release governance beyond the repository quality gates

These areas may be added later if the project needs them, but they are not required for
the current testing flow.

### Test Basis And Lightweight Traceability

FinancialManager uses repository-based traceability. Product behavior, domain rules,
risks, automated tests, and quality evidence are kept close to the code instead of being
managed in a separate requirements-management system.

The test basis consists of:

- implemented application behavior
- API route contracts and response shapes
- UI user journeys and visible validation behavior
- financial domain rules such as balances, transactions, holdings, gains, cash effects,
  and report calculations
- security and privacy risks described in this strategy
- local development documentation and Docker runtime assumptions
- defects, ideas, and future work tracked through GitHub issues when needed

Traceability is maintained through:

- clear test names
- test locations that match the tested service or feature
- suite structure
- Allure metadata
- linked GitHub issues for defects, risks, or follow-up work
- coverage reports for tested production code
- CI/CD artifacts generated from GitHub Actions

A dedicated requirement-to-test matrix is introduced only when the risk level justifies
it, for example for authentication, authorization, money calculations, transaction
lifecycle, brokerage flows, or data integrity.

### Repository Evidence

Testing evidence is stored or generated through the repository workflow:

- Markdown documentation for strategy, roadmap, and quality decisions
- Make targets for repeatable local and CI test execution
- automated test results collected by Allure
- coverage reports for line and branch coverage
- GitHub issues for risks, defects, test tasks, and accepted exceptions
- GitHub Actions artifacts for test results, coverage reports, and failure diagnostics

## 5. Test Levels

FinancialManager uses a layered testing approach. Each test level has a different purpose
and should answer a different question about the system.

The goal is not to duplicate the same checks at every level. Unit tests should verify
small pieces of logic, API and integration tests should verify service behavior and
dependencies, and functional tests should verify the most important user journeys through
the browser.

### 5.1 Unit Tests

Unit tests verify isolated behavior close to the code. They should be fast, deterministic,
and focused on business rules, validation, formatting, calculations, and error handling.

Backend unit tests cover service-level logic in:

- `session`
- `wallet`
- `stock`

Frontend unit tests cover reusable UI logic and component behavior in:

- `next-ui`

Unit tests should not depend on real external services, real network calls, browser
automation, or a full Docker stack. Test data should come from explicit fixtures,
factories, or clearly defined input values.

Backend unit tests are normally written in Python `unittest` style and may be collected,
executed, reported, and measured for coverage through `pytest`. In this strategy,
`pytest` as a runner does not by itself make a test a component or integration test. A
test remains a unit test when it invokes isolated Python behavior directly and replaces
external dependencies with mocks or stubs. For example, a Django health-view test that
calls the view function with `RequestFactory` and mocks database or cache probes is a
unit-level view test, while an HTTP request against the running service belongs at the
API/component or integration level.

Backend unit tests should focus on:

- validators
- money calculations
- date and formatting helpers
- authentication/session helper logic
- transaction and brokerage business rules
- parser behavior
- report-building logic
- error and boundary conditions

Frontend unit tests should focus on:

- form validation
- route guard behavior
- API client behavior with mocked responses
- formatting helpers
- loading, empty, and error states
- component rendering for important user states

Financial calculation tests should include boundary value analysis, for example:

- zero amounts
- negative values
- decimal precision
- rounding behavior
- same-day transaction ordering
- empty transaction lists
- missing or invalid input values

Primary evidence:

- `make unit-test`
- `make unit-test-next-ui`
- Allure unit test results
- backend and frontend unit coverage reports

### 5.2 Mocking And Stubbing

Mocks and stubs are used to isolate the tested code from external dependencies.

The preferred approach is:

- `unittest.mock` for Python internal boundaries
- `pytest` fixtures for reusable setup in service-local tests and for component/API or
  integration tests where users, database state, cookies, tokens, and auth headers are
  needed
- HTTP client mocking where external API behavior needs to be simulated
- mocked frontend API responses for Vitest and React Testing Library tests

Mocks must represent real interface contracts. A mock should not invent a response shape
that the real service would never return. If a mock becomes more complicated than the
behavior being tested, the test should be moved to a higher level, such as an API or
integration test.

The purpose of mocking is to make tests stable and focused, not to hide integration
problems.

### 5.3 Component And API Tests

Component and API tests verify public service behavior through HTTP interfaces. They test
the service from the outside, but still focus on one service or one API boundary at a
time.

These tests should verify:

- status codes
- response body structure
- content types
- validation errors
- authentication and authorization behavior
- redirects where applicable
- API contract stability
- expected error responses

Examples:

- login rejects invalid credentials
- protected endpoint rejects anonymous access
- wallet endpoint returns only the authenticated user’s data
- transaction creation validates required fields
- stock quote endpoint returns the expected response shape
- invalid request payload returns a controlled error response

Primary evidence:

- `make component-test`
- Allure component/API test results

Component/API tests that read or mutate persisted `session`, `stock`, or `wallet` data
must run against the database volumes managed by the test runtime. They must not use the
local development database volumes that are kept for manual work, exploratory data, or
backup/restore workflows.

### 5.4 Integration Tests

Integration tests verify that real dependencies work together correctly. They are used
where unit or API tests are not enough because the behavior depends on multiple services,
database state, migrations, cache behavior, routing, or cross-service assumptions.

Integration tests should cover:

- database connectivity
- database migrations
- service readiness
- Docker Compose service dependencies
- Traefik routing
- authentication flow used by another service
- session, wallet, or stock behavior that depends on persisted data
- cache behavior where applicable
- service-to-service assumptions

Examples:

- services start correctly in Docker
- migrations are applied before tests run
- authenticated user can access wallet data after login/session verification
- stock data is stored and later used by report generation
- API routes remain available through the expected local routing layer

Primary evidence:

- `make integration-test`
- Allure integration test results

For `session`, `wallet`, and `stock`, the test runtime starts the services against fresh
test database volumes, applies Django or Alembic migrations during service startup, and
removes those test volumes after the test command finishes. Migration checks are
integration evidence, not unit-test evidence. The test runtime uses a separate Docker
Compose project, `financialmanager_tests`, so test service names and database hostnames
resolve inside the isolated test network rather than to the developer's local stack.
The `test-runner` service starts Traefik and the UI services through Compose
dependencies, which keeps smoke and functional tests on the routed system boundary.

### 5.5 Smoke Tests

Smoke tests are fast checks that verify whether the system is basically alive. They do not
prove that the full system is correct. They only answer whether the local environment is
usable enough for deeper testing.

Smoke tests should cover:

- service health endpoints
- readiness endpoints
- Traefik public routing
- frontend start page
- login or public route availability
- basic API availability

Smoke tests should be small, stable, and quick to run. A smoke test failure usually means
that the environment, routing, startup sequence, or basic service availability is broken.

Primary evidence:

- `make smoke-test`
- Robot Framework smoke report
- Allure smoke test results

### 5.6 Functional End-To-End Tests

Functional end-to-end tests verify important user journeys through the browser. They are
used only for flows where browser behavior, routing, UI state, and backend interaction
must be verified together.

Functional tests should focus on the most important user flows, not every possible UI
detail.

Core journeys:

- open public home page
- register page renders correctly
- login page renders correctly
- protected route redirects anonymous users
- user can create a wallet
- user can add an account
- user can add a transaction
- user can view dashboard data
- user can log out

Functional tests should collect screenshots at each navigation step as confirmation
evidence, not only on failure. Screenshots are embedded directly in the Allure report
using `Take Screenshot    filename=EMBED    fullPage=True` after every `Go To` action.
This makes each step visible to QA without opening a separate file.

Functional tests should also collect traces, logs, or other diagnostics when a failure
occurs. These tests are more expensive than unit or API tests, so they should stay
focused on high-value flows.

Primary evidence:

- `make functional-test`
- Robot Framework results
- browser screenshots embedded in Allure at each navigation step
- Allure functional test results

### 5.7 Security Tests

Security tests focus on the most important security risks for a financial management
application. They are based on selected OWASP ASVS and OWASP WSTG areas, but the goal is
practical verification, not a formal security audit.

Priority areas:

- authentication
- session management
- cookie handling
- authorization and ownership checks
- input validation
- API misuse
- sensitive data exposure
- weak error handling
- import/export abuse
- business logic bypass

Examples:

- user cannot access another user’s wallets, accounts, transactions, or reports
- invalid credentials are rejected safely
- expired or invalid sessions are rejected
- protected endpoints require authentication
- malformed input returns controlled validation errors
- sensitive data is not exposed in error messages
- financial operations cannot be performed for another user’s resources

Security testing evidence can come from automated tests, exploratory test notes, static
analysis, dependency scanning, and documented risk acceptance.

Primary evidence:

- security-focused pytest/API tests
- authorization and session test cases
- documented security findings or exceptions
- static analysis results
- dependency scanning results
- future `make security-test`

### 5.8 Accessibility Tests

Accessibility tests verify that the most important UI flows are usable with basic
accessibility expectations. The target is WCAG 2.2 AA guidance where it is practical for
the application.

Priority areas:

- keyboard navigation
- visible focus state
- form labels
- validation and error messages
- heading structure
- dialog behavior
- color contrast
- responsive layout behavior
- screen-reader friendly state changes where applicable

Automated accessibility checks are useful, but they do not replace manual review. Core
flows should also be checked manually with keyboard navigation because automated tools do
not detect every usability or accessibility problem.

Primary evidence:

- manual keyboard review notes
- frontend component tests where applicable
- future axe-based automation
- future `make accessibility-test`

### 5.9 Performance Tests

Performance tests focus on the flows where poor performance would reduce usability or
trust. The goal is not to create artificial benchmark numbers, but to define realistic
local budgets and detect obvious regressions.

Local Docker performance budgets:

| Endpoint / Flow | Budget |
| --- | --- |
| Health and readiness endpoints | p95 < 100 ms |
| Dashboard and account summary API | p95 < 500 ms |
| Transaction list and holdings API | p95 < 800 ms |
| AI-backed report generation | < 10 s, with explicit timeout and controlled error response |
| Major UI pages, Largest Contentful Paint | < 2.5 s on a standard local machine |

These budgets apply to the local Docker environment under no intentional concurrent load.
They are not production SLAs. If a flow consistently exceeds its budget, it should be
treated as a performance issue and investigated.

Primary evidence:

- focused performance checks for high-risk flows
- documented performance results
- future `make performance-test`

## 6. Risk-Based Prioritization

FinancialManager uses risk-based test prioritization. Not every area of the application
has the same impact if it fails, so test effort is focused first on the parts that can
cause data loss, incorrect financial results, unauthorized access, or loss of user trust.

Risk priority is based on three factors:

- impact of failure
- probability of defects
- cost of finding the defect late

The highest priority is given to features connected with authentication, authorization,
financial data integrity, money calculations, transaction lifecycle, brokerage flows, and
sensitive data handling.

| Risk Area | Priority | Reason | Expected Test Response |
| --- | --- | --- | --- |
| Authentication and session security | Critical | A broken login or session flow can expose private financial data or allow unauthorized access. | Unit, API, integration, and security-focused tests. |
| Authorization and ownership checks | Critical | Users must never access another user’s wallets, accounts, transactions, reports, or stock-related data. | API tests, negative authorization tests, and cross-user access checks. |
| Money calculations | Critical | Incorrect balances, cash effects, gains, losses, or rounding behavior directly break product trust. | Unit tests with boundary values, decimal precision checks, and business-rule tests. |
| Transaction lifecycle | Critical | Create, update, delete, import, and categorization flows must preserve financial integrity. | Unit, API, and integration tests for normal and error paths. |
| Brokerage buy/sell flows | Critical | Cash balance, holdings, average price, realized gains, and portfolio value depend on correct logic. | Unit tests for business rules, API tests, and integration tests with persisted data. |
| Sensitive financial data handling | Critical | Financial data must not be exposed through API responses, logs, errors, or unauthorized routes. | Security tests, API misuse tests, log/error review, and negative test cases. |
| Data import/export | High | Parsing, mapping, or export defects can corrupt financial records or expose data. | Parser tests, validation tests, malformed-file tests, and controlled failure checks. |
| Quotes and instruments | High | Market data affects dashboards, reports, alerts, and user decisions. | Parser tests, API tests, cache tests, and failure-mode tests for unavailable data. |
| AI report generation | High | AI-supported reports must handle prompts, input data, caching, timeouts, and failure cases safely. | Unit/API tests for prompt construction, sanitization, timeout handling, and controlled errors. |
| UI forms and route protection | High | Users must see correct validation, safe navigation, and protected-route behavior. | Frontend unit tests, route guard tests, and functional browser tests for core flows. |
| Database migrations and backup/restore assumptions | High | Schema changes and recovery assumptions affect data availability and long-term maintainability. | Migration checks, integration tests, and documented recovery assumptions. |
| API contracts | High | Frontend and backend must agree on request/response behavior. | API/component tests, response-shape checks, and error-contract tests. |
| Accessibility of core flows | Medium | Accessibility issues reduce usability and professional quality, especially in forms and navigation. | Keyboard checks, focus checks, label/error checks, and future axe automation. |
| Performance of core flows | Medium | Slow dashboards, transaction lists, reports, or stock data views reduce trust and usability. | Local performance budgets and focused performance checks. |
| Low-risk visual details | Low | Small visual defects usually do not affect financial correctness or data safety. | Manual review, frontend component tests only when the behavior is reusable or important. |

Risk priority decides where testing effort should go first. Critical areas should have
automated tests before they are considered stable. High-risk areas should have automated
coverage for the main success path and the most important failure paths. Medium-risk
areas should be tested where they affect core user experience. Low-risk areas may be
covered by manual review unless they are repeated often or likely to regress.

A low coverage number is acceptable only when the risk is also low or when the gap is
tracked as known work. For critical areas, coverage gaps should be visible in the test
backlog or linked GitHub issues.

## 7. Coverage Policy

Coverage is used as one of the quality signals for FinancialManager, but it is not treated
as the only measure of test quality. A high coverage number is useful only when the tests
verify meaningful behavior and cover the areas where defects would have real impact.

The long-term target for production code is:

- 90% line coverage
- 90% branch coverage
- generated files, migrations, configuration-only files, and boilerplate code excluded
  where appropriate

Branch coverage shows whether tests execute the important decision paths inside the code,
not only individual lines. For example, if the code has an `if/else` condition, tests
should cover both outcomes where it matters. In this strategy, branch coverage is not
related to Git branches.

Coverage gates are applied gradually. The goal is to increase confidence without forcing
artificial tests that only improve the percentage. Coverage should increase when real
tests are added for important behavior.

### 7.1 Current Coverage Gates

The current coverage gates are staged per backend service. `next-ui` coverage is reported
as a separate frontend baseline until enough meaningful UI and client tests exist to set
a non-arbitrary gate.

| Area | Current Gate | Reason |
| --- | ---: | --- |
| `stock` | 55% | Market-data parser, mapping, GPW client, and historical-browser helper tests have expanded coverage beyond equity reports. |
| `wallet` | 8% | Validators, money/date edge cases, API dependency helpers, and auth/stock client error paths now support a higher starting gate. |
| `session` | 25% | Crypto, HMAC, 2FA, IP allow-list, throttle, middleware, and health tests now support a stronger security baseline. |
| `next-ui` | Report only | Frontend coverage is generated through Vitest, but no gate is enforced until the baseline reflects route guards, forms, API clients, and key UI states. |

The backend gates use branch coverage and service-local `.coveragerc` files. Those
configuration files define explicit `source` scopes so behavior-bearing Python files that
are never imported by the current unit tests still appear in coverage as 0%. They also
use report `include` rules to keep the visible report focused on production service
code. Generated files, migrations, configuration-only files, and mostly declarative
framework wiring such as models, schemas, admin setup, and URL wiring are intentionally
excluded when import-time execution would inflate the percentage without proving
behavior. Validators, helpers, view logic, service logic, financial rules, parsers,
clients, middleware, and other behavior-bearing production code remain in scope.
`next-ui` uses Vitest V8 coverage and publishes HTML coverage beside the backend reports.

The generated coverage overview is published under the Allure artifact at
`/coverage/`. It separates:

- global service coverage, which measures all included production code for a service
- domain/module coverage, which slices coverage by path groups so one well-tested module
  does not hide weak coverage elsewhere
- changed-code coverage, which reports coverage for executable lines added or modified
  in the current Git diff and uses 80% as the PR-review target

For Python services, the overview reads line and branch data from `coverage.xml` and
function-level data from the generated `coverage.py` HTML function index. A Python
function is counted as covered in the overview when at least one executable statement in
that function was covered by the current test run.

Changed-code coverage is currently reported as evidence. It is not an enforced gate until
the CI/CD quality workflow explicitly adds that check.

The current values are not final quality targets. They are starting gates that prevent
coverage from silently decreasing while the test suite is improved.

### 7.2 Wallet Risk Acknowledgment

`wallet` currently has the lowest coverage and the highest business risk. It contains
money calculations, transaction lifecycle, brokerage flows, holdings, gains, alerts,
recurring expenses, debts, goals, and other financial behavior.

The current `wallet` gate is accepted only as a measured starting point. It does not mean
that wallet quality is considered complete.

Wallet testing is the first coverage priority. Before new wallet functionality is treated
as stable, the related behavior should have automated tests for the main success path,
important validation paths, and important failure paths.

The next target for `wallet` is Stage 2 coverage.

### 7.3 Ratchet Plan

Coverage should be increased gradually after meaningful tests are added. The gate should
not be raised only to make the project look better. It should be raised when the suite
actually protects important behavior.

| Stage | Stock | Wallet | Session | Meaning |
| --- | ---: | ---: | ---: | --- |
| Stage 1 | 55% | 8% | 25% | Current measured baseline with branch coverage enabled and first risk-focused unit expansion. |
| Stage 2 | 70% | 25% | 40% | Priority unit tests added for the most important service logic. |
| Stage 3 | 80% | 60% | 65% | API/component and integration tests added for important flows. |
| Stage 4 | 90% | 90% | 90% | Mature target for line and branch coverage on production code. |

A coverage gate can be raised only when:

- the new tests verify real behavior
- critical paths are not skipped
- generated and boilerplate files are handled consistently
- the test suite remains stable
- the change is reflected in the Make target or CI/CD quality check

### 7.4 Critical Module Expectations

Critical modules should reach strong coverage before the whole service reaches the final
target. This prevents the project from having good average coverage while risky areas
remain weak.

Critical module targets:

- `session`: authentication, blocking, session verification, cookies, HMAC, 2FA, logout,
  and admin/security paths.
- `wallet`: money calculations, validators, accounts, transactions, holdings, brokerage
  flows, gains, alerts, debts, goals, and recurring expenses.
- `stock`: reports, quotes, instruments, parsers, scraping failure modes, caching, and
  prompt-safety-related logic.
- `next-ui`: route guards, login/register forms, API clients, dashboard states, money/date
  formatting, chart/report behavior, and protected route behavior.

### 7.5 Coverage Review Rules

Coverage reports should be reviewed together with the changed code. The important question
is not only whether the percentage passed, but whether the changed behavior is protected
by the right test level.

A coverage gap is acceptable when:

- the code is low risk
- the behavior is covered at a higher test level
- the code is configuration-only or boilerplate
- the gap is known and tracked for later work

A coverage gap is not acceptable when it affects:

- authentication or session security
- authorization or ownership checks
- money calculations
- transaction lifecycle
- brokerage buy/sell behavior
- sensitive financial data handling
- data import/export behavior
- critical API contracts

## 8. Entry And Exit Criteria

Entry and exit criteria define when work is ready to start, when a change is acceptable,
and when the project has enough test evidence for a release candidate.

The goal is not to create a heavy approval process. The goal is to make quality decisions
clear, repeatable, and based on risk.

### 8.1 Development Entry Criteria

Before implementing or changing a feature, the following should be clear:

- what behavior is expected
- which service, UI area, or API contract is affected
- whether the change touches authentication, authorization, money calculations, financial
  data, or user ownership rules
- what risk level the change has
- which test level is most appropriate
- what test data, fixtures, factories, or mocks are needed
- whether existing tests should be updated

For low-risk changes, this can be a quick mental check. For high-risk changes, especially
in `session`, `wallet`, or financial reporting logic, the expected behavior and test
approach should be visible in the code change, test names, or linked GitHub issue.

### 8.2 Local Change Exit Criteria

Before a change is considered locally acceptable:

- relevant unit tests pass
- affected API, component, or integration tests pass where applicable
- `make quality-test` passes for the touched area
- coverage does not decrease without a clear reason
- critical behavior touched by the change has automated test coverage
- security-sensitive changes include negative tests where practical
- Allure results are generated for executed automated suites
- new or changed tests are deterministic and do not depend on hidden local state

A change may still be accepted with a known gap, but the gap should be visible as a GitHub
issue, TODO, documented exception, or test backlog item.

#### Test Oracle Integrity

Tests should verify the intended business rule, API contract, or user-visible behavior,
not simply mirror whatever the current implementation happens to do. When the product
logic says that an operation should be rejected, such as a duplicate user-owned resource,
the test should assert the rejection even if the current code still accepts it.

If a meaningful test fails because the implementation is wrong, the failure is useful
evidence. Do not change the expected result only to make the suite green. Fix the
production behavior, update the API/UI contract where needed, or document the gap as
accepted work. A failing test that protects a real invariant is preferable to a passing
test that silently legalizes a defect.

### 8.3 Pull Request Exit Criteria

If the project uses pull requests, the pull request should meet the same quality criteria
as local acceptance.

Before merging a pull request:

- CI/CD quality checks pass in GitHub Actions
- the same Make targets used locally are executed in CI where practical
- test and coverage artifacts are available
- failed or skipped tests are understood
- critical or high-risk changes have appropriate automated coverage
- any accepted risk is documented in the pull request, GitHub issue, or test backlog

Pull requests are not required by the strategy, but when they are used, they should act as
a review point for code, tests, coverage, and risk.

### 8.4 Release Candidate Exit Criteria

Before a release candidate is considered ready:

- `make test-all` passes
- `make coverage-unit` passes
- GitHub Actions quality checks are green
- critical authentication and authorization checks pass
- critical wallet and money-calculation checks pass
- important transaction and brokerage flows pass
- known critical or high security findings are fixed or explicitly accepted
- critical accessibility blockers are fixed or explicitly accepted
- Allure report is available
- coverage report is available
- important known gaps are documented

A release candidate should not be treated as ready if there is an unresolved critical
defect in authentication, authorization, money calculations, transaction integrity, or
sensitive financial data handling.

## 9. Test Data Strategy

Test data must be deterministic, isolated, and easy to understand. The purpose of test
data is not only to make tests pass, but also to make the tested business scenario clear.

FinancialManager uses test data for users, sessions, wallets, accounts, transactions,
brokerage operations, instruments, quotes, reports, and UI flows. Test data should be
created in a repeatable way so that tests can run locally and in CI/CD with the same
expected result.

### 9.1 General Rules

Test data should follow these rules:

- use factories or explicit fixtures for users, wallets, accounts, transactions,
  instruments, quotes, holdings, cookies, tokens, and auth headers
- avoid random values unless the random generator is seeded
- avoid real credentials, real API keys, real tokens, and production-like secrets
- avoid real external network dependencies in unit tests
- isolate data between tests
- clean or recreate database state where needed
- never treat the developer's local `session`, `stock`, or `wallet` databases as
  disposable test fixtures when they are used for manual work, exploratory data, or
  backups
- make expected values visible in the test
- use clear names that explain the business scenario
- keep test data close to the test when it improves readability
- move repeated setup into fixtures or factories when it is reused often

A test should make the business intent visible. For example, a transaction test should
show the opening balance, transaction amount, expected cash effect, and final balance.

### 9.2 Test Data By Test Level

Different test levels require different test data.

| Test Level | Test Data Approach |
| --- | --- |
| Unit tests | Use direct input values, factories, and mocks. Keep data minimal and focused on one rule or branch. |
| API/component tests | Use realistic request payloads, auth headers, cookies, and database fixtures where needed. |
| Integration tests | Use persisted test data that verifies database, service, cache, and routing behavior together. |
| Smoke tests | Use only the minimum data needed to check that the system is alive. |
| Functional end-to-end tests | Use stable user accounts and clear UI-visible data that can be created, verified, and cleaned up. |
| Security tests | Use negative data, invalid tokens, cross-user resources, malformed payloads, expired sessions, and unauthorized access scenarios. |
| Performance tests | Use repeatable datasets large enough to expose slow behavior, but still realistic for local Docker execution. |

### 9.3 Financial Test Data

Financial data requires extra care because small mistakes in amounts, precision, dates, or
ordering can hide real defects.

Financial tests should include data for:

- zero amounts
- positive and negative amounts
- decimal precision
- rounding behavior
- multiple currencies where applicable
- same-day transaction ordering
- empty account or wallet state
- account balance updates
- transaction create, update, and delete behavior
- brokerage buy and sell operations
- holdings, average price, realized gain, and unrealized gain
- report calculations

Money-related tests should use explicit expected values. The expected result should not be
calculated in the test with the same logic as the production code, because that can hide
the same defect in both places.

### 9.4 User And Authorization Data

Tests that verify authentication, authorization, and ownership rules should use separate
users with clearly separated data.

Example test setup:

- `user_a` owns wallet A, account A, and transactions A
- `user_b` owns wallet B, account B, and transactions B
- `user_a` must not be able to access or modify data owned by `user_b`

Authorization test data should cover:

- anonymous user
- authenticated user
- user with valid session
- user with expired or invalid session
- user accessing own data
- user trying to access another user's data
- blocked user where applicable
- 2FA-related states where applicable

These tests are especially important for `session`, `wallet`, reports, and any endpoint
that returns sensitive financial data.

### 9.5 API And Integration Test Data

API and integration tests should use realistic but controlled data. The goal is to verify
service behavior, database state, response shape, and error handling without depending on
hidden local state.

API and integration test data should cover:

- valid request payloads
- missing required fields
- invalid field types
- invalid IDs
- invalid ownership
- duplicate records where applicable
- database persistence
- migration assumptions
- controlled error responses

Integration tests may use Docker-based services and a real database, but the data should
still be created and cleaned in a repeatable way.

For `session`, `wallet`, and `stock`, the real database used by component, integration,
and functional tests is the fresh test database volume created by
`tests/docker/run_with_test_runtime.sh`. It is intentionally separate from the ordinary
development database volumes used for manual work and backups. Inside the test runtime,
the service env points to test database hosts such as `session-db`, `wallet-db`, and
`stock-db` on the isolated `financialmanager_tests` network.

The current system-test runtime should be treated as a dedicated test environment, not a
parallel companion to the local development stack. Stop the normal dev stack before
running `make test-all` or the individual system-test targets. This keeps Traefik routing
and Docker provider discovery deterministic while still protecting local development
database volumes from test data.

### 9.6 External And Market Data

Tests must not depend on live external market data for normal automated execution. Live
market data can change, become unavailable, or return different results depending on time,
network, or provider behavior.

For automated tests, market data should be represented by:

- fixed quote fixtures
- saved parser input samples
- mocked HTTP responses
- controlled failure responses
- explicit cache scenarios
- known instrument examples

Live external calls may be used only in dedicated exploratory checks or manually triggered
tests, not as a requirement for the default quality gate.

### 9.7 Frontend Test Data

Frontend tests should use predictable data that represents the UI state being tested.

Frontend test data should cover:

- empty dashboard state
- loading state
- error state
- wallet with no accounts
- wallet with accounts
- account with transactions
- form validation errors
- protected route behavior
- report or chart data
- API client success and failure responses

For component tests, mocked API responses should match real backend response shapes. If a
mocked response does not match the real API contract, the test can become misleading.

### 9.8 Test Data Privacy

Test data must not contain real private financial information, real bank account data,
real credentials, real tokens, or real personal data.

Safe test data should be artificial and clearly marked as test-only. Example values may
look realistic enough to support testing, but they must not be copied from real users,
real accounts, or real production data.

### 9.9 Test Data Review

When a test fails, the test data should make it easy to understand what scenario was
being verified. If the setup is too large, unclear, or repeated in many places, it should
be simplified or moved into a reusable fixture or factory.

Test data should be reviewed when:

- a new financial rule is added
- a new API contract is introduced
- authorization behavior changes
- import/export behavior changes
- a bug is caused by missing edge-case data
- tests become difficult to read or maintain

## 10. Reporting And Evidence

Reporting and evidence are used to make test results visible, repeatable, and reviewable.
The goal is not to create heavy documentation, but to keep enough evidence to understand
what was tested, what passed, what failed, and where the remaining risks are.

FinancialManager uses repository-based evidence. Test execution, coverage, reports, and
accepted gaps should be traceable through Make targets, Allure reports, coverage reports,
GitHub issues, and GitHub Actions artifacts.

### 10.1 Evidence Sources

The main sources of testing evidence are:

- automated test results
- Allure reports
- coverage reports
- Robot Framework reports, logs, screenshots, and traces
- Make target execution
- GitHub Actions workflow results
- GitHub Actions artifacts
- GitHub issues for defects, risks, accepted exceptions, and follow-up work
- Markdown documentation for test strategy, roadmap, and quality decisions

Evidence should be generated from repeatable commands. The same quality flow should be
executable locally and in CI/CD.

### 10.2 Local Reporting

Local test execution is managed through Make targets. These targets define the standard
commands used to run tests and generate reports.

Current quality commands:

- `make unit-test`
- `make unit-test-next-ui`
- `make smoke-test`
- `make functional-test`
- `make component-test`
- `make integration-test`
- `make coverage-unit`
- `make quality-test`
- `make test-all`
- `make allure-up`

Allure is served locally at:

http://localhost:5252

Coverage reports are served beside Allure at:

http://localhost:5252/coverage/

Local reports are useful for development review, debugging, test improvement, and
checking whether a change is ready before pushing it to the repository.

### 10.3 CI/CD Reporting

GitHub Actions is the CI/CD execution layer for the same quality flow that is available
locally through Make targets.

CI/CD reporting should provide:

- workflow status for quality checks
- test execution results
- coverage results
- Allure result artifacts
- coverage HTML artifacts
- Robot Framework failure artifacts where applicable
- logs needed to investigate failed jobs

The purpose of CI/CD reporting is to confirm that the project can be tested in a clean,
repeatable environment, not only on one local machine.

### 10.4 Allure Reporting Rules

Allure is used as the main human-readable test report.

Tests should use Allure metadata where it improves readability and traceability.

Required metadata on every test class:

- `epic`: service or quality area, for example `Wallet`, `Session`, `Stock`, `Next UI`,
  `Security`, or `Integration`
- `feature`: tested domain, for example `Transactions`, `Authentication`, `Quotes`,
  `Reports`, or `Route Protection`
- `story`: tested behavior, for example `Login rejects invalid credentials`
- `severity`: risk-based importance of the test
- `tag`: one or more cross-cutting labels for filtering, for example `security`, `auth`,
  `financial-data`, `money`, `reports`, `ai`, `parsing`, `middleware`, `health`, `utils`
- `link`: a link to the GitHub project repository so QA can navigate directly from a failed
  test result to the repository

Optional metadata:

- `description`: a short explanation of the business scenario or invariant being tested.
  Add this when the class name and story line alone do not make the tested logic clear,
  for example for multi-step financial calculations, AI retry strategies, or sanitizer
  fallback logic.
- `issue`: a link to a specific GitHub issue when a test is tracking a known defect or
  open work item. Add this when the issue exists; do not invent placeholder links.

Severity must be assigned based on business or technical risk, not mechanically.

Suggested severity meaning:

| Severity | Meaning |
| --- | --- |
| Blocker | Failure blocks release readiness, for example broken authentication, authorization, or critical money calculation. |
| Critical | High-impact product behavior is broken, for example transaction lifecycle, brokerage logic, or sensitive data handling. |
| Normal | Important behavior is affected, but there is no immediate critical security or financial integrity risk. |
| Minor | Low-risk behavior, formatting, or non-critical UI behavior. |

### Failure Categories

Allure categories are defined in `categories.json` injected during report generation.
They classify failures so QA can prioritize investigation without reading every error.

| Category | Matched status | Meaning |
| --- | --- | --- |
| Infrastructure Issues | broken | Service connectivity or timeout errors — environment problem, not a code defect. |
| Test Defects | broken | Unexpected exception in test code — test setup or fixture problem. |
| Product Defects | failed | Assertion failure — the application did not behave as expected. |
| Skipped – Known Gap | skipped | Intentionally skipped test with a documented reason. |

### Environment Panel

The environment panel in every Allure report shows:

- `Environment`: where the tests ran (for example `local-docker`)
- `Git branch` and `Git commit`: which code was tested
- `Report generated`: when the report was created
- Coverage report links for each service

Allure reports should help answer:

- what was tested
- which area failed
- how important the failure is
- whether the failure is related to a known risk
- where to start debugging

### 10.5 Coverage Evidence

Coverage reports are used to show which production code is exercised by automated tests.
Coverage is reviewed together with risk, not as a standalone quality result.

Coverage evidence should show:

- line coverage
- branch coverage
- service-level coverage gates
- excluded files or patterns
- coverage changes after new tests are added

Coverage reports should not be used to hide missing risk coverage. A service can have a
passing coverage percentage and still require more tests if critical behavior is not
covered.

### 10.6 Failure Evidence

When tests fail, the report should provide enough information to investigate the failure
without guessing.

Failure evidence may include:

- assertion error
- request and response details where safe
- application logs
- service logs
- browser screenshot embedded inline in the Allure report
- browser Playwright trace zip attached to the Allure result, openable at
  https://trace.playwright.dev for step-by-step failure replay
- Robot Framework log
- Allure failure details
- CI job logs

Functional end-to-end tests attach a Playwright trace automatically when a suite fails.
Each suite should use the Python keywords `Open Next Ui Browser` and
`Close Browser And Keep Failure Artifacts` from
`tests/functional_tests/TestKeywords/browser_keywords.py`. The trace is not attached for
passing suites.

Sensitive data must not be included in reports, logs, screenshots, or artifacts.

This includes:

- real passwords
- real tokens
- real cookies
- real API keys
- real personal financial data
- sensitive user-specific financial history

### 10.7 Accepted Gaps And Exceptions

Not every gap has to block development, but important gaps should be visible.

Accepted gaps should be tracked through one of the following:

- GitHub issue
- test backlog item
- documented exception in Markdown
- comment in the related test or configuration
- pull request note where applicable

An accepted gap should explain:

- what is not covered
- why it is accepted for now
- what risk it creates
- what should be done later

Critical gaps in authentication, authorization, money calculations, transaction integrity,
or sensitive data handling should not be silently accepted.

### 10.8 Evidence Review

Before a change is considered ready, the evidence should answer these questions:

- Did the relevant tests run?
- Did the expected test levels pass?
- Did coverage stay the same or improve?
- Are failures, skipped tests, or quarantined tests understood?
- Are known gaps documented?
- Is there enough evidence for the risk level of the change?

The reporting process should support engineering decisions. It should make quality status
clear without requiring a separate test-management tool.

## 11. Tooling

FinancialManager uses a small set of tools that support local execution, automated
testing, reporting, coverage, and future CI/CD quality checks.

The tooling is selected to keep the test workflow repeatable from the repository. The
same commands should be usable locally and in GitHub Actions.

### 11.1 Current Tools

| Tool | Usage |
| --- | --- |
| Python `unittest` | Used for backend unit tests where isolated Python logic is tested close to the code. |
| `unittest.mock` | Used for backend unit-test mocking, patching, and replacing internal dependencies. |
| `pytest` | Used as the Python test runner for service-local backend unit tests and as the main framework for backend component, API, and integration tests. For unit tests, it may discover and execute `unittest`-style tests where configured. |
| `pytest` fixtures | Used for reusable test setup, database state, auth headers, cookies, test users, and service-level test data. |
| `pytest-cov` | Used for Python line and branch coverage reporting. |
| Vitest | Used for frontend unit tests in `next-ui`. |
| `@vitest/coverage-v8` | Used for `next-ui` frontend unit coverage reporting. |
| React Testing Library | Used for testing React component behavior from the user perspective. |
| Robot Framework | Used for smoke and functional test execution. |
| Robot Framework Browser / Playwright | Used for browser-based functional tests and UI journey verification. |
| Allure | Used for human-readable test reporting and test execution evidence. |
| Docker Compose | Used for reproducible local runtime and integration test environments. |
| Make | Used as the standard command layer for local and CI/CD test execution. |
| Python compile checks | Used as a lightweight backend quality check. |
| ESLint | Used for frontend linting. |
| TypeScript typecheck | Used for frontend static type verification. |

### 11.2 Tooling Rules

Tools should support the testing strategy, not replace it. A tool is useful only when it
helps make tests more repeatable, readable, maintainable, or easier to diagnose.

General rules:

- backend unit tests should stay close to Python logic, normally use `unittest` style,
  and may be run by `pytest` for discovery, Allure reporting, and coverage
- backend component, API, and integration tests should use `pytest`
- Python coverage should be collected with `pytest-cov`
- frontend unit tests should use Vitest and React Testing Library
- frontend unit coverage should be collected with Vitest V8 coverage
- smoke and browser functional tests should use Robot Framework with Browser / Playwright
- Allure should be used to collect and review test execution evidence
- Docker Compose should be used when real service dependencies are required
- Make targets should be the main interface for running quality checks

The preferred flow is:

- use `unittest` style for isolated backend Python logic
- use `pytest` as the Python runner, with `pytest`-style tests for service/API and
  integration-level execution
- use Robot Framework for smoke and browser-level functional tests
- use Allure and coverage reports as evidence

### 11.3 Planned Tooling Additions

The following tools may be added where they provide practical value:

| Tool | Intended Usage |
| --- | --- |
| `pytest-mock` | Cleaner mock assertions and fixture-based mocking where it improves readability. |
| `responses` or `respx` | HTTP client mocking for backend tests that need to simulate external API behavior. |
| MSW / Mock Service Worker | Frontend API mocking for Vitest and React Testing Library tests. |
| `bandit` | Python static security analysis. |
| `pip-audit` | Python dependency vulnerability scanning. |
| axe tooling | Automated accessibility checks for selected UI flows. |
| `semgrep` | Additional static analysis rules for security-sensitive or risky code paths. |
| focused performance tooling | Local performance checks for high-risk API and UI flows. |

Planned tools should be added only when they solve a real problem. The project should
avoid adding tools that increase maintenance cost without improving confidence, diagnosis,
or repeatability.

### 11.4 Tooling Evidence

Tooling evidence should be visible through:

- Make target output
- Allure reports
- coverage reports
- Robot Framework logs and screenshots
- GitHub Actions workflow results
- GitHub Actions artifacts
- documented exceptions or follow-up issues when a tool reports a known gap

The tooling setup should make it possible to understand whether a failure is caused by
application logic, test data, environment setup, service dependencies, or test instability.

## 12. CI/CD Quality Workflow

GitHub Actions is the CI/CD execution layer for the FinancialManager quality workflow.
The same Make targets used locally should also be used in CI/CD, so the repository has one
consistent way to run tests, coverage checks, and reporting.

The purpose of CI/CD is to verify that the project can be tested in a clean, repeatable
environment and that quality evidence is generated outside the local development machine.

The main workflow should live at:

.github/workflows/quality.yml

The workflow should run on every push to `main` and be available through manual dispatch.
This repository does not require a pull-request workflow for the current one-person
development model.

### 12.1 Implemented CI/CD Quality Workflow

The implemented GitHub Actions workflow is `.github/workflows/quality.yml`. It runs on
push to `main` and through manual dispatch. The workflow uses the
repository Make targets instead of duplicating test commands:

- `make quality-test`
- `make test-all`

The workflow includes:

- Python compile checks for backend services
- ESLint checks for `next-ui`
- TypeScript typecheck for `next-ui`
- backend unit tests written in Python `unittest` style and collected through the
  service `pytest` targets
- frontend unit tests using Vitest and React Testing Library
- coverage gates enforced at the current stage thresholds
- Allure result generation
- coverage report generation
- upload of Allure results as GitHub Actions artifacts
- upload of coverage HTML reports as GitHub Actions artifacts
- upload of Robot output, browser diagnostics, and the `next-ui` npm audit JSON report

These checks are the main automated quality gate for the repository.

### 12.2 Component, Integration, And Smoke Checks

Component, integration, and smoke tests should use the Docker-based runtime where real
service dependencies are required.

These checks should include:

- component/API tests with `make component-test`
- integration tests with `make integration-test`
- smoke tests with `make smoke-test`
- service readiness checks
- database migration checks
- Traefik routing checks where applicable
- fresh `session`, `wallet`, and `stock` test database volumes for stateful test runs

These checks may run on every push when execution time is acceptable. If they become too
slow, they can run on selected branches, manually, or before release candidates.

### 12.3 Functional End-To-End Checks

Functional end-to-end tests verify browser-level user journeys and are more expensive
than unit or API tests.

The CI/CD strategy for functional tests is:

- keep the suite focused on critical user journeys
- collect screenshots, traces, and Robot Framework logs on failure
- run them before release candidates
- optionally run them manually or on demand when the workflow is too slow for every push

Functional tests should not replace lower-level tests. They should confirm that the most
important user journeys work through the full application stack.

### 12.4 Security And Dependency Checks

Security checks should be added to CI/CD where they provide practical value.

The expected checks are:

- `bandit` for Python static security analysis
- `pip-audit` for Python dependency vulnerability scanning
- selected security-focused API tests
- future `semgrep` rules for security-sensitive code paths

Security findings should be reviewed according to risk. Critical findings related to
authentication, authorization, session handling, sensitive data exposure, or financial
data integrity should block release readiness unless they are explicitly accepted.

### 12.5 Accessibility And Performance Checks

Accessibility and performance checks are part of the quality workflow, but they do not
need to be the first blocking CI/CD gates.

Accessibility checks should focus on:

- keyboard navigation
- focus visibility
- form labels
- validation messages
- contrast issues
- selected axe-based automation

Performance checks should focus on the local budgets defined in the test levels section.

These checks may run manually, on demand, or before release candidates until they become
stable enough to run automatically.

### 12.6 Artifact Retention

Each CI/CD run should keep enough evidence to review the result later.

Expected artifacts:

- Allure test results
- coverage HTML reports
- Robot Framework reports
- screenshots and traces for functional test failures
- logs needed to investigate failed jobs

Artifact retention should be configured in GitHub Actions. A short retention period is
acceptable as long as release candidate evidence is preserved when needed.

### 12.7 CI/CD Readiness Rule

A change should not be treated as ready if the required CI/CD quality checks are failing
or if a critical failure is not understood.

For release candidates, the workflow should provide enough evidence to answer:

- Did the expected tests run?
- Did coverage gates pass?
- Are critical workflows verified?
- Are security-sensitive failures resolved or explicitly accepted?
- Are reports and artifacts available?

## 13. Priority Test Backlog

The test backlog is prioritized by product risk, current coverage, and the impact of a
defect on user trust. The goal is to add tests where they provide the highest value first,
not to distribute testing effort equally across all services.

The highest priority is given to areas connected with money calculations, transaction
integrity, authentication, authorization, and sensitive financial data handling.

### 13.1 Wallet First

`wallet` is the first testing priority because it contains the highest business risk and
currently has the lowest coverage gate.

The first goal for `wallet` is to protect the most important financial behavior with
automated tests before increasing the coverage gate to the next stage.

Priority areas:

- money and date utilities
- validators
- wallet CRUD
- account CRUD
- transaction creation
- transaction update
- transaction deletion
- transaction categorization
- transaction lifecycle rules
- balance calculations
- cash effects
- brokerage buy flows
- brokerage sell flows
- holdings calculation
- average price calculation
- realized and unrealized gains
- alerts
- recurring expenses
- debts
- financial goals

Expected test focus:

- unit tests for money calculations and business rules
- API/component tests for wallet, account, transaction, and brokerage endpoints
- integration tests for persisted financial data
- negative tests for invalid input and ownership violations
- boundary tests for zero amounts, negative values, decimal precision, and rounding

Wallet tests should make the financial scenario visible. For example, a transaction test
should clearly show the opening balance, transaction amount, expected cash effect, and
final balance.

### 13.2 Session Second

`session` is the second testing priority because authentication and session behavior
protect access to private financial data.

Priority areas:

- registration validation
- login success
- login failure
- logout behavior
- temporary user blocking
- permanent user blocking
- session verification
- HMAC/session cookie handling
- invalid cookie handling
- expired session handling
- 2FA flows
- admin and security-related paths

Expected test focus:

- unit tests for authentication helper logic
- API/component tests for login, logout, registration, and session verification
- negative tests for invalid credentials, expired sessions, and malformed cookies
- authorization tests for protected endpoints
- security-focused tests for session and cookie misuse

A successful login test is not enough. The backlog must also include negative tests that
prove invalid users, expired sessions, and unauthorized requests are rejected safely.

### 13.3 Stock Third

`stock` is the third testing priority because stock data affects reports, dashboards,
alerts, and user decisions. The risk is high, but it is lower than direct wallet integrity
and access control.

Priority areas:

- instruments
- latest quotes
- market parser edge cases
- report builder logic
- report service branches
- AI prompt construction
- input sanitization
- cache behavior
- unavailable market data
- scraping failure modes
- browser/scraper timeout handling
- malformed external data

Expected test focus:

- unit tests for parsers, report builders, and prompt construction
- mocked tests for external market data responses
- API/component tests for quote and instrument endpoints
- failure-mode tests for missing fields, malformed values, empty responses, and timeouts
- integration tests where stock data is persisted and later used by reports

Stock tests should not depend on live external market data unless the test is explicitly
marked as an external/system check.

### 13.4 Next UI In Parallel

`next-ui` should be tested in parallel with backend work because it is the main user-facing
layer. UI tests should focus on user behavior, not implementation details.

Priority areas:

- login form
- registration form
- route guards
- protected route behavior
- API clients
- money formatting
- date formatting
- dashboard empty states
- dashboard loading states
- dashboard error states
- chart and report rendering
- wallet/account/transaction forms
- validation messages
- logout behavior
- accessibility of core flows

Expected test focus:

- Vitest and React Testing Library tests for forms, route guards, helpers, and important
  UI states
- mocked API responses for frontend unit tests
- Robot Framework browser tests for critical user journeys
- accessibility checks for keyboard navigation, labels, focus behavior, and error messages

Frontend tests should verify what the user can see or do. They should avoid testing
internal component implementation unless the behavior is reusable and important.

### 13.5 Backlog Ordering Rule

The backlog should be ordered by risk, not by convenience.

The recommended order is:

1. `wallet` money calculations and transaction lifecycle
2. `wallet` brokerage and holdings logic
3. `session` authentication, session verification, and logout
4. `session` blocking, cookies, HMAC, and 2FA
5. `wallet` API/component tests for ownership and validation
6. `stock` parsers, quotes, reports, and failure modes
7. `next-ui` route guards, forms, dashboard states, and API clients
8. smoke and functional tests for the most important user journeys
9. security-focused negative tests
10. accessibility and performance checks for core flows

A backlog item should include enough information to understand:

- what behavior needs testing
- which risk it reduces
- which test level should cover it
- what evidence should exist when it is done

### 13.6 Definition Of Done For Test Backlog Items

A test backlog item is considered done when:

- the expected behavior is covered by the right test level
- the test is deterministic
- the test data is clear
- the test can run through the relevant Make target
- the result is visible in Allure or coverage reports where applicable
- the test does not depend on hidden local state
- the test protects a real behavior, not only a coverage percentage

Backlog items that cover critical behavior should not be closed only because a test was
added. They should be closed when the important success path and the most important failure
path are both covered.

## 14. Governance

Quality governance in FinancialManager is handled through repository-based rules,
repeatable commands, and visible test evidence. The goal is to keep the quality process
practical and maintainable without introducing a separate test-management system.

The project does not require a multi-branch workflow. The testing strategy can work with a
single `main` branch, and it can also support pull requests if they are used later.

Quality governance is based on:

- staged coverage gates
- risk-based test prioritization
- repeatable Make targets
- Allure reports
- coverage reports
- GitHub Actions quality checks
- GitHub issues for defects, risks, accepted exceptions, and follow-up work
- regular review of the test backlog

Every high-risk change should add or update tests in the same change. This is especially
important for authentication, authorization, session handling, money calculations,
transaction lifecycle, brokerage flows, and sensitive financial data handling.

Coverage gates should be raised only when the test suite protects meaningful behavior.
They should not be raised only to improve the percentage or make the project look more
complete.

### 14.1 Test Change Rule

A change should include test updates when it:

- changes business logic
- changes API behavior
- changes authentication or session behavior
- changes authorization or ownership rules
- changes money calculations
- changes transaction or brokerage behavior
- changes report generation
- fixes a defect that should not happen again

If a test is not added for a risky change, the reason should be visible in a GitHub issue,
comment, or accepted exception.

### 14.2 Coverage Gate Rule

Coverage gates are used to prevent silent quality regression. A gate should be raised only
when:

- new tests cover real product behavior
- critical paths are not skipped
- the test suite is stable
- generated or boilerplate code is excluded consistently
- the same gate can be executed locally and in GitHub Actions

A temporary low gate is acceptable only when the gap is known and the next improvement
step is clear.

### 14.3 Flaky Test Policy

A flaky test is a test-suite defect. It should not be ignored or repeatedly re-run until it
passes.

When a test fails intermittently, the expected handling is:

- reproduce the failure where practical
- inspect logs, screenshots, traces, timing, and test data assumptions
- identify whether the problem is in the application, the test, the environment, or the
  fixture setup
- fix the root cause when practical
- quarantine the test only when the root cause cannot be fixed immediately
- link the quarantine to a GitHub issue, TODO, or investigation note

A quarantined test may be marked with `@pytest.mark.skip`, a Vitest `skip`, or an
equivalent mechanism used by the related test framework.

Quarantined tests are not counted as quality evidence until they are fixed and re-enabled.

A release candidate should not be treated as ready if a flaky or quarantined test hides a
critical risk in authentication, authorization, money calculations, transaction integrity,
or sensitive financial data handling.

### 14.4 Accepted Exception Rule

Not every gap has to block development, but important exceptions must be visible.

An accepted exception should explain:

- what is not covered
- why it is accepted for now
- what risk it creates
- how it should be addressed later

Critical exceptions should be avoided in:

- authentication
- authorization
- session handling
- money calculations
- transaction integrity
- brokerage logic
- sensitive financial data handling
- database migrations

### 14.5 Review Rhythm

The test backlog, coverage gaps, flaky tests, and accepted exceptions should be reviewed
regularly as part of normal development work.

The review should answer:

- Are the highest-risk areas covered by tests?
- Are coverage gates still realistic?
- Are skipped or quarantined tests still justified?
- Are known gaps visible?
- Are new tests protecting real behavior?
- Are reports and artifacts useful for debugging?

The governance process should stay lightweight. Its purpose is to keep testing decisions
clear and traceable, not to create unnecessary process overhead.

## 15. Roadmap

The roadmap defines how the testing strategy should mature over time. The purpose is to
improve quality in controlled steps instead of trying to add every test type and tool at
once.

The roadmap is ordered by risk, current coverage gaps, and practical value for the
project.

### 15.1 Near Term

The near-term focus is to stabilize the current quality workflow and improve coverage in
the highest-risk areas.

Priorities:

- keep branch coverage enabled for Python services
- stabilize Stage 1 coverage gates
- add `wallet` tests first because it has the highest business risk and the lowest current
  coverage gate
- reach `wallet` Stage 2 coverage before treating new wallet functionality as stable
- add explicit tests for critical `session` and authentication paths
- add negative authorization tests for ownership checks
- add frontend coverage reporting as a separate `next-ui` track
- connect the existing Make targets to GitHub Actions
- publish Allure results and coverage reports as GitHub Actions artifacts
- add `bandit` and `pip-audit` to the CI/CD quality workflow
- document known gaps through GitHub issues or the test backlog

Expected result:

- the main quality commands run locally and in GitHub Actions
- Stage 1 coverage gates are stable
- the most important wallet and session risks have visible automated tests
- Allure and coverage evidence are available from local runs and CI/CD runs

### 15.2 Mid Term

The mid-term focus is to expand coverage from isolated tests to broader service behavior,
security checks, accessibility checks, and selected integration flows.

Priorities:

- raise coverage gates to Stage 2 where meaningful tests support the increase
- add API/component tests for wallet, session, stock, and selected frontend/backend
  contracts
- add integration tests for database migrations, service readiness, persisted financial
  data, and routing assumptions
- add `make security-test`
- add `make accessibility-test`
- add selected `semgrep` rules for security-sensitive code paths
- add more tests for brokerage flows, holdings, gains, and financial reports
- add controlled failure-mode tests for stock scraping, market data parsing, and AI report
  generation
- add accessibility checks for core forms, route protection, and dashboard flows
- review accepted gaps and remove gaps that affect critical product risk

Expected result:

- Stage 2 coverage is reached for the most important services
- component and integration tests protect key service behavior
- security and accessibility checks are part of the repeatable quality workflow
- high-risk financial and authorization paths are better protected

### 15.3 Long Term

The long-term focus is to mature the quality workflow so it can support release decisions
with clear evidence.

Priorities:

- reach the mature coverage target for production service code
- keep critical modules close to 90% line and branch coverage
- maintain meaningful coverage for authentication, authorization, money calculations,
  transaction lifecycle, brokerage flows, and sensitive data handling
- maintain WCAG 2.2 AA-oriented evidence for core UI flows where practical
- maintain OWASP ASVS-oriented evidence for selected security risks
- publish Allure and coverage evidence for release candidates
- keep CI/CD quality checks stable and useful
- keep flaky tests, skipped tests, and accepted exceptions visible
- review the test backlog regularly and keep it aligned with product risk

Expected result:

- release candidates are supported by automated evidence
- high-risk areas are covered by the right test levels
- reports and artifacts make quality status easy to review
- the test strategy stays practical and maintainable as the project grows
