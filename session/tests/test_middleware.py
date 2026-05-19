from __future__ import annotations

from unittest.mock import MagicMock, patch

import allure
import pytest
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from middleware.logmiddleware import RequestLoggingMiddleware
from middleware.reqmiddleware import RequestMiddleware

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Session middleware handles low-risk request decisions")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("middleware", "security")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class MiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_logging_middleware_returns_downstream_response(self) -> None:
        response = HttpResponse("ok", status=204)
        get_response = MagicMock(return_value=response)
        middleware = RequestLoggingMiddleware(get_response)

        result = middleware(self.factory.get("/healthz"))

        self.assertIs(result, response)
        get_response.assert_called_once()

    @override_settings(NEXT_UI_DOMAIN="next.localhost", UI_DOMAIN="wallet.localhost", APP_PROTOCOL="http")
    def test_request_middleware_bypasses_health_probe(self) -> None:
        response = HttpResponse("ok", status=200)
        get_response = MagicMock(return_value=response)
        middleware = RequestMiddleware(get_response)
        request = self.factory.get("/healthz", HTTP_USER_AGENT="Mozilla/5.0")

        result = middleware(request)

        self.assertIs(result, response)
        get_response.assert_called_once_with(request)

    @override_settings(NEXT_UI_DOMAIN="next.localhost", UI_DOMAIN="wallet.localhost", APP_PROTOCOL="http")
    @patch("middleware.reqmiddleware.BlockedIP")
    def test_request_middleware_rejects_missing_user_agent(self, blocked_ip_mock: MagicMock) -> None:
        blocked_ip_mock.objects.filter.return_value.first.return_value = None
        middleware = RequestMiddleware(MagicMock(return_value=HttpResponse("ok")))
        request = self.factory.get("/wallet")
        request.META["HTTP_USER_AGENT"] = ""

        response = middleware(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"The User-Agent header is missing.", response.content)

    @override_settings(NEXT_UI_DOMAIN="next.localhost", UI_DOMAIN="wallet.localhost", APP_PROTOCOL="http")
    @patch("middleware.reqmiddleware.BlockedIP")
    def test_request_middleware_rejects_bot_user_agent(self, blocked_ip_mock: MagicMock) -> None:
        blocked_ip_mock.objects.filter.return_value.first.return_value = None
        middleware = RequestMiddleware(MagicMock(return_value=HttpResponse("ok")))
        request = self.factory.get(
            "/wallet",
            HTTP_USER_AGENT="Googlebot/2.1 (+http://www.google.com/bot.html)",
        )

        response = middleware(request)

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Bots are blocked.", response.content)
