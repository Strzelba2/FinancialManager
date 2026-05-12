from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any


def market(**overrides: Any) -> SimpleNamespace:
    data = {
        "id": "market-001",
        "mic": "XWAR",
        "name": "Warsaw Stock Exchange",
        "currency": "PLN",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def instrument(**overrides: Any) -> SimpleNamespace:
    data = {
        "id": "instrument-001",
        "symbol": "TEST",
        "mic": "XWAR",
        "isin": "PLTEST000001",
        "name": "Test Instrument S.A.",
        "currency": "PLN",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def latest_quote(**overrides: Any) -> SimpleNamespace:
    data = {
        "symbol": "TEST",
        "mic": "XWAR",
        "price": Decimal("42.50"),
        "currency": "PLN",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def daily_candles(start: date = date(2026, 1, 1), periods: int = 5) -> list[dict[str, Any]]:
    return [
        {
            "date_quote": start + timedelta(days=idx),
            "open": Decimal("10.00") + idx,
            "high": Decimal("11.00") + idx,
            "low": Decimal("9.50") + idx,
            "close": Decimal("10.50") + idx,
            "volume": 1000 + idx,
        }
        for idx in range(periods)
    ]
