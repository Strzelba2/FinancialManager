---
name: api-contract-review
description: Use when reviewing FastAPI, Django, or Next.js API contract changes, including endpoints, request payloads, response shapes, error formats, status codes, auth requirements, and frontend API clients.
---

# API Contract Review

Use this skill when a change affects public API behavior or frontend/backend contracts.

Check:

- endpoint path
- HTTP method
- request payload
- response shape
- response field names
- status code
- content type
- error payload
- authentication requirement
- authorization and ownership behavior
- backward compatibility with `next-ui`
- frontend API client usage

Service conventions:

- `session` is Django-based and may use different error response structures than FastAPI services.
- `wallet` and `stock` are FastAPI-based and share similar error conventions.
- When reviewing cross-service contracts, verify that the calling side handles both error formats correctly.

Rules:

- Do not silently rename response fields.
- Do not silently change status codes.
- Do not silently change error payload structure.
- Do not weaken authentication or authorization checks.
- Update related tests when API behavior changes.
- Update frontend API clients when backend contracts change.
- Prefer API/component tests for public endpoint behavior.
- Do not add or remove API versioning prefixes without explicit agreement.

For financial endpoints, also apply the `financial-domain-rules` skill.