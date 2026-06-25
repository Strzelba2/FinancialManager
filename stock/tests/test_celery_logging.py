from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

import allure
import pytest

from app.core import celery_app


pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Stock Background Tasks")
@allure.story("Celery logging falls back when the log file is not writable")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "celery", "logging")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class CeleryLoggingTests(unittest.TestCase):
    def test_build_log_handler_falls_back_to_stream_when_file_is_not_writable(self) -> None:
        with patch("app.core.celery_app.logging.FileHandler", side_effect=PermissionError("denied")):
            handler = celery_app._build_log_handler("/stock_api/logs/celery_stock.json")

        self.assertIsInstance(handler, logging.StreamHandler)
        self.assertNotIsInstance(handler, logging.FileHandler)
