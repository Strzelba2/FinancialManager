<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes. APIs, conventions, and file structure may all differ
from your training data. Read the relevant guide in `node_modules/next/dist/docs/`
before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Next UI Agent Guide

Follow the root `AGENTS.md` first. This file adds frontend-specific rules for `next-ui`.

## Scope

`next-ui` is the Next.js frontend for FinancialManager. It is responsible for user-facing
flows, route protection, dashboards, reports, forms, charts, and API client behavior.

## Working Rules

- Preserve user-visible behavior unless the requested change explicitly alters it.
- Keep API client changes compatible with backend response shapes and error payloads.
- Do not silently change route guard behavior, auth redirects, money/date formatting, or
  dashboard empty/loading/error states.
- Use existing component, feature, and styling patterns before adding new ones.
- Keep UI text concise and domain-appropriate.
- Avoid introducing real secrets, tokens, or production-like financial data in tests.

## Testing Rules

- Use Vitest and React Testing Library for frontend unit tests.
- Use `msw` (Mock Service Worker) for API mocking in Vitest tests. Do not mock
  `fetch` directly or introduce other HTTP mocking libraries.
- Prefer behavior-focused assertions over implementation details.
- Cover forms, route guards, API clients, formatting helpers, dashboard states, and report
  behavior when changed.
- For UI states, consider success, empty, loading, error, and unauthorized states where
  applicable.
- Keep test data deterministic and readable.

## Accessibility Rules

- Add `aria-label` or `aria-labelledby` to interactive elements that lack visible text.
- Verify that form fields have an associated `<label>` element or `aria-label`.
- Do not remove `role`, `aria-*`, or `tabIndex` attributes without checking whether
  they serve a keyboard or screen-reader purpose.
- When adding dialogs, drawers, or modals, verify that focus is trapped inside and
  returned to the trigger element on close.
- Do not break keyboard navigation when modifying interactive components.
- Prefer semantic HTML (`<button>`, `<nav>`, `<main>`, `<section>`) over `<div>`
  with click handlers.

## TypeScript And ESLint Rules

- Do not use `any` to bypass type errors. Find the correct type or use a narrower
  assertion with a comment explaining why.
- Do not add `// eslint-disable` inline comments to silence lint errors.
- Do not use `as` casts to force a type without understanding the underlying contract.
- Fix type errors at the root cause, not at the call site.
- Keep component props typed with explicit interfaces or type aliases.

## Verification

Use the smallest relevant command:

```bash
make unit-test-next-ui
make quality-test-next-ui
```

For browser-level journeys, use repository-level Robot Framework tests through:

```bash
make functional-test
```
