from __future__ import annotations

import allure
import httpx
import pytest


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MALICIOUS_STRINGS = [
    "",
    " ",
    "\x00",
    "\r\nInjected-Header: yes",
    "' OR '1'='1",
    "' OR '1'='1' --",
    "\" OR \"1\"=\"1",
    "'; DROP TABLE userauth_user; --",
    "<script>alert(1)</script>",
    "{{7*7}}",
    "${jndi:ldap://127.0.0.1/a}",
    "../" * 20,
    "A" * 4096,
]
TYPE_MUTATIONS = [
    None,
    True,
    False,
    0,
    1,
    [],
    ["nested@example.com"],
    {},
    {"email": "nested@example.com"},
]


def _auth_cookie_names(response: httpx.Response) -> set[str]:
    return {cookie.name for cookie in response.cookies.jar}


def _request_headers(case_id: str, index: int) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": f"http://next.localhost:8081/login?fuzz={case_id}",
        "User-Agent": BROWSER_USER_AGENT,
        "Sec-CH-UA-Platform": '"Linux"',
        "X-Original-Client-IP": f"10.241.{index // 200}.{(index % 200) + 1}",
    }


def _payload_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []

    for index, value in enumerate(MALICIOUS_STRINGS + TYPE_MUTATIONS, start=1):
        cases.append({"email": value, "password": "WrongPass123!"})
        cases.append({"email": f"fuzz-{index}@example.com", "password": value})

    cases.extend(
        [
            {},
            {"email": "missing-password@example.com"},
            {"password": "WrongPass123!"},
            {"email": ["array@example.com"], "password": ["WrongPass123!"]},
            {"email": {"$ne": None}, "password": {"$ne": None}},
            {"email": "duplicate@example.com", "password": "WrongPass123!", "extra": "ignored"},
        ]
    )
    return cases


@pytest.mark.security
@pytest.mark.fuzz
@allure.epic("Security")
@allure.feature("Security")
@allure.story("Login rejects deterministic fuzz payloads without sessions or server errors")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "fuzz", "login")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises malformed login payloads through the public session-auth endpoint. "
    "The suite verifies rejection without auth cookies, server tracebacks, or password echoes."
)
class TestLoginFuzzing:
    @pytest.mark.parametrize("case_index,payload", list(enumerate(_payload_cases(), start=1)))
    def test_login_fuzz_payload_is_rejected_without_session(
        self,
        session_url: str,
        case_index: int,
        payload: dict[str, object],
    ) -> None:
        case_id = f"case-{case_index}"
        response = httpx.post(
            f"{session_url}/login/",
            headers=_request_headers(case_id, index=case_index),
            json=payload,
            timeout=10.0,
        )

        assert response.status_code in {400, 401}
        assert response.status_code != 500
        assert "sessionid" not in _auth_cookie_names(response)
        assert "hmac" not in _auth_cookie_names(response)
        assert "hmac_token" not in _auth_cookie_names(response)
        assert "Traceback" not in response.text

        password = payload.get("password")
        if isinstance(password, str) and password.strip():
            assert password not in response.text
