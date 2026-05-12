from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import allure
import pytest
from django.test import RequestFactory, SimpleTestCase

from userauth.views_health import healthz, readyz

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Health views expose deterministic probe payloads")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("health")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class HealthViewsTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_healthz_returns_ok_payload(self) -> None:
        response = healthz(self.factory.get("/healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"status": "ok"})

    @patch("userauth.views_health.cache")
    @patch("userauth.views_health.connections")
    def test_readyz_returns_ready_when_db_and_cache_work(self, connections_mock: MagicMock, cache_mock: MagicMock) -> None:
        connections_mock.__getitem__.return_value.cursor.return_value.execute.return_value = None
        cache_mock.get.return_value = "1"

        response = readyz(self.factory.get("/readyz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"status": "ready"})

    @patch("userauth.views_health.connections")
    def test_readyz_returns_db_down_when_database_probe_fails(self, connections_mock: MagicMock) -> None:
        connections_mock.__getitem__.return_value.cursor.return_value.execute.side_effect = RuntimeError("db unavailable")

        response = readyz(self.factory.get("/readyz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content), {"status": "db_down"})

    @patch("userauth.views_health.cache")
    @patch("userauth.views_health.connections")
    def test_readyz_returns_cache_down_when_cache_probe_fails(self, connections_mock: MagicMock, cache_mock: MagicMock) -> None:
        connections_mock.__getitem__.return_value.cursor.return_value.execute.return_value = None
        cache_mock.get.return_value = None

        response = readyz(self.factory.get("/readyz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content), {"status": "cache_down"})
