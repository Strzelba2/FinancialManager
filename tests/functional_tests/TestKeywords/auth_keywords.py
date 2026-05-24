from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from robot.api.deco import keyword

TESTS_ROOT = Path(__file__).resolve().parents[2]
if str(TESTS_ROOT) not in sys.path:
    sys.path.append(str(TESTS_ROOT))

from helpers.totp import fresh_totp_code

ROBOT_LIBRARY_SCOPE = "SUITE"

DEFAULT_PASSWORD = "FunctionalPass123!"
DEFAULT_REFERER = "http://next.localhost/register"
LEGACY_LOCAL_REFERER = "http://next.localhost:8081/register"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
LOGIN_THROTTLE_KEY_PATTERNS = (
    "*throttle_login*",
    "*login_attempts_*",
    "*too_many_login_attempts_*",
    "*to_many_login_attempts_*",
)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _read_redis_line(sock: socket.socket) -> bytes:
    chunks = []
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise RuntimeError("Redis connection closed while reading a line")
        if chunk == b"\r":
            lf = sock.recv(1)
            if lf != b"\n":
                raise RuntimeError("Invalid Redis line ending")
            return b"".join(chunks)
        chunks.append(chunk)


def _read_redis_response(sock: socket.socket):
    prefix = sock.recv(1)
    if not prefix:
        raise RuntimeError("Redis connection closed while reading a response")

    if prefix == b"+":
        return _read_redis_line(sock).decode("utf-8")
    if prefix == b"-":
        raise RuntimeError(_read_redis_line(sock).decode("utf-8"))
    if prefix == b":":
        return int(_read_redis_line(sock))
    if prefix == b"$":
        length = int(_read_redis_line(sock))
        if length == -1:
            return None
        payload = bytearray()
        while len(payload) < length:
            payload.extend(sock.recv(length - len(payload)))
        if sock.recv(2) != b"\r\n":
            raise RuntimeError("Invalid Redis bulk string ending")
        return bytes(payload).decode("utf-8")
    if prefix == b"*":
        count = int(_read_redis_line(sock))
        if count == -1:
            return None
        return [_read_redis_response(sock) for _ in range(count)]

    raise RuntimeError(f"Unsupported Redis response prefix: {prefix!r}")


def _redis_command(sock: socket.socket, *parts: str):
    payload = [f"*{len(parts)}\r\n".encode("utf-8")]
    for part in parts:
        encoded = part.encode("utf-8")
        payload.append(f"${len(encoded)}\r\n".encode("utf-8"))
        payload.append(encoded)
        payload.append(b"\r\n")
    sock.sendall(b"".join(payload))
    return _read_redis_response(sock)


def _delete_redis_keys_by_pattern(pattern: str) -> None:
    host = _env("FUNCTIONAL_REDIS_HOST", "redis")
    port = int(_env("FUNCTIONAL_REDIS_PORT", "6379"))
    database = _env("FUNCTIONAL_REDIS_DB", "1")

    with socket.create_connection((host, port), timeout=3.0) as sock:
        _redis_command(sock, "SELECT", database)
        cursor = "0"
        while True:
            response = _redis_command(sock, "SCAN", cursor, "MATCH", pattern, "COUNT", "100")
            cursor = str(response[0])
            keys = [str(key) for key in response[1]]
            if keys:
                _redis_command(sock, "DEL", *keys)
            if cursor == "0":
                break


@keyword("Reset Functional Auth Rate Limits")
def reset_functional_auth_rate_limits() -> None:
    for pattern in LOGIN_THROTTLE_KEY_PATTERNS:
        _delete_redis_keys_by_pattern(pattern)

    with psycopg.connect(
        host=_env("FUNCTIONAL_SESSION_DB_HOST", "session-db"),
        port=int(_env("FUNCTIONAL_SESSION_DB_PORT", "5432")),
        dbname=_env("FUNCTIONAL_SESSION_DB_NAME", "session_test"),
        user=_env("FUNCTIONAL_SESSION_DB_USER", "myuser"),
        password=_env("FUNCTIONAL_SESSION_DB_PASSWORD", "mypassword"),
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM userauth_blockedip")


@keyword("Generate Functional User Totp Code")
def generate_functional_user_totp_code(user: dict[str, str]) -> str:
    return fresh_totp_code(user["email"], user["username"])


@keyword("Create Active Functional User")
def create_active_functional_user(prefix: str = "func") -> dict[str, str]:
    suffix = uuid4().hex[:8]
    ip_tail = int(suffix[:2], 16)
    user = {
        "first_name": "Functional",
        "last_name": "Tester",
        "username": f"{prefix}{suffix}"[:12],
        "email": f"{prefix}.{suffix}@example.com",
        "password": DEFAULT_PASSWORD,
        "client_ip": f"10.230.{ip_tail}.10",
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
                "X-Original-Client-IP": user["client_ip"],
            },
            json={key: value for key, value in user.items() if key != "client_ip"},
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


@keyword("Start Functional Backend Session")
def start_functional_backend_session(user: dict[str, str]) -> int:
    auth_url = _env("FUNCTIONAL_SESSION_AUTH_URL", "http://session-auth:8000").rstrip("/")
    referers = [
        _env("FUNCTIONAL_NEXT_UI_LOGIN_REFERER", "http://next.localhost/login"),
        "http://next.localhost/login",
        "http://next.localhost:8081/login",
    ]
    response = None
    for referer in dict.fromkeys(referers):
        response = httpx.post(
            f"{auth_url}/login/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": referer,
                "User-Agent": BROWSER_USER_AGENT,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": "10.240.1.10",
            },
            json={"email": user["email"], "password": user["password"]},
            timeout=10.0,
        )
        if response.status_code != 400 or "Incorrect request" not in response.text:
            break

    if response is None:
        raise AssertionError("Could not start backend session: login request was not sent")

    return response.status_code


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
