from __future__ import annotations

import os
from uuid import uuid4

import httpx
import psycopg
from robot.api.deco import keyword

ROBOT_LIBRARY_SCOPE = "SUITE"

DEFAULT_PASSWORD = "FunctionalPass123!"
DEFAULT_REFERER = "http://next.localhost/register"
LEGACY_LOCAL_REFERER = "http://next.localhost:8081/register"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@keyword("Create Active Functional User")
def create_active_functional_user(prefix: str = "func") -> dict[str, str]:
    suffix = uuid4().hex[:8]
    user = {
        "first_name": "Functional",
        "last_name": "Tester",
        "username": f"{prefix}{suffix}"[:12],
        "email": f"{prefix}.{suffix}@example.com",
        "password": DEFAULT_PASSWORD,
    }

    auth_url = _env("FUNCTIONAL_SESSION_AUTH_URL", "http://session-auth:8000").rstrip("/")
    referers = [
        _env("FUNCTIONAL_NEXT_UI_REFERER", DEFAULT_REFERER),
        DEFAULT_REFERER,
        LEGACY_LOCAL_REFERER,
    ]
    response = None
    for referer in dict.fromkeys(referers):
        response = httpx.post(
            f"{auth_url}/register/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": referer,
                "User-Agent": BROWSER_USER_AGENT,
            },
            json=user,
            timeout=10.0,
        )
        if response.status_code == 201:
            break

        if response.status_code != 400 or "Incorrect request" not in response.text:
            break

    if response is None:
        raise AssertionError("Could not create functional user: register request was not sent")

    if response.status_code != 201:
        raise AssertionError(f"Could not create functional user: {response.status_code} {response.text}")

    _activate_user(user["email"])
    return user


def _activate_user(email: str) -> None:
    with psycopg.connect(
        host=_env("FUNCTIONAL_SESSION_DB_HOST", "session-db"),
        port=int(_env("FUNCTIONAL_SESSION_DB_PORT", "5432")),
        dbname=_env("FUNCTIONAL_SESSION_DB_NAME", "session_test"),
        user=_env("FUNCTIONAL_SESSION_DB_USER", "myuser"),
        password=_env("FUNCTIONAL_SESSION_DB_PASSWORD", "mypassword"),
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE userauth_user
                   SET is_active = TRUE,
                       is_verified = TRUE
                 WHERE email = %s
             RETURNING id
                """,
                (email,),
            )
            if cursor.fetchone() is None:
                raise AssertionError(f"Functional user was not found for activation: {email}")
