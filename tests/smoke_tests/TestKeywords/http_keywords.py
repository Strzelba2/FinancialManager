from __future__ import annotations

import os
import time
from collections.abc import Mapping

import httpx
from robot.api.deco import keyword
from robot.libraries.BuiltIn import BuiltIn

ROBOT_LIBRARY_SCOPE = "SUITE"

_SMOKE_SESSIONS: dict[str, str] = {}


def _log(message: str, level: str = "INFO") -> None:
    BuiltIn().log(message, level)


def _expected_int(value: int | str) -> int:
    return int(str(value).strip())


def _base_url(session_name: str) -> str:
    try:
        return _SMOKE_SESSIONS[session_name]
    except KeyError as exc:
        known = ", ".join(sorted(_SMOKE_SESSIONS)) or "none"
        raise AssertionError(f"Unknown smoke session '{session_name}'. Known sessions: {known}") from exc


def _get(
    url: str,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    return httpx.get(
        url,
        headers=dict(headers or {}),
        follow_redirects=True,
        timeout=10.0,
    )


def _wait_until_probe_matches(probe_name: str, probe, attempts: int = 20, delay_seconds: float = 2.0) -> None:
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            probe()
            return
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                _log(f"{probe_name} attempt {attempt}/{attempts} failed: {exc}", "DEBUG")
                time.sleep(delay_seconds)

    raise AssertionError(f"{probe_name} did not match after {attempts} attempts") from last_error


@keyword("Open Smoke Sessions")
def open_smoke_sessions() -> None:
    _SMOKE_SESSIONS.clear()
    _SMOKE_SESSIONS.update(
        {
            "traefik": os.environ.get("TRAEFIK_URL", "http://traefik"),
            "session": os.environ.get("SESSION_URL", "http://session-auth:8000"),
            "wallet": os.environ.get("WALLET_URL", "http://wallet:8001"),
            "stock": os.environ.get("STOCK_URL", "http://stock:8001"),
        }
    )


@keyword("Traefik Route Should Return Status")
def traefik_route_should_return_status(host: str, path: str, expected_status: int | str) -> None:
    expected = _expected_int(expected_status)

    def probe() -> None:
        response = _get(
            f"{_base_url('traefik')}{path}",
            headers={"Host": host},
        )
        if response.status_code != expected:
            raise AssertionError(f"{host}{path} returned {response.status_code}, expected {expected}")

    _wait_until_probe_matches(f"Traefik route {host}{path}", probe)


@keyword("Internal Endpoint Should Return Status")
def internal_endpoint_should_return_status(session_name: str, path: str, expected_status: int | str) -> None:
    expected = _expected_int(expected_status)

    def probe() -> None:
        response = _get(f"{_base_url(session_name)}{path}")
        if response.status_code != expected:
            raise AssertionError(f"{session_name}{path} returned {response.status_code}, expected {expected}")

    _wait_until_probe_matches(f"Internal endpoint {session_name}{path}", probe)


@keyword("Internal Endpoint Should Return Json Status")
def internal_endpoint_should_return_json_status(session_name: str, path: str, expected_status_value: str) -> None:
    def probe() -> None:
        response = _get(f"{_base_url(session_name)}{path}")
        if response.status_code != 200:
            raise AssertionError(f"{session_name}{path} returned {response.status_code}, expected 200")

        body = response.json()
        actual = body.get("status")
        if actual != expected_status_value:
            raise AssertionError(f"{session_name}{path} returned status={actual!r}, expected {expected_status_value!r}")

    _wait_until_probe_matches(f"Internal JSON endpoint {session_name}{path}", probe)
