from __future__ import annotations

import os
import socket
import sys
from datetime import datetime, timezone
from decimal import Decimal
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


@keyword("Seed Functional Wallet Account")
def seed_functional_wallet_account(user: dict[str, str], opening_balance: str = "0.00") -> dict[str, str]:
    suffix = uuid4().hex[:8]
    wallet_user_id = str(uuid4())
    wallet_id = str(uuid4())
    account_id = str(uuid4())
    wallet_name = f"Functional Wallet {suffix}"
    account_name = f"Functional Account {suffix}"
    now = datetime.now(timezone.utc)
    fingerprint = uuid4().bytes + uuid4().bytes

    with psycopg.connect(
        host=_env("FUNCTIONAL_WALLET_DB_HOST", "wallet-db"),
        port=int(_env("FUNCTIONAL_WALLET_DB_PORT", "5432")),
        dbname=_env("FUNCTIONAL_WALLET_DB_NAME", "Wallet_test"),
        user=_env("FUNCTIONAL_WALLET_DB_USER", "myuser"),
        password=_env("FUNCTIONAL_WALLET_DB_PASSWORD", "mypassword"),
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM banks ORDER BY name LIMIT 1")
            bank_row = cursor.fetchone()
            if bank_row is None:
                bank_id = str(uuid4())
                cursor.execute(
                    "INSERT INTO banks (id, name, shortname, bic) VALUES (%s, %s, %s, %s)",
                    (bank_id, f"Functional Bank {suffix}", f"F{suffix[:4]}".upper(), None),
                )
            else:
                bank_id = str(bank_row[0])

            cursor.execute(
                """
                INSERT INTO users (id, created_at, updated_at, username, email, first_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE
                    SET email = EXCLUDED.email,
                        first_name = EXCLUDED.first_name
                RETURNING id
                """,
                (
                    wallet_user_id,
                    now,
                    now,
                    user["username"],
                    user["email"],
                    user.get("first_name", "Functional"),
                ),
            )
            wallet_user_id = str(cursor.fetchone()[0])

            cursor.execute(
                """
                INSERT INTO wallets (id, created_at, updated_at, user_id, name, currency)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (wallet_id, now, now, wallet_user_id, wallet_name, "PLN"),
            )
            cursor.execute(
                """
                INSERT INTO deposit_accounts (
                    id, created_at, updated_at, name, account_type,
                    account_number_nonce, account_number_ct, account_number_fp,
                    iban_nonce, iban_ct, iban_fp,
                    currency, wallet_id, bank_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s, %s, %s)
                """,
                (
                    account_id,
                    now,
                    now,
                    account_name,
                    "CURRENT",
                    psycopg.Binary(b"1" * 12),
                    psycopg.Binary(f"functional-cipher-{suffix}".encode("utf-8")),
                    psycopg.Binary(fingerprint),
                    "PLN",
                    wallet_id,
                    bank_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO deposit_account_balances (
                    account_id, created_at, updated_at, available, blocked
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (account_id, now, now, Decimal(opening_balance), Decimal("0.00")),
            )

    return {
        "user_id": wallet_user_id,
        "wallet_id": wallet_id,
        "account_id": account_id,
        "wallet_name": wallet_name,
        "account_name": account_name,
        "currency": "PLN",
    }


@keyword("Seed Functional Brokerage Account")
def seed_functional_brokerage_account(wallet: dict[str, str], opening_balance: str = "10000.00") -> dict[str, str]:
    suffix = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    brokerage_account_id = str(uuid4())
    cash_account_id = str(uuid4())
    brokerage_name = f"Functional Brokerage {suffix}"
    cash_name = f"Functional Brokerage Cash {suffix}"
    mic = f"F{suffix[:3]}".upper()
    symbol = f"F{suffix[3:6]}".upper()
    isin = f"PL{suffix[:10].upper():0<10}"[:12]

    with psycopg.connect(
        host=_env("FUNCTIONAL_WALLET_DB_HOST", "wallet-db"),
        port=int(_env("FUNCTIONAL_WALLET_DB_PORT", "5432")),
        dbname=_env("FUNCTIONAL_WALLET_DB_NAME", "Wallet_test"),
        user=_env("FUNCTIONAL_WALLET_DB_USER", "myuser"),
        password=_env("FUNCTIONAL_WALLET_DB_PASSWORD", "mypassword"),
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM banks ORDER BY name LIMIT 1")
            bank_row = cursor.fetchone()
            if bank_row is None:
                bank_id = str(uuid4())
                cursor.execute(
                    "INSERT INTO banks (id, name, shortname, bic) VALUES (%s, %s, %s, %s)",
                    (bank_id, f"Functional Broker {suffix}", f"B{suffix[:4]}".upper(), None),
                )
            else:
                bank_id = str(bank_row[0])

            cursor.execute(
                """
                INSERT INTO brokerage_accounts (id, created_at, updated_at, name, wallet_id, bank_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (brokerage_account_id, now, now, brokerage_name, wallet["wallet_id"], bank_id),
            )
            cursor.execute(
                """
                INSERT INTO deposit_accounts (
                    id, created_at, updated_at, name, account_type,
                    account_number_nonce, account_number_ct, account_number_fp,
                    iban_nonce, iban_ct, iban_fp,
                    currency, wallet_id, bank_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s, %s, %s)
                """,
                (
                    cash_account_id,
                    now,
                    now,
                    cash_name,
                    "BROKERAGE",
                    psycopg.Binary(b"2" * 12),
                    psycopg.Binary(f"functional-brokerage-cipher-{suffix}".encode("utf-8")),
                    psycopg.Binary(uuid4().bytes + uuid4().bytes),
                    "PLN",
                    wallet["wallet_id"],
                    bank_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO deposit_account_balances (account_id, created_at, updated_at, available, blocked)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (cash_account_id, now, now, Decimal(opening_balance), Decimal("0.00")),
            )
            cursor.execute(
                """
                INSERT INTO brokerage_deposit_links (brokerage_account_id, deposit_account_id, currency)
                VALUES (%s, %s, %s)
                """,
                (brokerage_account_id, cash_account_id, "PLN"),
            )

    with psycopg.connect(
        host=_env("FUNCTIONAL_STOCK_DB_HOST", "stock-db"),
        port=int(_env("FUNCTIONAL_STOCK_DB_PORT", "5432")),
        dbname=_env("FUNCTIONAL_STOCK_DB_NAME", "stock_test"),
        user=_env("FUNCTIONAL_STOCK_DB_USER", "myuser"),
        password=_env("FUNCTIONAL_STOCK_DB_PASSWORD", "mypassword"),
    ) as conn:
        with conn.cursor() as cursor:
            market_id = str(uuid4())
            instrument_id = str(uuid4())
            cursor.execute(
                """
                INSERT INTO market (id, mic, name, country, timezone, active, currency)
                VALUES (%s, %s, %s, %s, %s, TRUE, %s)
                """,
                (market_id, mic, f"Functional Market {suffix}", "PL", "Europe/Warsaw", "PLN"),
            )
            cursor.execute(
                """
                INSERT INTO instrument (
                    id, created_at, updated_at, isin, symbol, shortname, name,
                    currency, type, status, historical_source, quote_source,
                    popularity, last_seen_at, market_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, 0, %s, %s)
                """,
                (
                    instrument_id,
                    now,
                    now,
                    isin,
                    symbol,
                    symbol,
                    f"Functional Instrument {suffix}",
                    "PLN",
                    "STOCK",
                    "ACTIVE",
                    now,
                    market_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO quote_latest (
                    instrument_id, last_price, change_pct, volume,
                    last_trade_at, provider, href, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (instrument_id, Decimal("50.00"), Decimal("0.00"), 1000, now, "functional", None, now),
            )

    return {
        "brokerage_account_id": brokerage_account_id,
        "cash_account_id": cash_account_id,
        "brokerage_name": brokerage_name,
        "cash_name": cash_name,
        "mic": mic,
        "symbol": symbol,
        "isin": isin,
        "opening_balance": opening_balance,
    }


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
