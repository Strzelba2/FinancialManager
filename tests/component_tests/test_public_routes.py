from __future__ import annotations

import allure
import pytest

from tests.helpers.http import wait_for_response


@pytest.mark.component
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Traefik routes public UI traffic to the legacy NiceGUI service")
def test_legacy_ui_login_page_is_available_through_traefik(traefik_url: str) -> None:
    response = wait_for_response(
        f"{traefik_url}/login",
        expected_statuses={200},
        headers={"Host": "wallet.localhost"},
    )

    assert "text/html" in response.headers.get("content-type", "")
    assert "Logowanie" in response.text


@pytest.mark.component
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Traefik routes public UI traffic to the legacy NiceGUI service")
def test_legacy_ui_home_page_is_available_through_traefik(traefik_url: str) -> None:
    response = wait_for_response(
        f"{traefik_url}/home",
        expected_statuses={200},
        headers={"Host": "wallet.localhost"},
    )

    assert "text/html" in response.headers.get("content-type", "")
    assert "FinansowaEg" in response.text


@pytest.mark.component
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Traefik routes public UI traffic to next-ui")
def test_next_ui_login_page_is_available_through_traefik(traefik_url: str) -> None:
    response = wait_for_response(
        f"{traefik_url}/login",
        expected_statuses={200},
        headers={"Host": "next.localhost"},
    )

    assert "text/html" in response.headers.get("content-type", "")
    assert "FinancialManager" in response.text


@pytest.mark.component
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Traefik routes public UI traffic to next-ui")
def test_next_ui_register_page_is_available_through_traefik(traefik_url: str) -> None:
    response = wait_for_response(
        f"{traefik_url}/register",
        expected_statuses={200},
        headers={"Host": "next.localhost"},
    )

    assert "text/html" in response.headers.get("content-type", "")
    assert "Rejestracja" in response.text
