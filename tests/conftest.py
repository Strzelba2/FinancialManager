from __future__ import annotations

import os

import pytest

from tests.helpers import factories


@pytest.fixture
def test_data():
    return factories


@pytest.fixture
def traefik_url() -> str:
    return "http://traefik"


@pytest.fixture
def session_url() -> str:
    return "http://session-auth:8000"


@pytest.fixture
def wallet_url() -> str:
    return "http://wallet:8001"


@pytest.fixture
def stock_url() -> str:
    return "http://stock:8001"


@pytest.fixture
def quote_source_base_url() -> str:
    return os.environ.get("ST_BASE_URL", "").rstrip("/")
