from __future__ import annotations

import allure
import httpx
import pytest


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Session verifySession rejects missing or anonymous authorization state")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("session", "auth", "security", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies public verifySession behavior through HTTP. Missing cookies return a "
    "401 contract payload; anonymous requests with placeholder cookies are still rejected."
)
class TestSessionVerifySessionContract:
    def test_verify_session_without_cookies_returns_401_payload(self, session_url: str) -> None:
        response = httpx.get(
            f"{session_url}/verifySession/",
            headers={
                "Accept": "application/json",
                "X-Forwarded-Host": "next.localhost",
            },
            timeout=10.0,
        )

        assert response.status_code == 401
        payload = response.json()
        assert payload["error"] == "User does not have permission to this site. Please login."
        assert payload["href"].endswith("/login")

    def test_verify_session_with_placeholder_cookies_rejects_anonymous_user(self, session_url: str) -> None:
        response = httpx.get(
            f"{session_url}/verifySession/",
            headers={"X-Forwarded-Host": "next.localhost"},
            cookies={"sessionid": "missing-session", "hmac": "1000:invalid"},
            follow_redirects=False,
            timeout=10.0,
        )

        assert response.status_code == 401
        assert response.json()["href"].endswith("/login")
