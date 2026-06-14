from __future__ import annotations

import pytest

from tests.helpers.http import wait_for_response


@pytest.fixture(scope="session", autouse=True)
def wait_for_next_ui_traefik_route() -> None:
    wait_for_response(
        "http://traefik/login",
        expected_statuses={200},
        headers={"Host": "next.localhost", "Accept": "text/html"},
        attempts=60,
        delay_seconds=1.0,
    )
