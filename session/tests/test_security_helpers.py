from __future__ import annotations

import base64
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import allure
import pyotp
import pytest
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.exceptions import Throttled

from userauth.crypto import (
    decrypt_bytes,
    derive_keys_from_dek,
    encrypt_bytes,
    hmac_bytes,
    hmac_verify,
    unwrap_dek,
    wrap_dek,
)
from userauth.hmac_token import HmacToken
from userauth.throttles import CryptoBatchThrottle, RegisterIPThrottle
from userauth.views import CryptoBatchView
from userauth.two_factor import (
    TWO_FACTOR_ATTEMPTS_SESSION_KEY,
    TWO_FACTOR_PENDING_LOGIN_TTL_SECONDS,
    TWO_FACTOR_PENDING_SESSION_KEY,
    TWO_FACTOR_USED_TOKEN_TTL_SECONDS,
    TWO_FACTOR_VERIFIED_SESSION_KEY,
    TwoFactor,
    TwoFactorSessionState,
)
from utils.utils import get_client_ip, is_ip_allowed, parse_allowed

pytestmark = pytest.mark.unit


class MutableSession(dict):
    def __init__(self, session_key: str | None = "session-key", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.session_key = session_key


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Session cryptography helpers preserve confidentiality and integrity")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security", "crypto")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class CryptoHelperTests(SimpleTestCase):
    def test_wrap_and_unwrap_dek_round_trip(self) -> None:
        dek = os.urandom(32)

        nonce, ciphertext = wrap_dek(dek)

        self.assertEqual(len(nonce), 12)
        self.assertNotEqual(ciphertext, dek)
        self.assertEqual(unwrap_dek(nonce, ciphertext), dek)

    def test_derived_keys_are_domain_separated_and_usable_for_encryption(self) -> None:
        dek = b"d" * 32

        enc_key, mac_key = derive_keys_from_dek(dek)
        nonce, ciphertext = encrypt_bytes(enc_key, b"secret payload")
        mac = hmac_bytes(mac_key, nonce + ciphertext)

        self.assertEqual(len(enc_key), 32)
        self.assertEqual(len(mac_key), 32)
        self.assertNotEqual(enc_key, mac_key)
        self.assertEqual(decrypt_bytes(enc_key, nonce, ciphertext), b"secret payload")
        self.assertTrue(hmac_verify(mac_key, nonce + ciphertext, mac))
        self.assertFalse(hmac_verify(mac_key, nonce + b"tampered", mac))


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Session HMAC tokens bind requests to session, client metadata, and freshness")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security", "hmac")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@override_settings(SERVER_SALT="unit-test-salt", VALID_HMAC=60)
class HmacTokenTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _request(self):
        request = self.factory.get(
            "/api/verifySession/",
            REMOTE_ADDR="10.10.0.2",
            HTTP_USER_AGENT="pytest",
            HTTP_SEC_CH_UA_PLATFORM="Linux",
        )
        request.COOKIES["sessionid"] = "session-123"
        return request

    def test_valid_hmac_accepts_fresh_matching_request(self) -> None:
        request = self._request()
        timestamp = 1_000
        token = HmacToken.calculate_token("session-123", request, timestamp)

        with patch("userauth.hmac_token.time.time", return_value=1_010):
            self.assertTrue(HmacToken.is_valid_hmac(token, request, str(timestamp)))

    def test_hmac_rejects_invalid_timestamp_expired_token_and_tampering(self) -> None:
        request = self._request()
        timestamp = 1_000
        token = HmacToken.calculate_token("session-123", request, timestamp)

        self.assertFalse(HmacToken.is_valid_hmac(token, request, "not-a-time"))
        with patch("userauth.hmac_token.time.time", return_value=1_061):
            self.assertFalse(HmacToken.is_valid_hmac(token, request, str(timestamp)))
        with patch("userauth.hmac_token.time.time", return_value=1_010):
            self.assertFalse(HmacToken.is_valid_hmac(base64.b64encode(b"bad").decode(), request, str(timestamp)))


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Two-factor helper generates deterministic secrets and verifiable tokens")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security", "2fa")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@override_settings(SERVER_SALT="unit-test-salt")
class TwoFactorTests(SimpleTestCase):
    def _request(self, session_key: str | None = "session-key"):
        request = RequestFactory().post("/two-factor/verify/")
        request.session = MutableSession(session_key)
        return request

    def _user(self):
        return SimpleNamespace(pk=42)

    def test_secret_generation_is_stable_for_same_identity(self) -> None:
        first = TwoFactor.generate_secret_key("User@Example.com", "artur")
        second = TwoFactor.generate_secret_key("user@example.com", "artur")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 32)

    @patch("userauth.two_factor.cache")
    def test_mark_pending_records_current_pending_session_with_short_ttl(self, cache: MagicMock) -> None:
        request = self._request("pending-session")
        user = self._user()

        TwoFactorSessionState.mark_pending(request, user)

        self.assertEqual(request.session[TWO_FACTOR_PENDING_SESSION_KEY], 42)
        self.assertEqual(request.session[TWO_FACTOR_ATTEMPTS_SESSION_KEY], 0)
        self.assertNotIn(TWO_FACTOR_VERIFIED_SESSION_KEY, request.session)
        cache.set.assert_called_once_with(
            "two_factor_pending_login:42",
            "pending-session",
            timeout=TWO_FACTOR_PENDING_LOGIN_TTL_SECONDS,
        )

    @patch("userauth.two_factor.cache")
    def test_current_pending_login_requires_matching_cached_session_key(self, cache: MagicMock) -> None:
        request = self._request("current-session")
        user = self._user()

        cache.get.return_value = "current-session"
        self.assertTrue(TwoFactorSessionState.is_current_pending_login(request, user))

        cache.get.return_value = "different-session"
        self.assertFalse(TwoFactorSessionState.is_current_pending_login(request, user))

    @patch("userauth.two_factor.cache")
    def test_clear_removes_pending_cache_only_for_current_session(self, cache: MagicMock) -> None:
        request = self._request("current-session")
        request.session[TWO_FACTOR_PENDING_SESSION_KEY] = 42
        user = self._user()

        cache.get.return_value = "current-session"
        TwoFactorSessionState.clear(request, user)

        cache.delete.assert_called_once_with("two_factor_pending_login:42")
        self.assertNotIn(TWO_FACTOR_PENDING_SESSION_KEY, request.session)

    @patch("userauth.two_factor.cache")
    def test_clear_does_not_remove_newer_pending_cache_marker(self, cache: MagicMock) -> None:
        request = self._request("old-session")
        user = self._user()

        cache.get.return_value = "new-session"
        TwoFactorSessionState.clear(request, user)

        cache.delete.assert_not_called()

    @patch("userauth.two_factor.cache.add", return_value=True)
    def test_verify_token_accepts_current_totp_and_rejects_invalid_token(self, cache_add: MagicMock) -> None:
        secret = TwoFactor.generate_secret_key("user@example.com", "artur")
        valid_token = pyotp.TOTP(secret).now()

        self.assertTrue(TwoFactor.verify_token("user@example.com", "artur", valid_token))
        self.assertFalse(TwoFactor.verify_token("user@example.com", "artur", "000000"))
        cache_add.assert_called_once()

    @patch("userauth.two_factor.cache.add", side_effect=[True, False])
    def test_verify_token_rejects_replayed_valid_totp(self, cache_add: MagicMock) -> None:
        secret = TwoFactor.generate_secret_key("user@example.com", "artur")
        valid_token = pyotp.TOTP(secret).now()

        self.assertTrue(TwoFactor.verify_token("user@example.com", "artur", valid_token))
        self.assertFalse(TwoFactor.verify_token("user@example.com", "artur", valid_token))

        self.assertEqual(cache_add.call_count, 2)
        cache_key = cache_add.call_args.args[0]
        self.assertTrue(cache_key.startswith("two_factor_used_totp:"))
        self.assertNotIn(valid_token, cache_key)
        self.assertEqual(cache_add.call_args.kwargs["timeout"], TWO_FACTOR_USED_TOKEN_TTL_SECONDS)

    def test_provisioning_uri_and_qr_code_are_machine_readable(self) -> None:
        secret = TwoFactor.generate_secret_key("user@example.com", "artur")
        uri = TwoFactor.generate_provisioning_uri(secret, "artur")
        qr_svg = base64.b64decode(TwoFactor.generate_qr_code(uri))

        self.assertIn("otpauth://totp/", uri)
        self.assertIn(b"<svg", qr_svg)


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Session IP helpers normalize allow-lists and resolve client addresses")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security", "middleware")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class IpHelperTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_get_client_ip_uses_original_then_forwarded_then_remote_address(self) -> None:
        self.assertEqual(
            get_client_ip(self.factory.get("/", HTTP_X_ORIGINAL_CLIENT_IP=" 10.0.0.9 ")),
            "10.0.0.9",
        )
        self.assertEqual(
            get_client_ip(self.factory.get("/", HTTP_X_FORWARDED_FOR="10.0.0.8, 10.0.0.7")),
            "10.0.0.8",
        )
        self.assertEqual(get_client_ip(self.factory.get("/", REMOTE_ADDR="10.0.0.6")), "10.0.0.6")

    def test_parse_allowed_accepts_json_python_iterables_and_localhost_alias(self) -> None:
        self.assertEqual(parse_allowed('["localhost", "10.0.0.0/24"]'), ["127.0.0.1", "10.0.0.0/24"])
        self.assertEqual(parse_allowed((" 192.168.0.1 ", "")), ["192.168.0.1"])
        self.assertEqual(parse_allowed(""), [])

    def test_is_ip_allowed_supports_exact_ip_cidr_and_invalid_values(self) -> None:
        self.assertTrue(is_ip_allowed("10.0.0.8", ["10.0.0.0/24"]))
        self.assertTrue(is_ip_allowed("127.0.0.1", ["127.0.0.1"]))
        self.assertFalse(is_ip_allowed("10.0.1.8", ["10.0.0.0/24"]))
        self.assertFalse(is_ip_allowed("not-an-ip", ["127.0.0.1"]))


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Session throttles escalate abusive registration IPs")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security", "throttle")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class RegisterIPThrottleTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_cache_key_is_scoped_to_client_ip(self) -> None:
        request = self.factory.post("/register/", REMOTE_ADDR="10.0.0.10")
        throttle = RegisterIPThrottle()

        self.assertIn("10.0.0.10", throttle.get_cache_key(request, view=None))

    def test_throttle_failure_raises_explicit_throttled_error(self) -> None:
        with self.assertRaisesRegex(Throttled, "Too many attempts"):
            RegisterIPThrottle().throttle_failure()

    @patch("userauth.throttles.BlockedIP")
    @patch("rest_framework.throttling.AnonRateThrottle.throttle_request", return_value=False, create=True)
    def test_failed_request_creates_first_temporary_block(
        self,
        _base_throttle: MagicMock,
        blocked_ip: MagicMock,
    ) -> None:
        request = self.factory.post(
            "/register/",
            REMOTE_ADDR="10.0.0.11",
            HTTP_USER_AGENT="pytest",
            HTTP_REFERER="http://next.localhost/register",
        )
        blocked_ip.objects.filter.return_value.first.return_value = None

        self.assertFalse(RegisterIPThrottle().throttle_request(request, view=None))

        blocked_ip.objects.create.assert_called_once_with(
            ip_address="10.0.0.11",
            user_agent="pytest",
            referer="http://next.localhost/register",
            endpoint="/register/",
        )

    @patch("userauth.throttles.BlockedIP")
    @patch("rest_framework.throttling.AnonRateThrottle.throttle_request", return_value=False, create=True)
    def test_failed_request_escalates_existing_temporary_block(
        self,
        _base_throttle: MagicMock,
        blocked_ip: MagicMock,
    ) -> None:
        request = self.factory.post("/register/", REMOTE_ADDR="10.0.0.12")
        existing = MagicMock(is_temporary=True)
        blocked_ip.objects.filter.return_value.first.return_value = existing

        with self.assertRaisesRegex(Throttled, "blocked"):
            RegisterIPThrottle().throttle_request(request, view=None)

        self.assertFalse(existing.is_temporary)
        existing.save.assert_called_once_with(update_fields=["is_temporary"])

    @patch("userauth.throttles.BlockedIP")
    @patch("rest_framework.throttling.AnonRateThrottle.throttle_request", return_value=False, create=True)
    def test_failed_request_rejects_existing_permanent_block(
        self,
        _base_throttle: MagicMock,
        blocked_ip: MagicMock,
    ) -> None:
        request = self.factory.post("/register/", REMOTE_ADDR="10.0.0.13")
        existing = MagicMock(is_temporary=False)
        blocked_ip.objects.filter.return_value.first.return_value = existing

        with self.assertRaisesRegex(Throttled, "permanently blocked"):
            RegisterIPThrottle().throttle_request(request, view=None)

        existing.save.assert_not_called()
        blocked_ip.objects.create.assert_not_called()

    @patch("userauth.throttles.BlockedIP")
    @patch("rest_framework.throttling.AnonRateThrottle.allow_request", return_value=True, create=True)
    def test_allow_request_returns_true_when_base_throttle_allows(
        self,
        _base_allow: MagicMock,
        blocked_ip: MagicMock,
    ) -> None:
        request = self.factory.post("/register/", REMOTE_ADDR="10.0.0.14")

        self.assertTrue(RegisterIPThrottle().allow_request(request, view=None))

        blocked_ip.objects.filter.assert_not_called()
        blocked_ip.objects.create.assert_not_called()

    @patch("userauth.throttles.BlockedIP")
    @patch("rest_framework.throttling.AnonRateThrottle.allow_request", return_value=False, create=True)
    def test_allow_request_records_block_when_base_throttle_denies(
        self,
        _base_allow: MagicMock,
        blocked_ip: MagicMock,
    ) -> None:
        request = self.factory.post(
            "/register/",
            REMOTE_ADDR="10.0.0.15",
            HTTP_USER_AGENT="pytest",
            HTTP_REFERER="http://next.localhost/register",
        )
        blocked_ip.objects.filter.return_value.first.return_value = None

        self.assertFalse(RegisterIPThrottle().allow_request(request, view=None))

        blocked_ip.objects.create.assert_called_once_with(
            ip_address="10.0.0.15",
            user_agent="pytest",
            referer="http://next.localhost/register",
            endpoint="/register/",
        )

    @patch("userauth.throttles.BlockedIP")
    @patch("rest_framework.throttling.AnonRateThrottle.allow_request", side_effect=Throttled(detail="limit"), create=True)
    def test_allow_request_records_block_and_reraises_throttled(
        self,
        _base_allow: MagicMock,
        blocked_ip: MagicMock,
    ) -> None:
        request = self.factory.post("/register/", REMOTE_ADDR="10.0.0.16")
        blocked_ip.objects.filter.return_value.first.return_value = None

        with self.assertRaises(Throttled):
            RegisterIPThrottle().allow_request(request, view=None)

        blocked_ip.objects.create.assert_called_once()


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Crypto batch endpoint uses a dedicated service throttle without blocking normal wallet bursts")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security", "crypto", "throttle")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Protects the service-to-service crypto endpoint with a loose IP throttle. "
    "The test verifies the normal burst needed for brokerage account setup and "
    "ensures the endpoint is not left completely unthrottled."
)
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "crypto-batch-throttle-tests",
        }
    }
)
class CryptoBatchThrottleTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        cache.clear()

    def tearDown(self) -> None:
        cache.clear()

    def _throttle(self, rate: str = "3/minute") -> CryptoBatchThrottle:
        throttle = CryptoBatchThrottle()
        throttle.rate = rate
        throttle.num_requests, throttle.duration = throttle.parse_rate(rate)
        return throttle

    def test_crypto_batch_view_uses_dedicated_throttle(self) -> None:
        self.assertEqual(CryptoBatchView.throttle_classes, [CryptoBatchThrottle])

    def test_cache_key_is_scoped_to_wallet_service_ip(self) -> None:
        request = self.factory.post(
            "/crypto/batch",
            REMOTE_ADDR="10.20.0.10",
            HTTP_X_ORIGINAL_CLIENT_IP="10.20.0.11",
        )

        cache_key = self._throttle().get_cache_key(request, view=None)

        self.assertIn("crypto_batch", cache_key)
        self.assertIn("10.20.0.11", cache_key)

    def test_allows_brokerage_setup_burst_and_limits_next_request(self) -> None:
        view = CryptoBatchView()

        allowed = []
        for _ in range(3):
            request = self.factory.post("/crypto/batch", REMOTE_ADDR="10.20.0.12")
            allowed.append(self._throttle().allow_request(request, view))

        denied = self._throttle().allow_request(
            self.factory.post("/crypto/batch", REMOTE_ADDR="10.20.0.12"),
            view,
        )

        self.assertEqual(allowed, [True, True, True])
        self.assertFalse(denied)

    @patch("userauth.throttles.BlockedIP")
    @patch("rest_framework.throttling.AnonRateThrottle.throttle_request", side_effect=Throttled(detail="limit"), create=True)
    def test_throttle_request_records_block_and_reraises_base_throttled(
        self,
        _base_throttle: MagicMock,
        blocked_ip: MagicMock,
    ) -> None:
        request = self.factory.post("/register/", REMOTE_ADDR="10.0.0.17")
        blocked_ip.objects.filter.return_value.first.return_value = None

        with self.assertRaises(Throttled):
            RegisterIPThrottle().throttle_request(request, view=None)

        blocked_ip.objects.create.assert_called_once()
