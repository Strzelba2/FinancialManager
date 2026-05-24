from __future__ import annotations

import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import allure
import httpx
import psycopg
import pytest

from tests.helpers.totp import totp_code


PASSWORD = "ComponentPass123!"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _create_active_user(session_url: str) -> dict[str, str]:
    suffix = uuid4().hex[:8]
    ip_tail = int(suffix[:2], 16)
    user = {
        "first_name": "Component",
        "last_name": "Tester",
        "username": f"auth{suffix}"[:12],
        "email": f"auth.{suffix}@example.com",
        "password": PASSWORD,
        "client_ip": f"10.220.{ip_tail}.10",
    }

    response = httpx.post(
        f"{session_url}/register/",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": "http://next.localhost:8081/register",
            "User-Agent": BROWSER_USER_AGENT,
            "X-Original-Client-IP": user["client_ip"],
        },
        json={key: value for key, value in user.items() if key != "client_ip"},
        timeout=10.0,
    )
    assert response.status_code == 201, response.text

    with psycopg.connect(
        host="session-db",
        port=5432,
        dbname="session_test",
        user="myuser",
        password="mypassword",
    ) as conn:
        with conn.cursor() as cursor:
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

    return user


def _login(
    session_url: str,
    user: dict[str, str],
    password: str = PASSWORD,
    client_ip: str | None = None,
    user_agent: str = BROWSER_USER_AGENT,
    referer: str = "http://next.localhost:8081/login",
) -> httpx.Response:
    if client_ip is None:
        client_ip = f"10.222.{uuid4().int % 200}.{(uuid4().int % 200) + 1}"

    return httpx.post(
        f"{session_url}/login/",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": referer,
            "User-Agent": user_agent,
            "Sec-CH-UA-Platform": '"Linux"',
            "X-Original-Client-IP": client_ip,
        },
        json={"email": user["email"], "password": password},
        timeout=10.0,
    )


def _set_cookie_headers(response: httpx.Response) -> list[str]:
    return response.headers.get_list("set-cookie")


def _auth_cookie_names(response: httpx.Response) -> set[str]:
    return {cookie.name for cookie in response.cookies.jar}


def _set_user_two_factor(email: str, enabled: bool) -> None:
    with psycopg.connect(
        host="session-db",
        port=5432,
        dbname="session_test",
        user="myuser",
        password="mypassword",
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE userauth_user
                   SET is_two_factor = %s,
                       is_verified = FALSE
                 WHERE email = %s
             RETURNING id
                """,
                (enabled, email),
            )
            assert cursor.fetchone() is not None


def _verify_session(
    session_url: str,
    sessionid: str,
    hmac_token: str,
    user_agent: str = BROWSER_USER_AGENT,
    client_ip: str = "203.0.113.20",
) -> httpx.Response:
    return httpx.get(
        f"{session_url}/verifySession/",
        headers={
            "Accept": "application/json",
            "X-Forwarded-Host": "next.localhost",
            "User-Agent": user_agent,
            "Sec-CH-UA-Platform": '"Linux"',
            "X-Original-Client-IP": client_ip,
        },
        cookies={"sessionid": sessionid, "hmac": hmac_token},
        follow_redirects=False,
        timeout=10.0,
    )


def _read_redis_line(sock: socket.socket) -> bytes:
    chunks = []
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise RuntimeError("Redis connection closed while reading a line")
        if chunk == b"\r":
            if sock.recv(1) != b"\n":
                raise RuntimeError("Invalid Redis line ending")
            return b"".join(chunks)
        chunks.append(chunk)


def _read_redis_response(sock: socket.socket):
    prefix = sock.recv(1)
    if not prefix:
        raise RuntimeError("Redis connection closed while reading a response")
    if prefix == b"+":
        return _read_redis_line(sock).decode("utf-8")
    if prefix == b"-":
        raise RuntimeError(_read_redis_line(sock).decode("utf-8"))
    if prefix == b":":
        return int(_read_redis_line(sock))
    if prefix == b"$":
        length = int(_read_redis_line(sock))
        if length == -1:
            return None
        payload = bytearray()
        while len(payload) < length:
            payload.extend(sock.recv(length - len(payload)))
        if sock.recv(2) != b"\r\n":
            raise RuntimeError("Invalid Redis bulk string ending")
        return bytes(payload).decode("utf-8")
    if prefix == b"*":
        count = int(_read_redis_line(sock))
        if count == -1:
            return None
        return [_read_redis_response(sock) for _ in range(count)]
    raise RuntimeError(f"Unsupported Redis response prefix: {prefix!r}")


def _redis_command(sock: socket.socket, *parts: str):
    payload = [f"*{len(parts)}\r\n".encode("utf-8")]
    for part in parts:
        encoded = part.encode("utf-8")
        payload.append(f"${len(encoded)}\r\n".encode("utf-8"))
        payload.append(encoded)
        payload.append(b"\r\n")
    sock.sendall(b"".join(payload))
    return _read_redis_response(sock)


def _delete_cache_keys(pattern: str) -> int:
    deleted = 0
    with socket.create_connection(("redis", 6379), timeout=3.0) as sock:
        _redis_command(sock, "SELECT", "1")
        cursor = "0"
        while True:
            response = _redis_command(sock, "SCAN", cursor, "MATCH", pattern, "COUNT", "100")
            cursor = str(response[0])
            keys = [str(key) for key in response[1]]
            if keys:
                deleted += int(_redis_command(sock, "DEL", *keys))
            if cursor == "0":
                break
    return deleted


@pytest.mark.component
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Next UI protected routes cannot be reached by spoofing identity headers")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("next-ui", "auth", "security", "forwardauth")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestNextUiForwardAuthBypass:
    @pytest.mark.parametrize(
        "path",
        [
            "/wallet",
            "/transactions",
            "/wallet-manager",
            "/user/favorites",
            "/brokerage/holdings",
        ],
    )
    def test_spoofed_identity_headers_without_auth_cookies_still_show_login(
        self,
        traefik_url: str,
        path: str,
    ) -> None:
        response = httpx.get(
            f"{traefik_url}{path}",
            headers={
                "Host": "next.localhost",
                "X-User": "spoofed-user",
                "X-First-Name": "Spoofed",
                "X-Email": "spoofed@example.com",
                "X-User-Id": str(uuid4()),
            },
            follow_redirects=True,
            timeout=10.0,
        )

        assert response.status_code in {401, 403, 307, 308} or (
            response.status_code == 200
            and "FinancialManager" in response.text
            and ("Zaloguj" in response.text or "Please login" in response.text)
        )
        assert "Portfel" not in response.text

    def test_direct_next_ui_service_does_not_trust_spoofed_identity_headers(self) -> None:
        response = httpx.get(
            "http://next-ui:3000/wallet",
            headers={
                "X-User": "spoofed-user",
                "X-First-Name": "Spoofed",
                "X-Email": "spoofed@example.com",
                "X-User-Id": str(uuid4()),
            },
            follow_redirects=True,
            timeout=10.0,
        )

        assert response.status_code in {401, 403, 307, 308} or (
            "FinancialManager" in response.text
            and ("Zaloguj" in response.text or "Please login" in response.text)
        )
        assert "WalletManager" not in response.text
        assert "Portfel" not in response.text


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Session verification rejects partial, malformed, and unauthenticated cookies")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("session", "auth", "security", "hmac")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestVerifySessionCookieBypass:
    @pytest.mark.parametrize(
        "cookies",
        [
            {"sessionid": "session-only"},
            {"hmac": "1000:hmac-only"},
            {"sessionid": "", "hmac": ""},
            {"sessionid": "missing-session", "hmac": "not-a-valid-hmac"},
            {"sessionid": "missing-session", "hmac": "1000:tampered"},
        ],
    )
    def test_verify_session_rejects_cookie_bypass_variants(
        self,
        session_url: str,
        cookies: dict[str, str],
    ) -> None:
        response = httpx.get(
            f"{session_url}/verifySession/",
            headers={
                "Accept": "application/json",
                "X-Forwarded-Host": "next.localhost",
                "User-Agent": BROWSER_USER_AGENT,
                "Sec-CH-UA-Platform": '"Linux"',
            },
            cookies=cookies,
            follow_redirects=False,
            timeout=10.0,
        )

        assert response.status_code in {400, 401, 302}
        assert response.status_code != 200


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Login IP throttle blocks abusive clients and records BlockedIP evidence")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("session", "auth", "security", "throttle")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestLoginIpThrottle:
    def test_repeated_login_attempts_from_same_ip_trigger_drf_throttle_and_blocked_ip(
        self,
        session_url: str,
    ) -> None:
        suffix = uuid4().hex[:8]
        client_ip = f"10.228.{int(suffix[:2], 16)}.10"
        responses = []

        for index in range(5):
            response = httpx.post(
                f"{session_url}/login/",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Referer": "http://next.localhost:8081/login",
                    "User-Agent": BROWSER_USER_AGENT,
                    "X-Original-Client-IP": client_ip,
                },
                json={
                    "email": f"ip-throttle-{suffix}-{index}@example.com",
                    "password": "WrongPass123!",
                },
                timeout=10.0,
            )
            responses.append(response)

        assert [response.status_code for response in responses[:4]] == [401, 401, 401, 401]
        assert responses[4].status_code == 429
        assert "sessionid" not in _auth_cookie_names(responses[4])
        assert "hmac_token" not in _auth_cookie_names(responses[4])

        with psycopg.connect(
            host="session-db",
            port=5432,
            dbname="session_test",
            user="myuser",
            password="mypassword",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ip_address, is_temporary, user_agent, referer, endpoint
                      FROM userauth_blockedip
                     WHERE referer = %s
                       AND endpoint = %s
                     ORDER BY blocked_at DESC
                     LIMIT 1
                    """,
                    ("http://next.localhost:8081/login", "/login/"),
                )
                row = cursor.fetchone()

        assert row is not None
        assert row[1:] == (
            True,
            BROWSER_USER_AGENT,
            "http://next.localhost:8081/login",
            "/login/",
        )


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Login cookie, session fixation, and 2FA contracts are enforced")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("session", "auth", "security", "cookies")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestLoginSessionCookieContract:
    def test_successful_login_returns_session_and_hmac_cookies(self, session_url: str) -> None:
        user = _create_active_user(session_url)

        response = _login(session_url, user)

        assert response.status_code == 200
        assert response.json() == {"message": "Login successful"}
        assert response.cookies.get("sessionid")
        assert response.cookies.get("hmac_token")
        set_cookie_headers = "\n".join(_set_cookie_headers(response)).lower()
        assert "httponly" in set_cookie_headers
        assert "samesite=lax" in set_cookie_headers
        hmac_cookie = next(
            header for header in _set_cookie_headers(response)
            if header.startswith("hmac_token=")
        ).lower()
        assert "secure" in hmac_cookie

    def test_rejected_login_does_not_set_auth_cookies(self, session_url: str) -> None:
        user = _create_active_user(session_url)

        response = _login(session_url, user, password="WrongPass123!")

        assert response.status_code == 401
        assert "sessionid" not in _auth_cookie_names(response)
        assert "hmac_token" not in _auth_cookie_names(response)
        assert "hmac" not in _auth_cookie_names(response)

    def test_login_rotates_preexisting_sessionid_to_prevent_session_fixation(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        fixed_session_id = "attacker-fixed-session"

        with httpx.Client(
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/login",
                "User-Agent": BROWSER_USER_AGENT,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": "203.0.113.21",
            },
            timeout=10.0,
        ) as client:
            client.cookies.set("sessionid", fixed_session_id, domain="session-auth", path="/")
            response = client.post(
                f"{session_url}/login/",
                json={"email": user["email"], "password": user["password"]},
            )

        assert response.status_code == 200
        assert response.cookies.get("sessionid") is not None
        assert response.cookies.get("sessionid") != fixed_session_id
        assert response.cookies.get("hmac_token") is not None

    def test_two_factor_login_requires_totp_before_hmac_cookie_is_issued(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        _set_user_two_factor(user["email"], enabled=True)
        client_ip = "10.222.2.42"

        login_response = _login(session_url, user, client_ip=client_ip)

        assert login_response.status_code == 202
        assert login_response.json() == {"requires_two_factor": True}
        sessionid = login_response.cookies.get("sessionid")
        assert sessionid
        assert "hmac_token" not in _auth_cookie_names(login_response)

        invalid_response = httpx.post(
            f"{session_url}/two-factor/verify/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/two-factor",
                "User-Agent": BROWSER_USER_AGENT,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": client_ip,
            },
            cookies={"sessionid": sessionid},
            json={"token": "000000"},
            timeout=10.0,
        )
        assert invalid_response.status_code == 401
        assert "hmac_token" not in _auth_cookie_names(invalid_response)

        valid_response = httpx.post(
            f"{session_url}/two-factor/verify/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/two-factor",
                "User-Agent": BROWSER_USER_AGENT,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": client_ip,
            },
            cookies={"sessionid": sessionid},
            json={"token": totp_code(user["email"], user["username"])},
            timeout=10.0,
        )

        assert valid_response.status_code == 200
        hmac_token = valid_response.cookies.get("hmac_token")
        assert hmac_token
        verify_response = _verify_session(
            session_url,
            sessionid,
            hmac_token,
            client_ip=client_ip,
        )
        assert verify_response.status_code == 200

    def test_new_two_factor_login_invalidates_previous_pending_challenge(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        _set_user_two_factor(user["email"], enabled=True)

        first_login = _login(
            session_url,
            user,
            client_ip="10.222.2.44",
            user_agent=BROWSER_USER_AGENT,
        )
        first_sessionid = first_login.cookies.get("sessionid")
        assert first_login.status_code == 202
        assert first_sessionid

        second_login = _login(
            session_url,
            user,
            client_ip="10.222.2.45",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        )
        second_sessionid = second_login.cookies.get("sessionid")
        assert second_login.status_code == 202
        assert second_sessionid

        stale_verify = httpx.post(
            f"{session_url}/two-factor/verify/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/two-factor",
                "User-Agent": BROWSER_USER_AGENT,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": "10.222.2.44",
            },
            cookies={"sessionid": first_sessionid},
            json={"token": totp_code(user["email"], user["username"])},
            timeout=10.0,
        )

        assert stale_verify.status_code == 409
        assert stale_verify.json() == {"error": "Two-factor verification expired. Please log in again."}
        assert "hmac_token" not in _auth_cookie_names(stale_verify)

        current_verify = httpx.post(
            f"{session_url}/two-factor/verify/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/two-factor",
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                "Sec-CH-UA-Platform": '"iOS"',
                "X-Original-Client-IP": "10.222.2.45",
            },
            cookies={"sessionid": second_sessionid},
            json={"token": totp_code(user["email"], user["username"])},
            timeout=10.0,
        )

        assert current_verify.status_code == 200
        assert current_verify.cookies.get("hmac_token")

    def test_two_factor_setup_does_not_enable_until_totp_is_confirmed(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        login_response = _login(session_url, user, client_ip="10.222.2.43")
        sessionid = login_response.cookies.get("sessionid")
        hmac_token = login_response.cookies.get("hmac_token")
        assert login_response.status_code == 200
        assert sessionid
        assert hmac_token

        setup_response = httpx.post(
            f"{session_url}/two-factor/setup/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/settings/profile",
                "User-Agent": BROWSER_USER_AGENT,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": "10.222.2.43",
            },
            cookies={"sessionid": sessionid, "hmac": hmac_token},
            json={},
            timeout=10.0,
        )

        assert setup_response.status_code == 200
        assert setup_response.json()["image"]

        status_response = httpx.get(
            f"{session_url}/two-factor/status/",
            headers={
                "Accept": "application/json",
                "Referer": "http://next.localhost:8081/settings/profile",
                "User-Agent": BROWSER_USER_AGENT,
                "X-Original-Client-IP": "10.222.2.43",
            },
            cookies={"sessionid": sessionid, "hmac": hmac_token},
            timeout=10.0,
        )
        assert status_response.status_code == 200
        assert status_response.json() == {"is_two_factor_enabled": False}

        enable_response = httpx.post(
            f"{session_url}/two-factor/enable/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/settings/profile",
                "User-Agent": BROWSER_USER_AGENT,
                "Sec-CH-UA-Platform": '"Linux"',
                "X-Original-Client-IP": "10.222.2.43",
            },
            cookies={"sessionid": sessionid, "hmac": hmac_token},
            json={"token": totp_code(user["email"], user["username"])},
            timeout=10.0,
        )

        assert enable_response.status_code == 200
        assert enable_response.json() == {"is_two_factor_enabled": True}

    def test_inactive_user_is_rejected_without_auth_cookies(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        with psycopg.connect(
            host="session-db",
            port=5432,
            dbname="session_test",
            user="myuser",
            password="mypassword",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE userauth_user SET is_active = FALSE WHERE email = %s", (user["email"],))

        response = _login(session_url, user)

        assert response.status_code == 401
        assert "sessionid" not in _auth_cookie_names(response)
        assert "hmac_token" not in _auth_cookie_names(response)

    def test_blocked_user_correct_login_is_rejected_with_permanent_block_contract(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        with psycopg.connect(
            host="session-db",
            port=5432,
            dbname="session_test",
            user="myuser",
            password="mypassword",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE userauth_user SET is_blocked = TRUE WHERE email = %s", (user["email"],))

        response = _login(session_url, user, client_ip="10.223.1.10")

        assert response.status_code == 401
        assert response.json()["blocked_permanently"] is True
        assert "sessionid" not in _auth_cookie_names(response)
        assert "hmac_token" not in _auth_cookie_names(response)

    @pytest.mark.parametrize(
        "payload",
        [
            {"email": "' OR '1'='1", "password": "anything"},
            {"email": "' OR '1'='1' --", "password": "anything"},
            {"email": "admin@example.com'--", "password": "anything"},
            {"email": "\" OR \"1\"=\"1", "password": "anything"},
            {"email": "sqli-password-1@example.com", "password": "' OR '1'='1"},
            {"email": "sqli-password-2@example.com", "password": "' OR '1'='1' --"},
            {"email": "sqli-password-3@example.com", "password": "\" OR \"1\"=\"1"},
            {"email": "sqli-password-4@example.com", "password": "'; DROP TABLE userauth_user; --"},
            {"email": "xss@example.com", "password": "<script>alert(1)</script>"},
            {"email": "missing@example.com", "password": "WrongPass123!"},
        ],
    )
    def test_injection_style_login_payloads_are_rejected_safely_without_sessions(
        self,
        session_url: str,
        payload: dict[str, str],
    ) -> None:
        response = httpx.post(
            f"{session_url}/login/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/login",
                "User-Agent": BROWSER_USER_AGENT,
                "X-Original-Client-IP": f"10.221.{uuid4().int % 200}.10",
            },
            json=payload,
            timeout=10.0,
        )

        assert response.status_code in {400, 401}
        assert response.status_code != 500
        assert "sessionid" not in _auth_cookie_names(response)
        assert "hmac_token" not in _auth_cookie_names(response)
        assert payload["password"] not in response.text

    @pytest.mark.parametrize(
        "headers",
        [
            {"User-Agent": BROWSER_USER_AGENT},
            {"Referer": "http://evil.example/login", "User-Agent": BROWSER_USER_AGENT},
            {"Referer": "http://next.localhost:8081/login", "User-Agent": ""},
        ],
    )
    def test_login_request_header_abuse_is_rejected_before_authentication(
        self,
        session_url: str,
        headers: dict[str, str],
    ) -> None:
        response = httpx.post(
            f"{session_url}/login/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                **headers,
            },
            json={"email": "header-abuse@example.com", "password": "WrongPass123!"},
            timeout=10.0,
        )

        assert response.status_code == 400
        assert "sessionid" not in _auth_cookie_names(response)
        assert "hmac_token" not in _auth_cookie_names(response)

    def test_direct_login_post_cannot_bypass_referer_with_spoofed_original_client_ip(
        self,
        session_url: str,
    ) -> None:
        response = httpx.post(
            f"{session_url}/login/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": BROWSER_USER_AGENT,
                "X-Original-Client-IP": "198.51.100.200",
            },
            json={"email": "spoofed-ip@example.com", "password": "WrongPass123!"},
            timeout=10.0,
        )

        assert response.status_code == 400
        assert "sessionid" not in _auth_cookie_names(response)
        assert "hmac_token" not in _auth_cookie_names(response)

    def test_verify_session_accepts_current_hmac_and_rejects_replay_variants(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        client_ip = "10.227.1.10"
        login_response = _login(session_url, user, client_ip=client_ip)
        sessionid = login_response.cookies.get("sessionid")
        hmac_token = login_response.cookies.get("hmac_token")
        assert sessionid
        assert hmac_token

        valid_response = _verify_session(
            session_url,
            sessionid=sessionid,
            hmac_token=hmac_token,
            client_ip=client_ip,
        )
        assert valid_response.status_code == 200
        assert valid_response.headers["X-Email"] == user["email"]

        replay_response = _verify_session(
            session_url,
            sessionid=sessionid,
            hmac_token=hmac_token,
            user_agent="Different Browser",
            client_ip=client_ip,
        )

        assert replay_response.status_code in {302, 400, 401}

    def test_verify_session_refreshes_hmac_cookie_value(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        client_ip = "10.227.2.10"
        login_response = _login(session_url, user, client_ip=client_ip)
        sessionid = login_response.cookies.get("sessionid")
        hmac_token = login_response.cookies.get("hmac_token")
        assert sessionid
        assert hmac_token

        deadline = time.monotonic() + 2
        refreshed_hmac = hmac_token
        verify_response = None
        while time.monotonic() < deadline and refreshed_hmac == hmac_token:
            verify_response = _verify_session(
                session_url,
                sessionid=sessionid,
                hmac_token=hmac_token,
                client_ip=client_ip,
            )
            refreshed_hmac = verify_response.cookies.get("hmac", hmac_token)

        assert verify_response is not None
        assert verify_response.status_code == 200
        assert refreshed_hmac != hmac_token
        set_cookie_headers = "\n".join(_set_cookie_headers(verify_response)).lower()
        assert "hmac=" in set_cookie_headers
        assert "httponly" in set_cookie_headers
        assert "secure" in set_cookie_headers
        assert "samesite=lax" in set_cookie_headers

    def test_wallet_user_id_is_forwarded_after_session_mapping_is_saved(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        client_ip = "10.227.3.10"
        login_response = _login(session_url, user, client_ip=client_ip)
        sessionid = login_response.cookies.get("sessionid")
        hmac_token = login_response.cookies.get("hmac_token")
        wallet_user_id = str(uuid4())
        assert sessionid
        assert hmac_token

        save_response = httpx.post(
            f"{session_url}/wallet-user-id/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/wallet",
                "User-Agent": BROWSER_USER_AGENT,
                "X-Original-Client-IP": client_ip,
            },
            cookies={"sessionid": sessionid, "hmac": hmac_token},
            json={"wallet_user_id": wallet_user_id},
            timeout=10.0,
        )
        assert save_response.status_code == 200

        verify_response = _verify_session(
            session_url,
            sessionid=sessionid,
            hmac_token=hmac_token,
            client_ip=client_ip,
        )

        assert verify_response.status_code == 200
        assert verify_response.headers["X-User-Id"] == wallet_user_id

    def test_logout_flushes_session_deletes_auth_cookies_and_rejects_reuse(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        client_ip = "10.227.4.10"
        login_response = _login(session_url, user, client_ip=client_ip)
        sessionid = login_response.cookies.get("sessionid")
        hmac_token = login_response.cookies.get("hmac_token")
        assert sessionid
        assert hmac_token

        logout_response = httpx.post(
            f"{session_url}/logout/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/logout",
                "User-Agent": BROWSER_USER_AGENT,
                "X-Original-Client-IP": client_ip,
            },
            cookies={"sessionid": sessionid, "hmac": hmac_token},
            timeout=10.0,
        )

        assert logout_response.status_code == 200
        assert logout_response.json() == {"message": "Logout successful"}
        set_cookie_headers = "\n".join(_set_cookie_headers(logout_response)).lower()
        assert "hmac=" in set_cookie_headers
        assert "max-age=0" in set_cookie_headers or "expires=thu, 01 jan 1970" in set_cookie_headers

        verify_response = _verify_session(
            session_url,
            sessionid=sessionid,
            hmac_token=hmac_token,
            client_ip=client_ip,
        )

        assert verify_response.status_code in {302, 400, 401}

    def test_same_fingerprint_can_login_again_and_refresh_active_login(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        client_ip = "10.227.5.10"

        first_login = _login(session_url, user, client_ip=client_ip)
        second_login = _login(session_url, user, client_ip=client_ip)

        assert first_login.status_code == 200
        assert second_login.status_code == 200
        assert second_login.cookies.get("sessionid")
        assert second_login.cookies.get("hmac_token")

    def test_logout_removes_active_login_so_different_fingerprint_can_login(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        first_login = _login(session_url, user, client_ip="10.227.6.10")
        sessionid = first_login.cookies.get("sessionid")
        hmac_token = first_login.cookies.get("hmac_token")
        assert first_login.status_code == 200
        assert sessionid
        assert hmac_token

        logout_response = httpx.post(
            f"{session_url}/logout/",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "http://next.localhost:8081/logout",
                "User-Agent": BROWSER_USER_AGENT,
                "X-Original-Client-IP": "10.227.6.10",
            },
            cookies={"sessionid": sessionid, "hmac": hmac_token},
            timeout=10.0,
        )
        assert logout_response.status_code == 200

        second_login = _login(
            session_url,
            user,
            client_ip="10.227.7.10",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        )

        assert second_login.status_code == 200
        assert second_login.cookies.get("sessionid")
        assert second_login.cookies.get("hmac_token")

    def test_expired_active_login_allows_different_fingerprint_login(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        first_login = _login(
            session_url,
            user,
            client_ip="10.227.8.10",
            user_agent=BROWSER_USER_AGENT,
        )
        assert first_login.status_code == 200

        deleted = _delete_cache_keys(f"*active_login:{user['id']}")
        assert deleted >= 1

        second_login = _login(
            session_url,
            user,
            client_ip="10.227.9.10",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        )

        assert second_login.status_code == 200
        assert second_login.cookies.get("sessionid")
        assert second_login.cookies.get("hmac_token")

    def test_repeated_invalid_passwords_return_temporary_block_metadata(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        responses = [
            _login(
                session_url,
                user,
                password="WrongPass123!",
                client_ip=f"10.224.{index}.10",
            )
            for index in range(1, 5)
        ]

        assert [response.status_code for response in responses[:3]] == [401, 401, 401]
        blocked = responses[3]
        payload = blocked.json()
        assert blocked.status_code == 429
        assert payload["blocked_permanently"] is False
        assert payload["retry_after_seconds"] > 0
        assert payload["retry_after_human"]
        assert "blocked_until" in payload
        assert "sessionid" not in _auth_cookie_names(blocked)
        assert "hmac_token" not in _auth_cookie_names(blocked)

    def test_repeated_temporary_blocks_escalate_to_permanent_user_block(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        responses = [
            _login(
                session_url,
                user,
                password="WrongPass123!",
                client_ip=f"10.225.{index}.10",
            )
            for index in range(1, 7)
        ]

        blocked = responses[-1]
        assert blocked.status_code == 429
        assert blocked.json()["blocked_permanently"] is True
        assert "sessionid" not in _auth_cookie_names(blocked)
        assert "hmac_token" not in _auth_cookie_names(blocked)

        with psycopg.connect(
            host="session-db",
            port=5432,
            dbname="session_test",
            user="myuser",
            password="mypassword",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT is_blocked FROM userauth_user WHERE email = %s", (user["email"],))
                row = cursor.fetchone()

        assert row == (True,)

    def test_second_login_from_different_fingerprint_is_rejected_while_session_is_fresh(
        self,
        session_url: str,
    ) -> None:
        user = _create_active_user(session_url)
        first_login = _login(
            session_url,
            user,
            client_ip="10.226.1.10",
            user_agent=BROWSER_USER_AGENT,
        )
        assert first_login.status_code == 200

        second_login = _login(
            session_url,
            user,
            client_ip="10.226.2.10",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        )

        assert second_login.status_code == 409
        assert "sessionid" not in _auth_cookie_names(second_login)
        assert "hmac_token" not in _auth_cookie_names(second_login)

    def test_repeated_concurrent_login_attempts_escalate_to_user_block(self, session_url: str) -> None:
        user = _create_active_user(session_url)
        first_login = _login(
            session_url,
            user,
            client_ip="10.229.1.10",
            user_agent=BROWSER_USER_AGENT,
        )
        assert first_login.status_code == 200

        responses = [
            _login(
                session_url,
                user,
                client_ip=f"10.229.{index}.10",
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            )
            for index in range(2, 8)
        ]

        assert [response.status_code for response in responses] == [409, 409, 409, 429, 429, 429]
        assert responses[-1].json()["blocked_permanently"] is True
        assert "sessionid" not in _auth_cookie_names(responses[-1])
        assert "hmac_token" not in _auth_cookie_names(responses[-1])

        with psycopg.connect(
            host="session-db",
            port=5432,
            dbname="session_test",
            user="myuser",
            password="mypassword",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT is_blocked FROM userauth_user WHERE email = %s", (user["email"],))
                row = cursor.fetchone()

        assert row == (True,)

    def test_parallel_first_logins_from_different_fingerprints_create_only_one_session(
        self,
        session_url: str,
    ) -> None:
        user = _create_active_user(session_url)
        barrier = threading.Barrier(3)
        fingerprints = [
            ("10.232.1.10", BROWSER_USER_AGENT),
            ("10.232.2.10", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"),
        ]

        def login_after_barrier(client_ip: str, user_agent: str) -> httpx.Response:
            barrier.wait(timeout=10.0)
            return _login(
                session_url,
                user,
                client_ip=client_ip,
                user_agent=user_agent,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(login_after_barrier, client_ip, user_agent)
                for client_ip, user_agent in fingerprints
            ]
            barrier.wait(timeout=10.0)
            responses = [future.result(timeout=10.0) for future in futures]

        statuses = sorted(response.status_code for response in responses)
        assert statuses == [200, 409]
        assert sum(1 for response in responses if response.cookies.get("sessionid")) == 1
        assert sum(1 for response in responses if response.cookies.get("hmac_token")) == 1

    def test_repeated_concurrent_login_attempts_from_same_ip_trigger_ip_throttle(
        self,
        session_url: str,
    ) -> None:
        user = _create_active_user(session_url)
        suffix = uuid4().hex[:8]
        second_device_ip = f"10.231.{int(suffix[:2], 16)}.10"
        second_device_referer = f"http://next.localhost:8081/login?case={suffix}"
        second_device_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"

        first_login = _login(
            session_url,
            user,
            client_ip="10.229.9.10",
            user_agent=BROWSER_USER_AGENT,
        )
        assert first_login.status_code == 200

        responses = [
            _login(
                session_url,
                user,
                client_ip=second_device_ip,
                referer=second_device_referer,
                user_agent=second_device_ua,
            )
            for _ in range(5)
        ]

        assert [response.status_code for response in responses[:3]] == [409, 409, 409]
        assert responses[3].status_code == 429
        assert responses[4].status_code == 429
        assert "sessionid" not in _auth_cookie_names(responses[4])
        assert "hmac_token" not in _auth_cookie_names(responses[4])

        with psycopg.connect(
            host="session-db",
            port=5432,
            dbname="session_test",
            user="myuser",
            password="mypassword",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT is_temporary, user_agent, referer, endpoint
                      FROM userauth_blockedip
                     WHERE referer = %s
                       AND endpoint = %s
                     ORDER BY blocked_at DESC
                     LIMIT 1
                    """,
                    (second_device_referer, "/login/"),
                )
                row = cursor.fetchone()

        assert row == (
            True,
            second_device_ua,
            second_device_referer,
            "/login/",
        )

    def test_distributed_invalid_passwords_across_ips_escalate_user_block_without_ip_block(
        self,
        session_url: str,
    ) -> None:
        user = _create_active_user(session_url)
        suffix = uuid4().hex[:8]
        referer = f"http://next.localhost:8081/login?distributed={suffix}"
        responses = [
            _login(
                session_url,
                user,
                password="WrongPass123!",
                client_ip=f"10.233.{index}.10",
                referer=referer,
            )
            for index in range(1, 7)
        ]

        assert [response.status_code for response in responses] == [401, 401, 401, 429, 429, 429]
        assert responses[-1].json()["blocked_permanently"] is True

        with psycopg.connect(
            host="session-db",
            port=5432,
            dbname="session_test",
            user="myuser",
            password="mypassword",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT is_blocked FROM userauth_user WHERE email = %s", (user["email"],))
                user_row = cursor.fetchone()
                cursor.execute("SELECT COUNT(*) FROM userauth_blockedip WHERE referer = %s", (referer,))
                blocked_ip_row = cursor.fetchone()

        assert user_row == (True,)
        assert blocked_ip_row == (0,)

    def test_single_ip_credential_stuffing_against_many_users_triggers_ip_throttle(
        self,
        session_url: str,
    ) -> None:
        users = [_create_active_user(session_url) for _ in range(5)]
        suffix = uuid4().hex[:8]
        client_ip = f"10.234.{int(suffix[:2], 16)}.10"
        referer = f"http://next.localhost:8081/login?stuffing={suffix}"
        responses = [
            _login(
                session_url,
                user,
                password="WrongPass123!",
                client_ip=client_ip,
                referer=referer,
            )
            for user in users
        ]

        assert [response.status_code for response in responses[:4]] == [401, 401, 401, 401]
        assert responses[4].status_code == 429
        assert "sessionid" not in _auth_cookie_names(responses[4])
        assert "hmac_token" not in _auth_cookie_names(responses[4])

        with psycopg.connect(
            host="session-db",
            port=5432,
            dbname="session_test",
            user="myuser",
            password="mypassword",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT is_temporary, referer, endpoint
                      FROM userauth_blockedip
                     WHERE referer = %s
                     ORDER BY blocked_at DESC
                     LIMIT 1
                    """,
                    (referer,),
                )
                row = cursor.fetchone()

        assert row == (True, referer, "/login/")
