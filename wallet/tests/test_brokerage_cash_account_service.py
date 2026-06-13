from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest
from fastapi import HTTPException

from app.api.services.accounts import (
    create_brokerage_cash_account_link_service,
    create_deposit_account_service,
)
from app.models.enums import AccountType, Currency
from app.schemas.schemas import AccountCreation, BrokerageCashAccountCreate

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Brokerage cash subaccounts accept technical identifiers")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "cash-links", "account-create", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies that brokerage currency cash subaccounts can be created with a technical "
    "account identifier without forcing it through IBAN validation."
)
class BrokerageCashAccountServiceUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_technical_cash_identifier_is_not_treated_as_iban(self) -> None:
        session = Mock()
        brokerage_account_id = uuid4()
        wallet_id = uuid4()
        bank_id = uuid4()
        created_account = SimpleNamespace(id=uuid4())

        create_account_mock = AsyncMock(return_value=created_account)
        create_link_mock = AsyncMock()

        with (
            patch(
                "app.api.services.accounts.get_link_by_ba_and_currency",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.accounts.create_deposit_account_service",
                new=create_account_mock,
            ),
            patch(
                "app.api.services.accounts.create_brokerage_deposit_link",
                new=create_link_mock,
            ),
        ):
            account = await create_brokerage_cash_account_link_service(
                session=session,
                brokerage_account_id=brokerage_account_id,
                wallet_id=wallet_id,
                bank_id=bank_id,
                brokerage_name="Bossa IKE",
                cash_account=BrokerageCashAccountCreate(
                    currency=Currency.USD,
                    account_number="BOSSA-IKE-USD",
                    name="Bossa IKE · USD",
                ),
                username="artur",
                crypto=Mock(),
            )

        self.assertIs(account, created_account)
        account_payload = create_account_mock.await_args.kwargs["data"]
        self.assertEqual(account_payload.account_number, "BOSSA-IKE-USD")
        self.assertEqual(account_payload.currency, Currency.USD)
        self.assertIsNone(account_payload.iban)
        link_payload = create_link_mock.await_args.kwargs["data"]
        self.assertEqual(link_payload.deposit_account_id, created_account.id)
        self.assertEqual(link_payload.brokerage_account_id, brokerage_account_id)
        self.assertEqual(link_payload.currency, Currency.USD)

    async def test_deposit_account_creation_returns_503_when_crypto_service_fails(self) -> None:
        session = Mock()
        crypto = Mock(batch=AsyncMock(return_value=None))
        bank_id = uuid4()
        wallet_id = uuid4()

        with patch(
            "app.api.services.accounts.get_bank",
            new=AsyncMock(return_value=SimpleNamespace(id=bank_id)),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await create_deposit_account_service(
                    session=session,
                    data=AccountCreation(
                        name="Bossa IKE · USD",
                        account_type=AccountType.BROKERAGE,
                        currency=Currency.USD,
                        account_number="BOSSA-IKE-USD-ARTUR",
                        bank_id=bank_id,
                    ),
                    username="artur",
                    wallet_id=wallet_id,
                    crypto=crypto,
                )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Crypto server do not work correctly")
