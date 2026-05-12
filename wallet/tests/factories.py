from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any


def wallet_user(**overrides: Any) -> SimpleNamespace:
    data = {
        "id": "user-001",
        "username": "artur.tests",
        "first_name": "artur",
        "email": "artur.tests@example.com",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def wallet(**overrides: Any) -> SimpleNamespace:
    data = {
        "id": "wallet-001",
        "name": "Main test wallet",
        "currency": "PLN",
        "user_id": "user-001",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def deposit_account(**overrides: Any) -> SimpleNamespace:
    data = {
        "id": "account-001",
        "wallet_id": "wallet-001",
        "name": "Primary account",
        "currency": "PLN",
        "available": Decimal("10000.00"),
        "blocked": Decimal("0.00"),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def transaction(**overrides: Any) -> SimpleNamespace:
    data = {
        "id": "transaction-001",
        "account_id": "account-001",
        "amount": Decimal("125.50"),
        "currency": "PLN",
        "type": "expense",
        "transaction_date": date(2026, 5, 5),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def holding(**overrides: Any) -> SimpleNamespace:
    data = {
        "symbol": "TEST",
        "mic": "XWAR",
        "quantity": Decimal("2"),
        "avg_price": Decimal("15.50"),
        "currency": "PLN",
    }
    data.update(overrides)
    return SimpleNamespace(**data)
