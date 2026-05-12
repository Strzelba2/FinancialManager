from __future__ import annotations

from typing import Any


def registration_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "username": "artur.tests",
        "email": "artur.tests@example.com",
        "first_name": "artur",
        "last_name": "Tester",
        "password": "ChangeMe-12345",
    }
    payload.update(overrides)
    return payload


def login_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "email": "artur.tests@example.com",
        "password": "ChangeMe-12345",
    }
    payload.update(overrides)
    return payload


def verified_session_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "X-User": "artur.tests",
        "X-First-Name": "artur",
        "X-Email": "artur.tests@example.com",
        "X-User-Id": "user-001",
    }
    headers.update(overrides)
    return headers
