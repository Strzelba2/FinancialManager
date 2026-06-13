from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest

from app.api.services.accounts import delete_brokerage_account_with_cash_accounts_service
from app.models.enums import AccountType

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Brokerage account deletion removes dedicated cash accounts")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "cash-links", "money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies the domain rule that deleting a brokerage account removes ordinary "
    "deposit accounts created only for that brokerage cash link, while shared deposit "
    "accounts are preserved."
)
class BrokerageAccountDeleteServiceUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_deletes_dedicated_brokerage_cash_deposit_account(self) -> None:
        session = Mock(delete=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
        user_id = uuid4()
        brokerage_id = uuid4()
        deposit_id = uuid4()
        brokerage_account = SimpleNamespace(id=brokerage_id)
        link = SimpleNamespace(
            brokerage_account_id=brokerage_id,
            deposit_account_id=deposit_id,
        )
        deposit_account = SimpleNamespace(
            id=deposit_id,
            account_type=AccountType.BROKERAGE,
        )

        with (
            patch(
                "app.api.services.accounts.get_brokerage_account_for_user",
                new=AsyncMock(return_value=brokerage_account),
            ),
            patch(
                "app.api.services.accounts.list_brokerage_deposit_links",
                new=AsyncMock(side_effect=[[link], [link]]),
            ),
            patch(
                "app.api.services.accounts.get_deposit_account_for_user",
                new=AsyncMock(return_value=deposit_account),
            ),
        ):
            ok = await delete_brokerage_account_with_cash_accounts_service(
                session=session,
                user_id=user_id,
                brokerage_account_id=brokerage_id,
            )

        self.assertTrue(ok)
        self.assertEqual(
            [call.args[0] for call in session.delete.await_args_list],
            [deposit_account, brokerage_account],
        )
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    async def test_keeps_shared_cash_deposit_account(self) -> None:
        session = Mock(delete=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
        user_id = uuid4()
        brokerage_id = uuid4()
        other_brokerage_id = uuid4()
        deposit_id = uuid4()
        brokerage_account = SimpleNamespace(id=brokerage_id)
        link = SimpleNamespace(
            brokerage_account_id=brokerage_id,
            deposit_account_id=deposit_id,
        )
        sibling_link = SimpleNamespace(
            brokerage_account_id=other_brokerage_id,
            deposit_account_id=deposit_id,
        )

        with (
            patch(
                "app.api.services.accounts.get_brokerage_account_for_user",
                new=AsyncMock(return_value=brokerage_account),
            ),
            patch(
                "app.api.services.accounts.list_brokerage_deposit_links",
                new=AsyncMock(side_effect=[[link], [link, sibling_link]]),
            ),
            patch(
                "app.api.services.accounts.get_deposit_account_for_user",
                new=AsyncMock(),
            ) as get_deposit_mock,
        ):
            ok = await delete_brokerage_account_with_cash_accounts_service(
                session=session,
                user_id=user_id,
                brokerage_account_id=brokerage_id,
            )

        self.assertTrue(ok)
        get_deposit_mock.assert_not_awaited()
        self.assertEqual(
            [call.args[0] for call in session.delete.await_args_list],
            [brokerage_account],
        )
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
