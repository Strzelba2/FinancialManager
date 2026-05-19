# Session Login Security

## Purpose

This document describes the implemented security contract for the `session`
login flow used by `next-ui`. The flow protects authentication, session
verification, HMAC cookies, login retry handling, and repeated second-device
login attempts.

## Scope

In scope:

- `POST /login/` in `session-auth`
- `POST /logout/` in `session-auth`
- `GET /verifySession/` in `session-auth`
- `next-ui` login server action and route guard behavior
- `next-ui` browser-to-API auth boundary for protected wallet/stock mutations
- Login throttling, `BlockedIP`, user temporary block, and permanent user block

Out of scope:

- New tests for the legacy NiceGUI UI, which is planned for retirement.
- Formal security compliance claims. This is a standards-informed testing model,
  not a certification statement.

## Business Rules

- A login from the same request fingerprint is allowed and refreshes the active
  login state.
- A login from a different request fingerprint is rejected with `409 Conflict`
  while an active login exists and the HMAC window is still fresh.
- If the active login naturally expires, a later login from a different
  fingerprint is allowed.
- Logout clears the active login entry only for the current session key, so the
  account can be used from another device after the owner logs out.
- Repeated rejected login attempts, including repeated second-device attempts,
  feed the normal login attempt counters.
- Repeated attempts from the same IP are still governed by `LoginIPThrottle` and
  create `BlockedIP` evidence when the throttle is exceeded.
- Repeated account-level failures can escalate to a permanent user block.

The request fingerprint is derived from the trusted client IP, `User-Agent`, and
`Sec-CH-UA-Platform`, then hashed with the server salt before being stored in the
cache.

## Main Flow

1. `next-ui` validates the login form and sends credentials to `session-auth`
   with the original client IP and browser headers.
2. `session-auth` middleware validates Referer, User-Agent, bot status, and IP
   block state before the login view runs.
3. DRF throttling applies `LoginIPThrottle` per client IP.
4. The login view validates credentials.
5. If the user is blocked, the request returns the permanent block contract.
6. If another fresh active login exists for a different fingerprint, the request
   returns `409 Conflict` and records the failed login attempt.
7. On success, Django rotates the session key, `sessionid` and `hmac_token`
   cookies are issued, and the active login cache entry is stored for the HMAC
   validity window.
8. `verifySession` validates and refreshes the HMAC cookie and refreshes the
   active login cache TTL.
9. `next-ui` renders `/logout` as a confirmation page. The session is ended only
   when the user submits the logout Server Action, which calls `session-auth`
   `POST /logout/`, clears the browser cookies, and redirects to `/login`.

## API Contract

`POST /login/` success:

- Status: `200 OK`
- Body: `{"message": "Login successful"}`
- Cookies: `sessionid`, `hmac_token`

`POST /login/` second fresh fingerprint:

- Status: `409 Conflict`
- Body includes `error` and `blocked_permanently: false`
- No auth cookies are issued

`POST /login/` invalid credentials:

- Status: `401 Unauthorized`
- No auth cookies are issued

`POST /login/` temporary or permanent retry block:

- Status: `429 Too Many Requests`
- Body includes retry metadata and `blocked_permanently`
- No auth cookies are issued

`next-ui` maps these responses into user-visible messages and fails closed when
a successful login response does not expose both required auth cookies.

## Security Considerations

- CSRF protection is enforced at the browser boundary. `next-ui` Server Actions
  use Next.js same-origin checks and `serverActions.allowedOrigins`, while
  protected `next-ui` `/api/**` routes remain behind Traefik ForwardAuth. With
  `SameSite=Lax`, cross-site `POST` form submissions do not carry the auth
  cookies required by ForwardAuth.
- `session-auth` login/logout/set-wallet-user-id calls from `next-ui` are
  server-to-server calls on the internal Docker network. They use the existing
  session/HMAC/Referer contract and are not treated as public browser CSRF
  endpoints for the Next UI flow.
- `GET /logout` must not perform a state change. Logout is an explicit
  `POST`-backed Server Action in `next-ui`.
- `X-Original-Client-IP`, `X-Forwarded-For`, and `X-Real-IP` are trusted only
  from configured trusted proxies or private/loopback proxy sources.
- Plaintext credentials, auth cookies, HMAC values, and email addresses are not
  written to login logs.
- Missing-user authentication performs dummy password hash work to reduce timing
  enumeration risk.
- Auth cookies default to `Secure` when `NODE_ENV=production` or the configured
  public app URL uses HTTPS. Local or non-TLS deployments can override this with
  `AUTH_COOKIE_SECURE=false`; production deployments should set the public app
  URL and cookie policy intentionally to avoid silent cookie delivery failures.
- `next-ui` route guards do not trust spoofed `X-User*` headers on direct
  service access.
- Session fixation is mitigated by Django session key rotation during login.

## Test Expectations

Evidence expected from the testing process:

- Session unit tests for helper behavior, auth backend logging, middleware bot
  blocking, spoofed IP handling, timing-enumeration mitigation, and response
  contracts.
- `next-ui` unit tests for login action API handling, MSW-based auth mocking,
  cookie security flags, 403/409 mapping, fail-closed cookie handling, login page
  states, and proxy route guards.
- Component tests for successful login, rejected login, session fixation, HMAC
  verification, HMAC refresh, logout, SQL injection and XSS payload rejection,
  Referer/User-Agent abuse, direct header spoofing, `BlockedIP`, user blocks,
  active login refresh, and second-device rejection.
- Integration tests for Traefik ForwardAuth and public/protected route contracts.
- Functional Robot tests for the browser login path, anonymous route protection,
  XSS and SQL injection payload rejection through the form, and visible
  second-device conflict messaging.
- Security fuzzing tests for malformed login payloads, type mutations, injection
  strings, and oversized input.
- Login load/security tests for abusive request bursts, IP throttle stability, and
  no-session/no-500 invariants under concurrency.
- Login stress tests for many users logging in, verifying sessions, logging out,
  mixed valid/invalid credential pressure, threaded unique-user capacity checks,
  threaded same-user races, and second-device pressure without issuing new auth cookies.
  The current login contract does not define a global active-user cap; stress evidence
  verifies the configured development profile and session isolation rather than a
  product-level admission-control limit.
- Explicit capacity probes for the development setup ramp unique users through login,
  direct `/verifySession/`, routed `/wallet`, routed `/transactions`, and logout. The
  direct verify phase runs before routed page requests so the JSON report can distinguish
  session-auth verification failures from Traefik/ForwardAuth/Next UI page failures and
  include the exact status, body sample, or timeout sample for the failing phase. The same
  evidence is rendered as a readable HTML capacity report and attached to Allure. The probe
  records the first failing user-count step as operational evidence for future
  admission-control or scaling decisions. The capacity target runs `session-auth` with a
  prod-like Gunicorn profile (`ENV_TYPE=prod`, `GUNICORN_WORKERS=3`,
  `GUNICORN_TIMEOUT=60`) while other test suites keep `ENV_TYPE=test`. It also includes
  `next.localhost` in the session service allowed hosts so `DEBUG=False` plus
  `USE_X_FORWARDED_HOST` can validate routed ForwardAuth requests. Each ramp step uses a
  disjoint user/IP pool. Each virtual user uses a stable `198.18.0.0/15`
  benchmarking-range `X-Original-Client-IP` across login and routed page requests so HMAC
  fingerprinting is exercised with a per-user IP model rather than one shared client
  address.
- OWASP ZAP DAST evidence through the explicit `make login-dast-test` workflow,
  with reports written under `tests/artifacts/zap-login-dast`.
