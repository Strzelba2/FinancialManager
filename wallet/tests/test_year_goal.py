from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import allure
import pytest
from pydantic import ValidationError

from app.crud.year_goal_crud import create_year_goal, update_year_goal, upsert_year_goal
from app.models.enums import Currency
from app.schemas.schemas import YearGoalCreate, YearGoalUpdate


pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Year goals persist expected capital gain targets separately from revenue and expense goals")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "goals", "money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class YearGoalTests(IsolatedAsyncioTestCase):
    def test_year_goal_create_defaults_capital_gain_target_to_zero(self) -> None:
        payload = YearGoalCreate(
            wallet_id=uuid.uuid4(),
            year=2026,
            rev_target_year=Decimal("120000.00"),
            exp_budget_year=Decimal("80000.00"),
            currency=Currency.PLN,
        )

        self.assertEqual(payload.capital_gain_target_year, Decimal("0.00"))

    def test_year_goal_create_rejects_negative_capital_gain_target(self) -> None:
        with self.assertRaises(ValidationError):
            YearGoalCreate(
                wallet_id=uuid.uuid4(),
                year=2026,
                rev_target_year=Decimal("120000.00"),
                exp_budget_year=Decimal("80000.00"),
                capital_gain_target_year=Decimal("-1.00"),
                currency=Currency.PLN,
            )

    async def test_upsert_updates_existing_capital_gain_target(self) -> None:
        wallet_id = uuid.uuid4()
        existing = SimpleNamespace(
            wallet_id=wallet_id,
            year=2026,
            rev_target_year=Decimal("100000.00"),
            exp_budget_year=Decimal("70000.00"),
            capital_gain_target_year=Decimal("5000.00"),
            currency=Currency.PLN,
        )
        payload = YearGoalCreate(
            wallet_id=wallet_id,
            year=2026,
            rev_target_year=Decimal("120000.00"),
            exp_budget_year=Decimal("80000.00"),
            capital_gain_target_year=Decimal("24000.00"),
            currency=Currency.PLN,
        )
        session = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        with patch("app.crud.year_goal_crud.get_year_goal", new=AsyncMock(return_value=existing)):
            result = await upsert_year_goal(session, payload=payload)

        self.assertIs(result, existing)
        self.assertEqual(existing.rev_target_year, Decimal("120000.00"))
        self.assertEqual(existing.exp_budget_year, Decimal("80000.00"))
        self.assertEqual(existing.capital_gain_target_year, Decimal("24000.00"))
        session.add.assert_called_once_with(existing)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(existing)

    async def test_create_refreshes_year_goal_before_response_serialization(self) -> None:
        payload = YearGoalCreate(
            wallet_id=uuid.uuid4(),
            year=2026,
            rev_target_year=Decimal("120000.00"),
            exp_budget_year=Decimal("80000.00"),
            capital_gain_target_year=Decimal("24000.00"),
            currency=Currency.PLN,
        )
        session = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        result = await create_year_goal(session, payload=payload)

        session.add.assert_called_once_with(result)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(result)

    async def test_update_refreshes_year_goal_before_response_serialization(self) -> None:
        goal_id = uuid.uuid4()
        existing = SimpleNamespace(
            id=goal_id,
            rev_target_year=Decimal("100000.00"),
            exp_budget_year=Decimal("70000.00"),
            capital_gain_target_year=Decimal("5000.00"),
            currency=Currency.PLN,
        )
        session = MagicMock()
        session.get = AsyncMock(return_value=existing)
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        patch_payload = YearGoalUpdate(capital_gain_target_year=Decimal("60000.00"))

        result = await update_year_goal(session, goal_id=goal_id, patch=patch_payload)

        self.assertIs(result, existing)
        self.assertEqual(existing.capital_gain_target_year, Decimal("60000.00"))
        session.add.assert_called_once_with(existing)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(existing)
