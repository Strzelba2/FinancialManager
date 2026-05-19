from __future__ import annotations

import asyncio
import time
from statistics import quantiles
from uuid import uuid4

import allure
import httpx
import pytest


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _auth_cookie_names(response: httpx.Response) -> set[str]:
    return {cookie.name for cookie in response.cookies.jar}


def _headers(case_id: str, client_ip: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": f"http://next.localhost:8081/login?load={case_id}",
        "User-Agent": BROWSER_USER_AGENT,
        "Sec-CH-UA-Platform": '"Linux"',
        "X-Original-Client-IP": client_ip,
    }


def _p95(durations: list[float]) -> float:
    if len(durations) < 2:
        return durations[0]
    return quantiles(durations, n=20, method="inclusive")[18]


async def _post_login(
    client: httpx.AsyncClient,
    session_url: str,
    case_id: str,
    client_ip: str,
    email: str,
    password: str = "WrongPass123!",
) -> tuple[httpx.Response, float]:
    started = time.perf_counter()
    response = await client.post(
        f"{session_url}/login/",
        headers=_headers(case_id, client_ip),
        json={"email": email, "password": password},
    )
    return response, time.perf_counter() - started


@pytest.mark.security
@pytest.mark.performance
@allure.epic("Security")
@allure.feature("Performance")
@allure.story("Login security controls stay stable under abusive request bursts")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "performance", "login")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises abusive login bursts against session-auth. The suite verifies that throttle paths "
    "stay bounded, avoid server errors, and never create authenticated cookies."
)
class TestLoginSecurityLoad:
    def test_invalid_login_burst_from_many_ips_has_no_server_errors_or_sessions(self, session_url: str) -> None:
        async def scenario() -> tuple[list[httpx.Response], list[float]]:
            case_id = uuid4().hex[:8]
            async with httpx.AsyncClient(timeout=15.0) as client:
                tasks = [
                    _post_login(
                        client,
                        session_url,
                        case_id=case_id,
                        client_ip=f"10.242.{index}.10",
                        email=f"load-missing-{case_id}-{index}@example.com",
                    )
                    for index in range(1, 13)
                ]
                results = await asyncio.gather(*tasks)
                return [result[0] for result in results], [result[1] for result in results]

        responses, durations = asyncio.run(scenario())

        assert all(response.status_code == 401 for response in responses)
        assert all(response.status_code != 500 for response in responses)
        assert all("sessionid" not in _auth_cookie_names(response) for response in responses)
        assert all("hmac_token" not in _auth_cookie_names(response) for response in responses)
        assert _p95(durations) < 8.0

    def test_repeated_login_burst_from_one_ip_triggers_throttle_without_server_errors(self, session_url: str) -> None:
        async def scenario() -> tuple[list[httpx.Response], list[float]]:
            case_id = uuid4().hex[:8]
            client_ip = f"10.243.{int(case_id[:2], 16)}.10"
            async with httpx.AsyncClient(timeout=15.0) as client:
                results = []
                for index in range(5):
                    results.append(
                        await _post_login(
                            client,
                            session_url,
                            case_id=case_id,
                            client_ip=client_ip,
                            email=f"single-ip-load-{case_id}-{index}@example.com",
                        )
                    )
                return [result[0] for result in results], [result[1] for result in results]

        responses, durations = asyncio.run(scenario())

        assert [response.status_code for response in responses[:4]] == [401, 401, 401, 401]
        assert responses[4].status_code == 429
        assert all(response.status_code != 500 for response in responses)
        assert "sessionid" not in _auth_cookie_names(responses[4])
        assert "hmac_token" not in _auth_cookie_names(responses[4])
        assert _p95(durations) < 8.0
