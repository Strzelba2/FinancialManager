from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import allure
import pytest
from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework import serializers
from rest_framework.response import Response

from userauth.serializers import LoginSerializer
from userauth.backends import UsernameOrEmailBackend
from userauth.throttles import TwoFactorVerifyThrottle
from userauth.two_factor import (
    TWO_FACTOR_ATTEMPTS_SESSION_KEY,
    TWO_FACTOR_PENDING_SESSION_KEY,
    TWO_FACTOR_VERIFIED_SESSION_KEY,
)
from userauth.views import (
    LoginView,
    LogoutView,
    TwoFactorEnableView,
    TwoFactorDisableView,
    TwoFactorSetupView,
    TwoFactorVerifyView,
    VerifySessionView,
    _clear_active_login,
    _store_active_login,
)
from utils.utils import get_client_ip

pytestmark = pytest.mark.unit


class MutableSession(dict):
    session_key = "fresh-session-key"


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Session login helpers avoid trusting spoofable client identity data")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "middleware")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class LoginClientIdentityTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override_settings(TRUSTED_CLIENT_IP_HEADER_PROXIES=["10.0.0.5"])
    def test_original_client_ip_header_is_ignored_from_untrusted_remote_addr(self) -> None:
        request = self.factory.post(
            "/login/",
            REMOTE_ADDR="198.51.100.44",
            HTTP_X_ORIGINAL_CLIENT_IP="203.0.113.99",
            HTTP_X_FORWARDED_FOR="203.0.113.88",
            HTTP_X_REAL_IP="203.0.113.77",
        )

        self.assertEqual(get_client_ip(request), "198.51.100.44")

    @override_settings(TRUSTED_CLIENT_IP_HEADER_PROXIES=["10.0.0.5"])
    def test_original_client_ip_header_is_allowed_from_trusted_proxy(self) -> None:
        request = self.factory.post(
            "/login/",
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_ORIGINAL_CLIENT_IP="203.0.113.99",
        )

        self.assertEqual(get_client_ip(request), "203.0.113.99")


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Authentication backend never writes password values to logs")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "logging")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class AuthenticationLoggingTests(SimpleTestCase):
    @patch("userauth.backends.logger")
    @patch("userauth.backends.get_user_model")
    def test_email_and_password_values_are_not_logged_when_authentication_fails(
        self,
        get_user_model: MagicMock,
        logger: MagicMock,
    ) -> None:
        email = "unknown@example.com"
        password = "UltraSecretPassword123!"
        user_model = MagicMock()
        user_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        user_model.objects.get.side_effect = user_model.DoesNotExist()
        get_user_model.return_value = user_model

        self.assertIsNone(
            UsernameOrEmailBackend().authenticate(
                request=None,
                username=email,
                password=password,
            )
        )

        logged = repr(logger.info.call_args_list + logger.warning.call_args_list + logger.error.call_args_list)
        self.assertNotIn(email, logged)
        self.assertNotIn(password, logged)

    @patch("userauth.backends.logger")
    @patch("userauth.backends.get_user_model")
    def test_known_user_wrong_password_does_not_log_email_or_password(
        self,
        get_user_model: MagicMock,
        logger: MagicMock,
    ) -> None:
        email = "known@example.com"
        password = "WrongSecretPassword123!"
        user = MagicMock()
        user.check_password.return_value = False
        user_model = MagicMock()
        user_model.objects.get.return_value = user
        get_user_model.return_value = user_model

        self.assertIsNone(
            UsernameOrEmailBackend().authenticate(
                request=None,
                username=email,
                password=password,
            )
        )

        logged = repr(logger.info.call_args_list + logger.warning.call_args_list + logger.error.call_args_list)
        self.assertNotIn(email, logged)
        self.assertNotIn(password, logged)


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Login validation does not disclose credentials through errors or logs")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "logging")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class LoginSerializerSecurityTests(SimpleTestCase):
    @patch("userauth.serializers.logger")
    @patch("userauth.serializers.authenticate", return_value=None)
    def test_failed_login_validation_does_not_echo_email_or_password(
        self,
        _authenticate: MagicMock,
        logger: MagicMock,
    ) -> None:
        email = "sensitive.email@example.com"
        password = "UltraSecretPassword123!"
        serializer = LoginSerializer(data={"email": email, "password": password})

        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        error_payload = repr(serializer.errors)
        logged = repr(logger.info.call_args_list + logger.warning.call_args_list + logger.error.call_args_list)
        self.assertNotIn(email, error_payload)
        self.assertNotIn(password, error_payload)
        self.assertNotIn(email, logged)
        self.assertNotIn(password, logged)


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Authentication spends comparable password-hash work for unknown emails")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "timing")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class AuthenticationTimingEnumerationTests(SimpleTestCase):
    @patch("userauth.backends.hashers.check_password")
    @patch("userauth.backends.get_user_model")
    def test_unknown_email_path_runs_dummy_password_hash_check(
        self,
        get_user_model: MagicMock,
        check_password: MagicMock,
    ) -> None:
        user_model = MagicMock()
        user_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        user_model.objects.get.side_effect = user_model.DoesNotExist()
        get_user_model.return_value = user_model

        self.assertIsNone(
            UsernameOrEmailBackend().authenticate(
                request=None,
                username="missing@example.com",
                password="SecretPass123!",
            )
        )

        check_password.assert_called_once()
        password, dummy_hash = check_password.call_args.args
        self.assertEqual(password, "SecretPass123!")
        self.assertIsInstance(dummy_hash, str)

    @patch("userauth.backends.hashers.check_password", return_value=False)
    @patch("userauth.backends._DUMMY_PASSWORD_HASH", "dummy-hash")
    @patch("userauth.backends.get_user_model")
    def test_known_and_unknown_email_paths_both_perform_password_verification_work(
        self,
        get_user_model: MagicMock,
        check_password: MagicMock,
    ) -> None:
        user_model = MagicMock()
        user_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        existing_user = MagicMock()
        existing_user.check_password.return_value = False
        user_model.objects.get.side_effect = [
            existing_user,
            user_model.DoesNotExist(),
        ]
        get_user_model.return_value = user_model
        backend = UsernameOrEmailBackend()

        self.assertIsNone(
            backend.authenticate(
                request=None,
                username="known@example.com",
                password="WrongPass123!",
            )
        )
        self.assertIsNone(
            backend.authenticate(
                request=None,
                username="missing@example.com",
                password="WrongPass123!",
            )
        )

        existing_user.check_password.assert_called_once_with("WrongPass123!")
        check_password.assert_called_once_with("WrongPass123!", "dummy-hash")


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Active login cache entries follow the HMAC freshness window")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "hmac")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class ActiveLoginTtlTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override_settings(
        VALID_HMAC=17,
        SERVER_SALT="unit-test-salt",
        TRUSTED_CLIENT_IP_HEADER_PROXIES=["10.0.0.0/8"],
    )
    @patch("userauth.views.cache")
    def test_active_login_entry_uses_valid_hmac_timeout(self, cache: MagicMock) -> None:
        request = self.factory.post(
            "/login/",
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_ORIGINAL_CLIENT_IP="203.0.113.44",
            HTTP_USER_AGENT="Unit Browser",
            HTTP_SEC_CH_UA_PLATFORM='"Linux"',
        )
        request.session = SimpleNamespace(session_key="fresh-session-key")
        user = SimpleNamespace(pk=42)

        _store_active_login(request, user)

        cache.set.assert_called_once()
        key, value = cache.set.call_args.args
        timeout = cache.set.call_args.kwargs["timeout"]
        self.assertEqual(key, "active_login:42")
        self.assertEqual(value["session_key"], "fresh-session-key")
        self.assertEqual(len(value["fingerprint_hash"]), 64)
        self.assertEqual(timeout, 17)

    @patch("userauth.views.cache")
    def test_active_login_is_not_stored_without_session_key(self, cache: MagicMock) -> None:
        request = self.factory.post("/login/")
        request.session = SimpleNamespace(session_key="")
        user = SimpleNamespace(pk=42)

        _store_active_login(request, user)

        cache.set.assert_not_called()

    @patch("userauth.views.cache")
    def test_active_login_clear_ignores_missing_identity(self, cache: MagicMock) -> None:
        _clear_active_login(None, "session-key")
        _clear_active_login(42, "")

        cache.get.assert_not_called()
        cache.delete.assert_not_called()

    @patch("userauth.views.cache")
    def test_active_login_clear_deletes_only_matching_session(self, cache: MagicMock) -> None:
        cache.get.return_value = {"session_key": "current-session"}

        _clear_active_login(42, "current-session")

        cache.get.assert_called_once_with("active_login:42")
        cache.delete.assert_called_once_with("active_login:42")

    @patch("userauth.views.cache")
    def test_active_login_clear_does_not_delete_mismatched_session(self, cache: MagicMock) -> None:
        cache.get.return_value = {"session_key": "other-session"}

        _clear_active_login(42, "current-session")

        cache.get.assert_called_once_with("active_login:42")
        cache.delete.assert_not_called()


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Login response helpers expose safe retry and block contracts")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class LoginViewResponseContractTests(SimpleTestCase):
    def test_retry_after_formatter_uses_compact_human_durations(self) -> None:
        view = LoginView()

        self.assertEqual(view._format_retry_after(0), "0s")
        self.assertEqual(view._format_retry_after(65), "1m 5s")
        self.assertEqual(view._format_retry_after(3661), "1h 1m 1s")

    @patch.object(LoginView, "_cache_ttl_seconds", return_value=65)
    def test_temporary_block_response_has_retry_metadata(self, _ttl: MagicMock) -> None:
        response = LoginView()._temporary_block_response(
            "blocked@example.com",
            "login_attempts_blocked@example.com",
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["retry_after_seconds"], 65)
        self.assertEqual(response.data["retry_after_human"], "1m 5s")
        self.assertFalse(response.data["blocked_permanently"])
        self.assertIn("blocked_until", response.data)

    def test_permanent_block_response_does_not_echo_credentials(self) -> None:
        response = LoginView()._permanent_block_response("blocked@example.com")

        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.data["blocked_permanently"])
        self.assertNotIn("blocked@example.com", repr(response.data))
        self.assertNotIn("password", repr(response.data).lower())

    @patch("userauth.views.cache")
    def test_failed_login_attempt_counter_uses_user_temporary_block_window(self, cache: MagicMock) -> None:
        LoginView()._record_failed_login_attempt("login_attempts_user@example.com", 2)

        cache.set.assert_called_once_with(
            "login_attempts_user@example.com",
            3,
            timeout=settings.USER_TEMPORARY_BLOCK_TIME,
        )

    @patch("userauth.views.cache")
    def test_concurrent_login_response_records_attempt_and_returns_409(self, cache: MagicMock) -> None:
        response = LoginView()._concurrent_login_response(
            "user@example.com",
            "login_attempts_user@example.com",
            0,
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data["blocked_permanently"])
        cache.set.assert_called_once_with(
            "login_attempts_user@example.com",
            1,
            timeout=settings.USER_TEMPORARY_BLOCK_TIME,
        )


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Login view enforces active-session and failure contracts without leaking sessions")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class LoginViewPostSecurityFlowTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _request(self, email: str = "user@example.com"):
        request = self.factory.post(
            "/login/",
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_ORIGINAL_CLIENT_IP="203.0.113.44",
            HTTP_USER_AGENT="Unit Browser",
            HTTP_SEC_CH_UA_PLATFORM='"Linux"',
        )
        request.data = {"email": email, "password": "SecretPass123!"}
        request.session = MagicMock()
        request.session.session_key = "fresh-session-key"
        return request

    def _user(self):
        return SimpleNamespace(
            pk=42,
            username="unit-user",
            first_name="Unit",
            email="user@example.com",
            is_blocked=False,
            is_two_factor=False,
            is_verified=True,
        )

    @patch("userauth.views.time.time", return_value=1_000)
    @patch("userauth.views.HmacToken.calculate_token", return_value="fresh-hmac")
    @patch("userauth.views.login")
    @patch("userauth.views.cache")
    @patch.object(LoginView, "serializer_class")
    def test_successful_login_stores_session_contract_and_active_login(
        self,
        serializer_class: MagicMock,
        cache: MagicMock,
        _login: MagicMock,
        _calculate_token: MagicMock,
        _time: MagicMock,
    ) -> None:
        user = self._user()
        request = self._request(user.email)
        request.user = user
        serializer = MagicMock()
        serializer.is_valid.return_value = True
        serializer.validated_data = {"user": user}
        serializer_class.return_value = serializer
        cache.get.side_effect = [0, 0, None]

        with patch("userauth.two_factor.cache"):
            response = LoginView().post(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"message": "Login successful"})
        self.assertEqual(response.cookies["hmac_token"].value, "1000:fresh-hmac")
        cache.delete.assert_any_call("login_attempts_user@example.com")
        cache.delete.assert_any_call("too_many_login_attempts_user@example.com")
        cache.set.assert_any_call(
            "session:fresh-session-key",
            {"username": "unit-user", "first_name": "Unit", "email": "user@example.com"},
            timeout=3600,
        )
        self.assertTrue(any(call.args[0] == "active_login:42" for call in cache.set.call_args_list))

    @patch("userauth.views._request_fingerprint_hash", return_value="current-fingerprint")
    @patch("userauth.views.login")
    @patch("userauth.views.cache")
    @patch.object(LoginView, "serializer_class")
    def test_different_fresh_active_login_fingerprint_returns_409_before_django_login(
        self,
        serializer_class: MagicMock,
        cache: MagicMock,
        django_login: MagicMock,
        _fingerprint: MagicMock,
    ) -> None:
        user = self._user()
        request = self._request(user.email)
        serializer = MagicMock()
        serializer.is_valid.return_value = True
        serializer.validated_data = {"user": user}
        serializer_class.return_value = serializer
        cache.get.side_effect = [0, 0, {"fingerprint_hash": "other-fingerprint"}]

        with patch("userauth.two_factor.cache"):
            response = LoginView().post(request)

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data["blocked_permanently"])
        django_login.assert_not_called()
        cache.set.assert_called_once_with(
            "login_attempts_user@example.com",
            1,
            timeout=settings.USER_TEMPORARY_BLOCK_TIME,
        )

    @patch("userauth.views.cache")
    @patch.object(LoginView, "serializer_class")
    def test_invalid_login_payload_records_failed_attempt_and_returns_401(
        self,
        serializer_class: MagicMock,
        cache: MagicMock,
    ) -> None:
        request = self._request()
        serializer = MagicMock()
        serializer.is_valid.return_value = False
        serializer.errors = {"email": ["Invalid login."]}
        serializer_class.return_value = serializer
        cache.get.side_effect = [0, 0]

        with patch("userauth.two_factor.cache"):
            response = LoginView().post(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, {"error": {"email": ["Invalid login."]}})
        cache.set.assert_called_once_with(
            "login_attempts_user@example.com",
            1,
            timeout=settings.USER_TEMPORARY_BLOCK_TIME,
        )

    @patch("userauth.views.HmacToken.calculate_token")
    @patch("userauth.views.login")
    @patch("userauth.views.cache")
    @patch.object(LoginView, "serializer_class")
    def test_two_factor_login_returns_json_challenge_without_hmac_cookie(
        self,
        serializer_class: MagicMock,
        cache: MagicMock,
        _login: MagicMock,
        calculate_token: MagicMock,
    ) -> None:
        user = self._user()
        user.is_two_factor = True
        user.is_verified = True
        request = self._request(user.email)
        request.session = MutableSession()
        serializer = MagicMock()
        serializer.is_valid.return_value = True
        serializer.validated_data = {"user": user}
        serializer_class.return_value = serializer
        cache.get.side_effect = [0, 0, None]

        with patch("userauth.two_factor.cache"):
            response = LoginView().post(request)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, {"requires_two_factor": True})
        self.assertNotIn("hmac_token", response.cookies)
        self.assertEqual(request.session[TWO_FACTOR_PENDING_SESSION_KEY], 42)
        self.assertNotIn(TWO_FACTOR_VERIFIED_SESSION_KEY, request.session)
        calculate_token.assert_not_called()


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Two-factor JSON API gates login completion and profile activation")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "2fa", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TwoFactorJsonApiTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_verify_view_uses_dedicated_two_factor_throttle(self) -> None:
        self.assertEqual(TwoFactorVerifyView.throttle_classes, [TwoFactorVerifyThrottle])

    def _user(self, is_two_factor: bool = True):
        user = SimpleNamespace(
            pk=42,
            username="unit-user",
            first_name="Unit",
            email="user@example.com",
            is_two_factor=is_two_factor,
            is_verified=False,
            is_authenticated=True,
            save=MagicMock(),
        )
        return user

    def _request(self, path: str, token: str = "123456"):
        request = self.factory.post(
            path,
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_ORIGINAL_CLIENT_IP="203.0.113.44",
            HTTP_USER_AGENT="Unit Browser",
            HTTP_SEC_CH_UA_PLATFORM='"Linux"',
        )
        request.data = {"token": token}
        request.session = MutableSession({TWO_FACTOR_PENDING_SESSION_KEY: 42})
        return request

    @patch("userauth.views.HmacToken.calculate_token")
    @patch("userauth.views.TwoFactor.verify_token")
    def test_verify_rejects_non_two_factor_user_without_auth_cookie(
        self,
        verify_token: MagicMock,
        calculate_token: MagicMock,
    ) -> None:
        request = self._request("/two-factor/verify/")
        request.user = self._user(is_two_factor=False)

        with patch("userauth.views.TwoFactorSessionState.clear_current_pending_login"):
            response = TwoFactorVerifyView().post(request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data,
            {"error": "Two-factor authentication is not enabled for this user."},
        )
        self.assertNotIn("hmac_token", response.cookies)
        self.assertNotIn(TWO_FACTOR_PENDING_SESSION_KEY, request.session)
        verify_token.assert_not_called()
        calculate_token.assert_not_called()

    @patch("userauth.views.time.time", return_value=1_000)
    @patch("userauth.views.HmacToken.calculate_token", return_value="fresh-hmac")
    @patch("userauth.views.TwoFactor.verify_token", return_value=True)
    @patch("userauth.views.cache")
    def test_verify_accepts_valid_totp_and_issues_hmac_cookie(
        self,
        cache: MagicMock,
        verify_token: MagicMock,
        _calculate_token: MagicMock,
        _time: MagicMock,
    ) -> None:
        request = self._request("/two-factor/verify/")
        request.user = self._user()

        with (
            patch("userauth.views.TwoFactorSessionState.is_current_pending_login", return_value=True),
            patch("userauth.views.TwoFactorSessionState.clear_current_pending_login"),
        ):
            response = TwoFactorVerifyView().post(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"message": "Two-factor verification successful"})
        self.assertEqual(response.cookies["hmac_token"].value, "1000:fresh-hmac")
        self.assertEqual(request.session[TWO_FACTOR_VERIFIED_SESSION_KEY], 42)
        self.assertNotIn(TWO_FACTOR_PENDING_SESSION_KEY, request.session)
        verify_token.assert_called_once_with("user@example.com", "unit-user", "123456")
        self.assertTrue(any(call.args[0] == "active_login:42" for call in cache.set.call_args_list))

    @patch("userauth.views.TwoFactor.verify_token")
    def test_verify_rejects_already_verified_session_without_auth_cookie(self, verify_token: MagicMock) -> None:
        request = self._request("/two-factor/verify/")
        request.user = self._user()
        request.session = MutableSession({TWO_FACTOR_VERIFIED_SESSION_KEY: 42})

        response = TwoFactorVerifyView().post(request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data,
            {"error": "Two-factor verification is already complete for this session."},
        )
        self.assertNotIn("hmac_token", response.cookies)
        verify_token.assert_not_called()

    @patch("userauth.views.TwoFactor.verify_token")
    def test_verify_rejects_session_without_pending_challenge(self, verify_token: MagicMock) -> None:
        request = self._request("/two-factor/verify/")
        request.user = self._user()
        request.session = MutableSession()

        response = TwoFactorVerifyView().post(request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data,
            {"error": "Two-factor verification is not pending for this session."},
        )
        self.assertNotIn("hmac_token", response.cookies)
        verify_token.assert_not_called()

    @patch("userauth.views.logout")
    @patch("userauth.views.TwoFactor.verify_token")
    def test_verify_rejects_stale_pending_session_without_auth_cookie(
        self,
        verify_token: MagicMock,
        django_logout: MagicMock,
    ) -> None:
        request = self._request("/two-factor/verify/")
        request.user = self._user()

        with (
            patch("userauth.views.TwoFactorSessionState.is_current_pending_login", return_value=False),
            patch("userauth.views.TwoFactorSessionState.clear_current_pending_login"),
        ):
            response = TwoFactorVerifyView().post(request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data,
            {"error": "Two-factor verification expired. Please log in again."},
        )
        self.assertNotIn("hmac_token", response.cookies)
        self.assertNotIn(TWO_FACTOR_PENDING_SESSION_KEY, request.session)
        verify_token.assert_not_called()
        django_logout.assert_called_once_with(request)

    @patch("userauth.views.TwoFactor.verify_token", return_value=False)
    def test_verify_rejects_invalid_totp_without_auth_cookie(self, verify_token: MagicMock) -> None:
        request = self._request("/two-factor/verify/")
        request.user = self._user()

        with (
            patch("userauth.views.TwoFactorSessionState.is_current_pending_login", return_value=True),
            patch("userauth.views.TwoFactorSessionState.clear_current_pending_login"),
        ):
            response = TwoFactorVerifyView().post(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, {"error": "Invalid 2FA code."})
        self.assertNotIn("hmac_token", response.cookies)
        self.assertEqual(request.session[TWO_FACTOR_ATTEMPTS_SESSION_KEY], 1)
        verify_token.assert_called_once()

    @patch("userauth.views.logout")
    @patch("userauth.views.TwoFactor.verify_token", return_value=False)
    def test_verify_logs_out_after_too_many_invalid_totp_attempts(
        self,
        _verify_token: MagicMock,
        django_logout: MagicMock,
    ) -> None:
        request = self._request("/two-factor/verify/")
        request.user = self._user()
        request.session[TWO_FACTOR_ATTEMPTS_SESSION_KEY] = 2

        with (
            patch("userauth.views.TwoFactorSessionState.is_current_pending_login", return_value=True),
            patch("userauth.views.TwoFactorSessionState.clear_current_pending_login"),
        ):
            response = TwoFactorVerifyView().post(request)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data, {"error": "Too many failed 2FA attempts. Please log in again."})
        self.assertNotIn("hmac_token", response.cookies)
        django_logout.assert_called_once_with(request)

    @patch("userauth.views.TwoFactor.generate_secret_key", return_value="secret")
    @patch("userauth.views.TwoFactor.generate_provisioning_uri", return_value="otpauth://totp/unit")
    @patch("userauth.views.TwoFactor.generate_qr_code", return_value="svg-base64")
    def test_setup_generates_qr_without_enabling_two_factor(
        self,
        _qr_code: MagicMock,
        _uri: MagicMock,
        _secret: MagicMock,
    ) -> None:
        request = self._request("/two-factor/setup/")
        user = self._user(is_two_factor=False)
        request.user = user

        response = TwoFactorSetupView().post(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"image": "svg-base64", "is_two_factor_enabled": False})
        self.assertFalse(user.is_two_factor)
        user.save.assert_not_called()

    @patch("userauth.views.TwoFactor.generate_secret_key")
    def test_setup_rejects_pending_two_factor_session(
        self,
        generate_secret_key: MagicMock,
    ) -> None:
        request = self._request("/two-factor/setup/")
        request.user = self._user(is_two_factor=True)

        response = TwoFactorSetupView().post(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data, {"error": "Two-factor authentication is required."})
        self.assertNotIn("hmac_token", response.cookies)
        generate_secret_key.assert_not_called()

    @patch("userauth.views.TwoFactor.verify_token", return_value=True)
    def test_enable_requires_valid_totp_before_persisting_two_factor(self, verify_token: MagicMock) -> None:
        request = self._request("/two-factor/enable/")
        user = self._user(is_two_factor=False)
        request.user = user
        request.session = MutableSession()

        response = TwoFactorEnableView().post(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"is_two_factor_enabled": True})
        self.assertTrue(user.is_two_factor)
        user.save.assert_called_once_with(update_fields=["is_two_factor"])
        self.assertEqual(request.session[TWO_FACTOR_VERIFIED_SESSION_KEY], 42)
        verify_token.assert_called_once_with("user@example.com", "unit-user", "123456")

    @patch("userauth.views.TwoFactor.verify_token", return_value=False)
    def test_disable_rejects_invalid_token_when_two_factor_is_already_disabled(
        self,
        verify_token: MagicMock,
    ) -> None:
        request = self._request("/two-factor/disable/")
        user = self._user(is_two_factor=False)
        request.user = user

        response = TwoFactorDisableView().post(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, {"error": "Invalid 2FA code."})
        user.save.assert_not_called()
        verify_token.assert_called_once_with("user@example.com", "unit-user", "123456")


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Logout clears active-login state and verifySession fails closed on bad HMAC data")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "hmac")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class SessionLifecycleViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _verified_request(self, hmac_cookie: str = "1000:provided-hmac"):
        request = self.factory.get(
            "/verifySession/",
            HTTP_ACCEPT="application/json",
            HTTP_X_FORWARDED_HOST="next.localhost:8081",
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_ORIGINAL_CLIENT_IP="203.0.113.44",
            HTTP_USER_AGENT="Unit Browser",
            HTTP_SEC_CH_UA_PLATFORM='"Linux"',
        )
        request.COOKIES["sessionid"] = "fresh-session-key"
        request.COOKIES["hmac"] = hmac_cookie
        request.user = SimpleNamespace(
            pk=42,
            username="unit-user",
            first_name="Unit",
            email="user@example.com",
            is_authenticated=True,
        )
        request.session = MagicMock()
        request.session.session_key = "fresh-session-key"
        request.session.get.side_effect = lambda key, default=None: {"wallet_user_id": "wallet-user-1"}.get(
            key,
            default,
        )
        return request

    @patch("userauth.views._clear_active_login")
    @patch("userauth.views.logout")
    def test_logout_flushes_session_and_clears_active_login(self, django_logout: MagicMock, clear_active: MagicMock) -> None:
        request = self.factory.post("/logout/")
        request.user = SimpleNamespace(pk=42)
        request.session = MagicMock()
        request.session.session_key = "fresh-session-key"

        response = LogoutView().post(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"message": "Logout successful"})
        django_logout.assert_called_once_with(request)
        request.session.flush.assert_not_called()
        clear_active.assert_called_once_with(42, "fresh-session-key")
        self.assertIn("hmac", response.cookies)

    def test_verify_session_rejects_malformed_hmac_token(self) -> None:
        request = self._verified_request(hmac_cookie="not-a-valid-token")

        response = VerifySessionView().get(request)

        self.assertEqual(response.status_code, 400)

    @patch.object(VerifySessionView, "get", return_value=Response({"ok": True}))
    def test_verify_session_accepts_next_server_action_forwardauth_request(
        self,
        _get: MagicMock,
    ) -> None:
        request = self.factory.get(
            "/verifySession/",
            HTTP_ACCEPT="text/x-component",
            HTTP_USER_AGENT="Unit Browser",
        )

        with patch.object(VerifySessionView, "throttle_classes", []):
            response = VerifySessionView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        _get.assert_called_once()

    @patch("userauth.views.logout")
    @patch("userauth.views.HmacToken.is_valid_hmac", return_value=False)
    def test_verify_session_logs_out_and_redirects_when_hmac_validation_fails(
        self,
        _is_valid_hmac: MagicMock,
        django_logout: MagicMock,
    ) -> None:
        request = self._verified_request()

        response = VerifySessionView().get(request)

        self.assertEqual(response.status_code, 302)
        django_logout.assert_called_once_with(request)

    @patch("userauth.views.time.time", return_value=1_001)
    @patch("userauth.views.HmacToken.calculate_token", return_value="fresh-hmac")
    @patch("userauth.views.HmacToken.is_valid_hmac", return_value=True)
    @patch("userauth.views.cache")
    def test_verify_session_refreshes_hmac_headers_and_active_login(
        self,
        cache: MagicMock,
        _is_valid_hmac: MagicMock,
        _calculate_token: MagicMock,
        _time: MagicMock,
    ) -> None:
        request = self._verified_request()

        response = VerifySessionView().get(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-User"], "unit-user")
        self.assertEqual(response.headers["X-User-Id"], "wallet-user-1")
        self.assertEqual(response.cookies["hmac"].value, "1001:fresh-hmac")
        self.assertTrue(any(call.args[0] == "active_login:42" for call in cache.set.call_args_list))
