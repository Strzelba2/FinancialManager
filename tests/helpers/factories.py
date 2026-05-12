from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


def _with_overrides(payload: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    result = deepcopy(payload)
    result.update({key: value for key, value in overrides.items() if value is not None})
    return result


def user_payload(**overrides: Any) -> dict[str, Any]:
    return _with_overrides(
        {
            "username": "artur.tests",
            "email": "artur.tests@example.com",
            "first_name": "artur",
            "last_name": "Tester",
            "password": "ChangeMe-12345",
        },
        **overrides,
    )


def auth_headers(user_id: str = "test-user-001", username: str = "artur.tests") -> dict[str, str]:
    return {
        "X-User-Id": user_id,
        "X-User": username,
        "X-First-Name": "artur",
        "X-Email": "artur.tests@example.com",
    }


def auth_cookies() -> dict[str, str]:
    return {
        "sessionid": "test-session-id",
        "hmac": "test-hmac",
    }


def wallet_payload(**overrides: Any) -> dict[str, Any]:
    return _with_overrides(
        {
            "name": "Main test wallet",
            "currency": "PLN",
        },
        **overrides,
    )


def account_payload(**overrides: Any) -> dict[str, Any]:
    return _with_overrides(
        {
            "name": "Primary brokerage account",
            "currency": "PLN",
            "cash_balance": str(Decimal("10000.00")),
        },
        **overrides,
    )


def instrument_payload(**overrides: Any) -> dict[str, Any]:
    return _with_overrides(
        {
            "symbol": "TEST",
            "mic": "XWAR",
            "isin": "PLTEST000001",
            "name": "Test Instrument S.A.",
            "currency": "PLN",
        },
        **overrides,
    )


def quote_payload(**overrides: Any) -> dict[str, Any]:
    return _with_overrides(
        {
            "symbol": "TEST",
            "mic": "XWAR",
            "price": "42.50",
            "currency": "PLN",
            "quoted_at": datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc).isoformat(),
        },
        **overrides,
    )


def transaction_payload(**overrides: Any) -> dict[str, Any]:
    return _with_overrides(
        {
            "type": "expense",
            "amount": "125.50",
            "currency": "PLN",
            "description": "Deterministic grocery expense",
            "transaction_date": date(2026, 5, 5).isoformat(),
        },
        **overrides,
    )


def brokerage_event_payload(**overrides: Any) -> dict[str, Any]:
    return _with_overrides(
        {
            "kind": "TRADE_BUY",
            "symbol": "TEST",
            "mic": "XWAR",
            "quantity": "2",
            "price": "15.50",
            "currency": "PLN",
            "event_date": date(2026, 5, 5).isoformat(),
        },
        **overrides,
    )


def price_alert_payload(**overrides: Any) -> dict[str, Any]:
    return _with_overrides(
        {
            "symbol": "TEST",
            "mic": "XWAR",
            "target_price": "50.00",
            "direction": "above",
            "currency": "PLN",
        },
        **overrides,
    )
