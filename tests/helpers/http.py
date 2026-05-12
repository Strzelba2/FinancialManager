from __future__ import annotations

from collections.abc import Iterable, Mapping
import time

import httpx


def wait_for_response(
    url: str,
    *,
    expected_statuses: Iterable[int],
    headers: Mapping[str, str] | None = None,
    follow_redirects: bool = True,
    attempts: int = 20,
    delay_seconds: float = 1.0,
) -> httpx.Response:
    last_error: Exception | None = None
    last_response: httpx.Response | None = None
    expected = set(expected_statuses)

    for attempt in range(attempts):
        try:
            response = httpx.get(
                url,
                headers=dict(headers or {}),
                follow_redirects=follow_redirects,
                timeout=10.0,
            )
            if response.status_code in expected:
                return response
            last_response = response
        except httpx.HTTPError as exc:
            last_error = exc

        if attempt < attempts - 1:
            time.sleep(delay_seconds)

    if last_response is not None:
        raise AssertionError(
            f"{url} returned {last_response.status_code}, expected one of {sorted(expected)}"
        )

    raise AssertionError(f"{url} did not become reachable") from last_error
