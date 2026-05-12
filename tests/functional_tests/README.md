# Functional Tests

Robot Framework functional tests live here. Suite files are kept in `TestSuites/`, while
Python-backed Robot keyword libraries live in `TestKeywords/`. The suites use the Browser
library, which is powered by Playwright, so browser journeys stay in the same Robot/Allure
reporting flow as smoke tests.

## Allure Integration

Screenshots are captured at each navigation step through the Python keyword
`Capture Test Screenshot` and appear inline in the Allure test body.

When a test fails, a full Playwright trace zip is attached to Allure automatically.
The trace can be opened at https://trace.playwright.dev to replay the failure step by step.

### How tracing works

Tracing is enabled at context level through the Python keyword `Open Next Ui Browser`.
The Browser library (robotframework-browser >= 19) records a Playwright trace
for the entire suite session and saves it to `{OUTPUT DIR}/browser/traces/` when the
browser is closed.

`Close Browser And Keep Failure Artifacts` calls the Python Allure helper when
`${SUITE STATUS}` is `FAIL`. The helper picks the most recently written zip from the
traces directory and attaches it to Allure.

The trace is NOT attached for passing suites to keep Allure artifact size manageable.

Note: this produces one trace per suite run, covering all tests in the suite. Opening
the attached zip at https://trace.playwright.dev shows the full browser session timeline.

Current coverage starts with public/auth next-ui journeys:

- public home route exposes auth entry points
- login and register pages expose stable form controls
- anonymous protected routes redirect back to login

Next high-value flows to add after deterministic seed data exists:

- register/login with Mailpit activation
- create wallet
- add account
- add transaction
- view dashboard
- add favorite and price alert
- logout and auth-error redirects
