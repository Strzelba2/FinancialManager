# Session Agent Guide

Follow the root `AGENTS.md` first. This file adds service-specific rules for `session`.

## Scope

`session` is the Django authentication and session service. It is responsible for
registration, login, logout, session verification, cookies, HMAC/session tokens, blocking,
2FA-related paths, admin/security behavior, middleware, serializers, validators, forms,
and user authentication models.

## Risk Profile

Treat `session` changes as security-sensitive. Incorrect behavior can expose private
financial data or allow unauthorized access to other services.

Critical areas:

- authentication
- authorization assumptions
- session verification
- HMAC/session tokens
- cookie behavior
- login success and failure paths
- temporary and permanent blocking
- logout behavior
- 2FA/admin security paths
- middleware allow/deny behavior
- API contracts used by `wallet`, `stock`, and `next-ui`

## Working Rules

- Do not change auth, session, cookie, HMAC, or blocking behavior without considering
  negative tests.
- Check both allowed and denied behavior for security-sensitive paths.
- Keep secrets, tokens, cookies, and credentials fake and deterministic in tests.
- Preserve public auth/session API contracts unless the user explicitly requests a change.
- When middleware behavior changes, check health/readiness routes and protected route
  behavior.
- For Django changes, respect existing project settings and test database patterns.

## Test Expectations

High-risk changes should consider:

- valid and invalid login
- blocked user behavior
- missing, malformed, expired, or tampered session data
- HMAC verification success and failure
- cookie creation, deletion, and security flags where applicable
- anonymous access to protected routes
- cross-service session verification behavior

## Verification

Use the smallest relevant command:

```bash
make unit-test-session
make coverage-unit-session
```

For public auth behavior or cross-service assumptions:

```bash
make component-test
make integration-test
make smoke-test
```
