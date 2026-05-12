from __future__ import annotations

import allure
import pytest

from tests.helpers.http import wait_for_response


@pytest.mark.integration
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Session service exposes health probes")
def test_session_healthz_returns_ok(session_url: str) -> None:
    response = wait_for_response(
        f"{session_url}/healthz",
        expected_statuses={200},
    )

    assert response.json() == {"status": "ok"}


@pytest.mark.integration
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Session service verifies database and cache readiness")
def test_session_readyz_returns_ready(session_url: str) -> None:
    response = wait_for_response(
        f"{session_url}/readyz",
        expected_statuses={200},
    )

    assert response.json() == {"status": "ready"}


@pytest.mark.integration
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Wallet service exposes health probes")
def test_wallet_healthz_returns_200(wallet_url: str) -> None:
    response = wait_for_response(
        f"{wallet_url}/healthz",
        expected_statuses={200},
    )

    assert response.status_code == 200


@pytest.mark.integration
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Stock service exposes health probes")
def test_stock_healthz_returns_200(stock_url: str) -> None:
    response = wait_for_response(
        f"{stock_url}/healthz",
        expected_statuses={200},
    )

    assert response.status_code == 200
