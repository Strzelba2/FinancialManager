from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from pathlib import Path

TOTP_WINDOW_SECONDS = 30
_USED_TOTP_COUNTERS: dict[tuple[str, str], set[int]] = {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def session_env_value(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value

    env_file = _repo_root() / "session" / "config" / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip() == name:
            return raw_value.strip().strip('"').strip("'")

    raise AssertionError(f"Missing required session env value: {name}")


def two_factor_secret(email: str, username: str) -> str:
    server_salt = session_env_value("SERVER_SALT")
    combined = f"{username[::-1]}:POST:{email.lower()}:{server_salt}".encode("utf-8")
    hash1 = hashlib.sha512(combined).digest()
    salted_hash = hashlib.pbkdf2_hmac(
        "sha256",
        hash1,
        server_salt.encode("utf-8"),
        iterations=100_000,
    )
    return base64.b32encode(salted_hash).decode("utf-8")[:32]


def totp_code(
    email: str,
    username: str,
    now: int | float | None = None,
    counter: int | None = None,
) -> str:
    secret = two_factor_secret(email, username)
    if counter is None:
        timestamp = now if now is not None else time.time()
        counter = int(timestamp // TOTP_WINDOW_SECONDS)

    digest = hmac.new(base64.b32decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def fresh_totp_code(email: str, username: str) -> str:
    now = time.time()
    counter = int(now // TOTP_WINDOW_SECONDS)
    counters = [counter, counter + 1, counter - 1]
    if now % TOTP_WINDOW_SECONDS > 25:
        counters = [counter + 1, counter, counter - 1]

    # Functional tests can request several codes for one user in a single
    # process. Keep process-local counters fresh so session's replay cache does
    # not reject a repeated TOTP during the same test run.
    used_counters = _USED_TOTP_COUNTERS.setdefault((email, username), set())
    fresh_counter = next((candidate for candidate in counters if candidate not in used_counters), None)
    if fresh_counter is None:
        raise AssertionError("No fresh functional TOTP counter is available in the current validation window")

    used_counters.add(fresh_counter)
    return totp_code(email, username, counter=fresh_counter)
