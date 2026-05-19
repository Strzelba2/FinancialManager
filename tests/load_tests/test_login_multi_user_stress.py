from __future__ import annotations

import asyncio
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from statistics import quantiles
from threading import Barrier
from uuid import uuid4

import allure
import httpx
import psycopg
import pytest


PASSWORD = "StressPass123!"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MOBILE_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = int(raw_value)
    return max(minimum, min(value, maximum))


def _auth_cookie_names(response: httpx.Response) -> set[str]:
    return {cookie.name for cookie in response.cookies.jar}


def _headers(
    case_id: str,
    client_ip: str,
    referer_path: str = "/login",
    user_agent: str = BROWSER_USER_AGENT,
) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": f"http://next.localhost:8081{referer_path}?stress={case_id}",
        "User-Agent": user_agent,
        "Sec-CH-UA-Platform": '"Linux"',
        "X-Original-Client-IP": client_ip,
    }


def _p95(durations: list[float]) -> float:
    if len(durations) < 2:
        return durations[0]
    return quantiles(durations, n=20, method="inclusive")[18]


def _create_active_users(session_url: str, count: int, *, prefix: str) -> list[dict[str, str]]:
    suffix = uuid4().hex[:10]
    register_ip_second_octet = {
        "stress": 244,
        "device": 246,
        "mixed": 248,
        "capacity": 251,
    }.get(prefix, 249)
    register_ip_third_octet = int(suffix[:2], 16)
    users = []

    for index in range(count):
        user = {
            "first_name": "Stress",
            "last_name": "Tester",
            "username": f"{prefix}{suffix[:6]}{index:03d}",
            "email": f"{prefix}.{suffix}.{index}@example.com",
            "password": PASSWORD,
            "client_ip": f"10.{register_ip_second_octet}.{register_ip_third_octet}.{index + 1}",
        }
        response = httpx.post(
            f"{session_url}/register/",
            headers=_headers(
                f"register-{suffix}-{index}",
                user["client_ip"],
                referer_path="/register",
            ),
            json={key: value for key, value in user.items() if key != "client_ip"},
            timeout=15.0,
        )
        assert response.status_code == 201, response.text
        users.append(user)

    with psycopg.connect(
        host="session-db",
        port=5432,
        dbname="session_test",
        user="myuser",
        password="mypassword",
    ) as conn:
        with conn.cursor() as cursor:
            for user in users:
                cursor.execute(
                    """
                    UPDATE userauth_user
                       SET is_active = TRUE,
                           is_verified = TRUE
                     WHERE email = %s
                 RETURNING id
                    """,
                    (user["email"],),
                )
                row = cursor.fetchone()
                assert row is not None
                user["id"] = str(row[0])

    return users


async def _timed_request(awaitable) -> tuple[httpx.Response, float]:
    started = time.perf_counter()
    response = await awaitable
    return response, time.perf_counter() - started


async def _login(
    client: httpx.AsyncClient,
    session_url: str,
    user: dict[str, str],
    case_id: str,
    client_ip: str,
    password: str = PASSWORD,
    user_agent: str = BROWSER_USER_AGENT,
) -> tuple[httpx.Response, float]:
    return await _timed_request(
        client.post(
            f"{session_url}/login/",
            headers=_headers(case_id, client_ip, user_agent=user_agent),
            json={"email": user["email"], "password": password},
        )
    )


async def _verify_session(
    client: httpx.AsyncClient,
    session_url: str,
    sessionid: str,
    hmac_token: str,
    case_id: str,
    client_ip: str,
    user_agent: str = BROWSER_USER_AGENT,
) -> tuple[httpx.Response, float]:
    return await _timed_request(
        client.get(
            f"{session_url}/verifySession/",
            headers={
                "Accept": "application/json",
                "Cookie": f"sessionid={sessionid}; hmac={hmac_token}",
                "X-Forwarded-Host": "next.localhost",
                "User-Agent": user_agent,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": client_ip,
                "X-Login-Stress-Case": case_id,
            },
            follow_redirects=False,
        )
    )


async def _logout(
    client: httpx.AsyncClient,
    session_url: str,
    sessionid: str,
    hmac_token: str,
    case_id: str,
    client_ip: str,
    user_agent: str = BROWSER_USER_AGENT,
) -> tuple[httpx.Response, float]:
    return await _timed_request(
        client.post(
            f"{session_url}/logout/",
            headers={
                **_headers(case_id, client_ip, referer_path="/logout", user_agent=user_agent),
                "Cookie": f"sessionid={sessionid}; hmac={hmac_token}",
            },
        )
    )


def _login_sync(
    session_url: str,
    user: dict[str, str],
    case_id: str,
    client_ip: str,
    password: str = PASSWORD,
    user_agent: str = BROWSER_USER_AGENT,
) -> tuple[httpx.Response, float]:
    with httpx.Client(timeout=30.0) as client:
        started = time.perf_counter()
        response = client.post(
            f"{session_url}/login/",
            headers=_headers(case_id, client_ip, user_agent=user_agent),
            json={"email": user["email"], "password": password},
        )
        return response, time.perf_counter() - started


def _login_after_barrier(
    barrier: Barrier,
    session_url: str,
    user: dict[str, str],
    case_id: str,
    client_ip: str,
    password: str = PASSWORD,
    user_agent: str = BROWSER_USER_AGENT,
) -> tuple[httpx.Response, float]:
    barrier.wait(timeout=20.0)
    return _login_sync(
        session_url,
        user,
        case_id=case_id,
        client_ip=client_ip,
        password=password,
        user_agent=user_agent,
    )


def _verify_session_sync(
    session_url: str,
    sessionid: str,
    hmac_token: str,
    case_id: str,
    client_ip: str,
    user_agent: str = BROWSER_USER_AGENT,
) -> tuple[httpx.Response, float]:
    with httpx.Client(timeout=30.0) as client:
        started = time.perf_counter()
        response = client.get(
            f"{session_url}/verifySession/",
            headers={
                "Accept": "application/json",
                "Cookie": f"sessionid={sessionid}; hmac={hmac_token}",
                "X-Forwarded-Host": "next.localhost",
                "User-Agent": user_agent,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": client_ip,
                "X-Login-Stress-Case": case_id,
            },
            follow_redirects=False,
        )
        return response, time.perf_counter() - started


def _logout_sync(
    session_url: str,
    sessionid: str,
    hmac_token: str,
    case_id: str,
    client_ip: str,
    user_agent: str = BROWSER_USER_AGENT,
) -> tuple[httpx.Response, float]:
    with httpx.Client(timeout=30.0) as client:
        started = time.perf_counter()
        response = client.post(
            f"{session_url}/logout/",
            headers={
                **_headers(case_id, client_ip, referer_path="/logout", user_agent=user_agent),
                "Cookie": f"sessionid={sessionid}; hmac={hmac_token}",
            },
        )
        return response, time.perf_counter() - started


@pytest.mark.security
@pytest.mark.performance
@pytest.mark.load
@pytest.mark.stress
@allure.epic("Security")
@allure.feature("Load")
@allure.story("Login and session controls remain correct under multi-user stress")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "performance", "load", "stress", "login")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises heavier multi-user login, session verification, logout, invalid credential, "
    "threaded race, and second-device pressure scenarios through the real session-auth "
    "service and test database. The default profile is sized for test-all, while environment "
    "variables can raise the request volume for deeper local stress evidence."
)
class TestLoginMultiUserStress:
    def test_many_users_login_verify_logout_without_session_cross_contamination(
        self,
        session_url: str,
    ) -> None:
        user_count = _env_int("LOGIN_STRESS_USERS", 24, minimum=4, maximum=120)
        cycles = _env_int("LOGIN_STRESS_CYCLES", 2, minimum=1, maximum=10)
        concurrency = _env_int("LOGIN_STRESS_CONCURRENCY", 16, minimum=2, maximum=80)
        p95_limit = float(os.getenv("LOGIN_STRESS_P95_SECONDS", "20"))
        users = _create_active_users(session_url, user_count, prefix="stress")

        async def user_journey(index: int, user: dict[str, str], semaphore: asyncio.Semaphore) -> list[float]:
            durations = []
            async with httpx.AsyncClient(timeout=30.0) as client:
                for cycle in range(cycles):
                    case_id = f"multi-{index}-{cycle}-{uuid4().hex[:6]}"
                    client_ip = f"10.245.{index // 200}.{(index % 200) + 1}"

                    async with semaphore:
                        login_response, duration = await _login(
                            client,
                            session_url,
                            user,
                            case_id=case_id,
                            client_ip=client_ip,
                        )
                    durations.append(duration)
                    assert login_response.status_code == 200, login_response.text
                    sessionid = login_response.cookies.get("sessionid")
                    hmac_token = login_response.cookies.get("hmac_token")
                    assert sessionid
                    assert hmac_token

                    async with semaphore:
                        verify_response, duration = await _verify_session(
                            client,
                            session_url,
                            sessionid=sessionid,
                            hmac_token=hmac_token,
                            case_id=case_id,
                            client_ip=client_ip,
                        )
                    durations.append(duration)
                    assert verify_response.status_code == 200, verify_response.text
                    assert verify_response.headers["X-Email"] == user["email"]
                    refreshed_hmac = verify_response.cookies.get("hmac") or hmac_token

                    async with semaphore:
                        logout_response, duration = await _logout(
                            client,
                            session_url,
                            sessionid=sessionid,
                            hmac_token=refreshed_hmac,
                            case_id=case_id,
                            client_ip=client_ip,
                        )
                    durations.append(duration)
                    assert logout_response.status_code == 200, logout_response.text

                    async with semaphore:
                        rejected_response, duration = await _verify_session(
                            client,
                            session_url,
                            sessionid=sessionid,
                            hmac_token=refreshed_hmac,
                            case_id=case_id,
                            client_ip=client_ip,
                        )
                    durations.append(duration)
                    assert rejected_response.status_code in {302, 400, 401}

            return durations

        async def scenario() -> list[float]:
            semaphore = asyncio.Semaphore(concurrency)
            journeys = [
                user_journey(index, user, semaphore)
                for index, user in enumerate(users)
            ]
            nested_durations = await asyncio.gather(*journeys)
            return [duration for durations in nested_durations for duration in durations]

        durations = asyncio.run(scenario())

        assert len(durations) == user_count * cycles * 4
        assert _p95(durations) < p95_limit

    def test_second_fingerprint_pressure_never_receives_new_auth_cookies(
        self,
        session_url: str,
    ) -> None:
        attempt_count = _env_int("LOGIN_STRESS_SECOND_DEVICE_ATTEMPTS", 24, minimum=6, maximum=120)
        user = _create_active_users(session_url, 1, prefix="device")[0]

        async def scenario() -> tuple[httpx.Response, list[httpx.Response], list[float]]:
            async with httpx.AsyncClient(timeout=30.0) as first_client:
                first_login, _ = await _login(
                    first_client,
                    session_url,
                    user,
                    case_id="second-device-primary",
                    client_ip="10.246.1.10",
                    user_agent=BROWSER_USER_AGENT,
                )

            start = asyncio.Event()

            async def second_device_attempt(index: int) -> tuple[httpx.Response, float]:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await start.wait()
                    return await _login(
                        client,
                        session_url,
                        user,
                        case_id=f"second-device-{index}",
                        client_ip=f"10.247.{index // 200}.{(index % 200) + 1}",
                        user_agent=MOBILE_USER_AGENT,
                    )

            tasks = [
                asyncio.create_task(second_device_attempt(index))
                for index in range(attempt_count)
            ]
            start.set()
            results = await asyncio.gather(*tasks)
            return first_login, [result[0] for result in results], [result[1] for result in results]

        first_login, responses, durations = asyncio.run(scenario())

        assert first_login.status_code == 200, first_login.text
        assert first_login.cookies.get("sessionid")
        assert first_login.cookies.get("hmac_token")
        assert all(response.status_code in {401, 409, 429} for response in responses)
        assert all(response.status_code != 500 for response in responses)
        assert all("sessionid" not in _auth_cookie_names(response) for response in responses)
        assert all("hmac_token" not in _auth_cookie_names(response) for response in responses)
        assert any(response.status_code == 409 for response in responses)
        assert _p95(durations) < float(os.getenv("LOGIN_STRESS_P95_SECONDS", "20"))

    def test_mixed_valid_and_invalid_logins_keep_failures_unauthenticated_under_pressure(
        self,
        session_url: str,
    ) -> None:
        user_count = _env_int("LOGIN_STRESS_MIXED_USERS", 20, minimum=4, maximum=120)
        users = _create_active_users(session_url, user_count, prefix="mixed")

        async def scenario() -> tuple[list[httpx.Response], list[httpx.Response], list[float]]:
            start = asyncio.Event()

            async def login_attempt(index: int, user: dict[str, str]) -> tuple[bool, httpx.Response, float]:
                valid_attempt = index % 2 == 0
                password = PASSWORD if valid_attempt else "WrongPass123!"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await start.wait()
                    response, duration = await _login(
                        client,
                        session_url,
                        user,
                        case_id=f"mixed-{index}",
                        client_ip=f"10.248.{index // 200}.{(index % 200) + 1}",
                        password=password,
                    )
                    return valid_attempt, response, duration

            tasks = [
                asyncio.create_task(login_attempt(index, user))
                for index, user in enumerate(users)
            ]
            start.set()
            results = await asyncio.gather(*tasks)
            valid_responses = [response for valid, response, _ in results if valid]
            invalid_responses = [response for valid, response, _ in results if not valid]
            durations = [duration for _, _, duration in results]
            return valid_responses, invalid_responses, durations

        valid_responses, invalid_responses, durations = asyncio.run(scenario())

        assert all(response.status_code == 200 for response in valid_responses)
        assert all(response.cookies.get("sessionid") for response in valid_responses)
        assert all(response.cookies.get("hmac_token") for response in valid_responses)
        assert all(response.status_code in {401, 429} for response in invalid_responses)
        assert all("sessionid" not in _auth_cookie_names(response) for response in invalid_responses)
        assert all("hmac_token" not in _auth_cookie_names(response) for response in invalid_responses)
        assert all(response.status_code != 500 for response in valid_responses + invalid_responses)
        assert _p95(durations) < float(os.getenv("LOGIN_STRESS_P95_SECONDS", "20"))

    def test_threaded_many_unique_users_login_verify_and_logout_without_identity_leakage(
        self,
        session_url: str,
    ) -> None:
        user_count = _env_int("LOGIN_STRESS_CONCURRENT_USERS", 48, minimum=8, maximum=200)
        p95_limit = float(os.getenv("LOGIN_STRESS_P95_SECONDS", "20"))
        users = _create_active_users(session_url, user_count, prefix="capacity")
        login_barrier = Barrier(user_count + 1)

        def login_attempt(index: int, user: dict[str, str]) -> tuple[int, dict[str, str], httpx.Response, float]:
            client_ip = f"10.252.{index // 200}.{(index % 200) + 1}"
            response, duration = _login_after_barrier(
                login_barrier,
                session_url,
                user,
                case_id=f"capacity-login-{index}",
                client_ip=client_ip,
            )
            return index, user, response, duration

        with ThreadPoolExecutor(max_workers=user_count) as executor:
            login_futures = [
                executor.submit(login_attempt, index, user)
                for index, user in enumerate(users)
            ]
            login_barrier.wait(timeout=20.0)
            login_results = [future.result(timeout=60.0) for future in login_futures]

        login_durations = [result[3] for result in login_results]
        login_statuses = Counter(result[2].status_code for result in login_results)

        assert login_statuses == Counter({200: user_count}), login_statuses
        assert _p95(login_durations) < p95_limit

        sessions = []
        for index, user, response, _ in login_results:
            sessionid = response.cookies.get("sessionid")
            hmac_token = response.cookies.get("hmac_token")
            assert sessionid
            assert hmac_token
            sessions.append(
                {
                    "index": index,
                    "user": user,
                    "sessionid": sessionid,
                    "hmac_token": hmac_token,
                    "client_ip": f"10.252.{index // 200}.{(index % 200) + 1}",
                }
            )

        verify_barrier = Barrier(user_count + 1)

        def verify_attempt(session: dict[str, object]) -> tuple[dict[str, object], httpx.Response, float]:
            verify_barrier.wait(timeout=20.0)
            response, duration = _verify_session_sync(
                session_url,
                sessionid=str(session["sessionid"]),
                hmac_token=str(session["hmac_token"]),
                case_id=f"capacity-verify-{session['index']}",
                client_ip=str(session["client_ip"]),
            )
            return session, response, duration

        with ThreadPoolExecutor(max_workers=user_count) as executor:
            verify_futures = [
                executor.submit(verify_attempt, session)
                for session in sessions
            ]
            verify_barrier.wait(timeout=20.0)
            verify_results = [future.result(timeout=60.0) for future in verify_futures]

        verify_durations = [result[2] for result in verify_results]
        verify_statuses = Counter(result[1].status_code for result in verify_results)

        assert verify_statuses == Counter({200: user_count}), verify_statuses
        assert _p95(verify_durations) < p95_limit

        for session, response, _ in verify_results:
            user = session["user"]
            assert isinstance(user, dict)
            assert response.headers["X-Email"] == user["email"]
            refreshed_hmac = response.cookies.get("hmac")
            if refreshed_hmac:
                session["hmac_token"] = refreshed_hmac

        logout_barrier = Barrier(user_count + 1)

        def logout_attempt(session: dict[str, object]) -> tuple[httpx.Response, float]:
            logout_barrier.wait(timeout=20.0)
            return _logout_sync(
                session_url,
                sessionid=str(session["sessionid"]),
                hmac_token=str(session["hmac_token"]),
                case_id=f"capacity-logout-{session['index']}",
                client_ip=str(session["client_ip"]),
            )

        with ThreadPoolExecutor(max_workers=user_count) as executor:
            logout_futures = [
                executor.submit(logout_attempt, session)
                for session in sessions
            ]
            logout_barrier.wait(timeout=20.0)
            logout_results = [future.result(timeout=60.0) for future in logout_futures]

        logout_responses = [result[0] for result in logout_results]
        logout_durations = [result[1] for result in logout_results]

        assert Counter(response.status_code for response in logout_responses) == Counter({200: user_count})
        assert _p95(logout_durations) < p95_limit

    def test_threaded_same_user_over_capacity_still_rejects_extra_sessions_safely(
        self,
        session_url: str,
    ) -> None:
        thread_count = _env_int("LOGIN_STRESS_RACE_THREADS", 12, minimum=2, maximum=80)
        user = _create_active_users(session_url, 1, prefix="race")[0]
        barrier = Barrier(thread_count + 1)

        def attempt(index: int) -> tuple[httpx.Response, float]:
            user_agent = BROWSER_USER_AGENT if index % 2 == 0 else MOBILE_USER_AGENT
            return _login_after_barrier(
                barrier,
                session_url,
                user,
                case_id=f"same-user-capacity-{index}",
                client_ip=f"10.253.{index // 200}.{(index % 200) + 1}",
                user_agent=user_agent,
            )

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [
                executor.submit(attempt, index)
                for index in range(thread_count)
            ]
            barrier.wait(timeout=20.0)
            results = [future.result(timeout=45.0) for future in futures]

        responses = [result[0] for result in results]
        durations = [result[1] for result in results]
        statuses = Counter(response.status_code for response in responses)
        successful_responses = [response for response in responses if response.status_code == 200]
        rejected_responses = [response for response in responses if response.status_code != 200]

        assert statuses[200] == 1, statuses
        assert len(successful_responses) == 1
        assert successful_responses[0].cookies.get("sessionid")
        assert successful_responses[0].cookies.get("hmac_token")
        assert all(response.status_code in {401, 409, 429} for response in rejected_responses)
        assert all("sessionid" not in _auth_cookie_names(response) for response in rejected_responses)
        assert all("hmac_token" not in _auth_cookie_names(response) for response in rejected_responses)
        assert all(response.status_code != 500 for response in responses)
        assert _p95(durations) < float(os.getenv("LOGIN_STRESS_P95_SECONDS", "20"))
