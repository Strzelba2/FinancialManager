from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest
from fastapi import HTTPException

from app.api.services.sell_assets_service import (
    sell_metal_holding_service,
    sell_real_estate_service,
)
from app.models.enums import CapitalGainKind, Currency, MetalType
from app.schemas.response import SellMetalIn, SellRealEstateIn

pytestmark = pytest.mark.unit


class _Begin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session() -> Mock:
    session = Mock()
    session.begin = Mock(return_value=_Begin())
    session.add = Mock()
    session.flush = AsyncMock()
    return session


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Asset sale services realize gains and update financial state")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "money", "metals", "real-estate", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Covers realized PnL, optional cash transaction creation, deposit balance updates, "
    "partial metal cost-basis allocation, full metal disposal, and ownership/currency errors."
)
class SellAssetsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_metal_sale_allocates_cost_basis_and_updates_cash_balance(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        account_id = uuid4()
        metal_id = uuid4()
        tx_id = uuid4()
        occurred = datetime(2026, 6, 1, 10, tzinfo=timezone.utc)
        session = _session()
        holding = SimpleNamespace(
            id=metal_id,
            wallet_id=wallet_id,
            metal=MetalType.GOLD,
            grams=Decimal("30.000000"),
            cost_basis=Decimal("900.00"),
            cost_currency=Currency.PLN,
        )
        balance = SimpleNamespace(available=Decimal("1000.00"))
        req = SellMetalIn(
            deposit_account_id=account_id,
            grams_sold=Decimal("10.000000"),
            proceeds_amount=Decimal("400.00"),
            proceeds_currency="PLN",
            occurred_at=occurred,
            create_transaction=True,
        )

        with (
            patch("app.api.services.sell_assets_service.get_metal_holding", new=AsyncMock(return_value=holding)),
            patch(
                "app.api.services.sell_assets_service.get_wallet",
                new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id)),
            ),
            patch(
                "app.api.services.sell_assets_service.get_deposit_account",
                new=AsyncMock(return_value=SimpleNamespace(id=account_id, wallet_id=wallet_id, currency=Currency.PLN)),
            ),
            patch("app.api.services.sell_assets_service.get_last_balance_after", new=AsyncMock(return_value=Decimal("1000.00"))),
            patch(
                "app.api.services.sell_assets_service.create_transaction_uow",
                new=AsyncMock(return_value=SimpleNamespace(id=tx_id)),
            ) as create_tx,
            patch("app.api.services.sell_assets_service.get_deposit_account_balance", new=AsyncMock(return_value=balance)),
            patch("app.api.services.sell_assets_service.update_metal_holding", new=AsyncMock()) as update_holding,
            patch("app.api.services.sell_assets_service.delete_metal_holding", new=AsyncMock()) as delete_holding,
        ):
            result = await sell_metal_holding_service(session, user_id, metal_id, req)

        self.assertEqual(result, 1)
        capital_gain = session.add.call_args_list[0].args[0]
        self.assertEqual(capital_gain.kind, CapitalGainKind.METAL_REALIZED_PNL)
        self.assertEqual(capital_gain.amount, Decimal("100.0000000000"))
        self.assertEqual(capital_gain.currency, Currency.PLN)
        self.assertEqual(capital_gain.transaction_id, tx_id)
        create_tx.assert_awaited_once()
        tx_payload = create_tx.await_args.args[1]
        self.assertEqual(tx_payload.amount, Decimal("400.00"))
        self.assertEqual(tx_payload.balance_before, Decimal("1000.00"))
        self.assertEqual(tx_payload.balance_after, Decimal("1400.00"))
        self.assertEqual(balance.available, Decimal("1400.00"))
        update_holding.assert_awaited_once()
        update_payload = update_holding.await_args.kwargs["payload"]
        self.assertEqual(update_payload.grams, Decimal("20.000000"))
        self.assertEqual(update_payload.cost_basis, Decimal("600.0000000000"))
        delete_holding.assert_not_awaited()

    async def test_full_metal_sale_deletes_holding_by_id_without_cash_transaction(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        account_id = uuid4()
        metal_id = uuid4()
        session = _session()
        holding = SimpleNamespace(
            id=metal_id,
            wallet_id=wallet_id,
            metal=MetalType.SILVER,
            grams=Decimal("5.000000"),
            cost_basis=Decimal("100.00"),
            cost_currency=Currency.PLN,
        )
        req = SellMetalIn(
            deposit_account_id=account_id,
            grams_sold=Decimal("5.000000"),
            proceeds_amount=Decimal("150.00"),
            proceeds_currency="PLN",
            create_transaction=False,
        )

        with (
            patch("app.api.services.sell_assets_service.get_metal_holding", new=AsyncMock(return_value=holding)),
            patch(
                "app.api.services.sell_assets_service.get_wallet",
                new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id)),
            ),
            patch(
                "app.api.services.sell_assets_service.get_deposit_account",
                new=AsyncMock(return_value=SimpleNamespace(id=account_id, wallet_id=wallet_id, currency=Currency.PLN)),
            ),
            patch("app.api.services.sell_assets_service.create_transaction_uow", new=AsyncMock()) as create_tx,
            patch("app.api.services.sell_assets_service.update_metal_holding", new=AsyncMock()) as update_holding,
            patch("app.api.services.sell_assets_service.delete_metal_holding", new=AsyncMock()) as delete_holding,
        ):
            result = await sell_metal_holding_service(session, user_id, metal_id, req)

        self.assertEqual(result, 1)
        delete_holding.assert_awaited_once_with(session, metal_id)
        update_holding.assert_not_awaited()
        create_tx.assert_not_awaited()

    async def test_metal_sale_rejects_oversell_before_persisting_gain(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        account_id = uuid4()
        metal_id = uuid4()
        session = _session()
        req = SellMetalIn(
            deposit_account_id=account_id,
            grams_sold=Decimal("10.000000"),
            proceeds_amount=Decimal("100.00"),
            proceeds_currency="PLN",
        )

        with (
            patch(
                "app.api.services.sell_assets_service.get_metal_holding",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        id=metal_id,
                        wallet_id=wallet_id,
                        grams=Decimal("2.000000"),
                        cost_basis=Decimal("40.00"),
                        cost_currency=Currency.PLN,
                    )
                ),
            ),
            patch(
                "app.api.services.sell_assets_service.get_wallet",
                new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id)),
            ),
            patch(
                "app.api.services.sell_assets_service.get_deposit_account",
                new=AsyncMock(return_value=SimpleNamespace(id=account_id, wallet_id=wallet_id, currency=Currency.PLN)),
            ),
        ):
            with self.assertRaises(HTTPException) as exc:
                await sell_metal_holding_service(session, user_id, metal_id, req)

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(session.add.call_count, 0)

    async def test_real_estate_sale_realizes_pnl_creates_income_transaction_and_deletes_asset(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        account_id = uuid4()
        real_estate_id = uuid4()
        tx_id = uuid4()
        occurred = datetime(2026, 6, 2, 9, tzinfo=timezone.utc)
        session = _session()
        balance = SimpleNamespace(available=Decimal("2000.00"))
        req = SellRealEstateIn(
            deposit_account_id=account_id,
            proceeds_amount=Decimal("650000.00"),
            proceeds_currency="PLN",
            occurred_at=occurred,
            create_transaction=True,
        )

        with (
            patch(
                "app.api.services.sell_assets_service.get_real_estate",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        id=real_estate_id,
                        wallet_id=wallet_id,
                        name="Mieszkanie Warszawa",
                        purchase_price=Decimal("500000.00"),
                        purchase_currency=Currency.PLN,
                    )
                ),
            ),
            patch(
                "app.api.services.sell_assets_service.get_wallet",
                new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id)),
            ),
            patch(
                "app.api.services.sell_assets_service.get_deposit_account",
                new=AsyncMock(return_value=SimpleNamespace(id=account_id, wallet_id=wallet_id, currency=Currency.PLN)),
            ),
            patch("app.api.services.sell_assets_service.get_last_balance_after", new=AsyncMock(return_value=Decimal("2000.00"))),
            patch(
                "app.api.services.sell_assets_service.create_transaction_uow",
                new=AsyncMock(return_value=SimpleNamespace(id=tx_id)),
            ) as create_tx,
            patch("app.api.services.sell_assets_service.get_deposit_account_balance", new=AsyncMock(return_value=balance)),
            patch("app.api.services.sell_assets_service.delete_real_estate", new=AsyncMock()) as delete_real_estate,
        ):
            result = await sell_real_estate_service(session, user_id, real_estate_id, req)

        self.assertEqual(result, 1)
        capital_gain = session.add.call_args_list[0].args[0]
        self.assertEqual(capital_gain.kind, CapitalGainKind.REAL_ESTATE_REALIZED_PNL)
        self.assertEqual(capital_gain.amount, Decimal("150000.00"))
        self.assertEqual(capital_gain.transaction_id, tx_id)
        tx_payload = create_tx.await_args.args[1]
        self.assertEqual(tx_payload.description, "Property sale: Mieszkanie Warszawa")
        self.assertEqual(tx_payload.balance_after, Decimal("652000.00"))
        self.assertEqual(balance.available, Decimal("652000.00"))
        delete_real_estate.assert_awaited_once_with(session, real_estate_id)

    async def test_real_estate_sale_rejects_foreign_wallet_before_cash_effects(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        real_estate_id = uuid4()
        session = _session()
        req = SellRealEstateIn(
            deposit_account_id=uuid4(),
            proceeds_amount=Decimal("650000.00"),
            proceeds_currency="PLN",
        )

        with (
            patch(
                "app.api.services.sell_assets_service.get_real_estate",
                new=AsyncMock(return_value=SimpleNamespace(id=real_estate_id, wallet_id=wallet_id)),
            ),
            patch(
                "app.api.services.sell_assets_service.get_wallet",
                new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=uuid4())),
            ),
            patch("app.api.services.sell_assets_service.create_transaction_uow", new=AsyncMock()) as create_tx,
        ):
            with self.assertRaises(HTTPException) as exc:
                await sell_real_estate_service(session, user_id, real_estate_id, req)

        self.assertEqual(exc.exception.status_code, 404)
        create_tx.assert_not_awaited()
