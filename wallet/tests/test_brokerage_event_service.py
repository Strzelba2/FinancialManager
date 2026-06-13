from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest
from fastapi import HTTPException, status

from app.api.services.brokerage_event import (
    create_brokerage_event_and_update_holding,
    get_or_create_stock_backed_instrument,
    resolve_stock_instrument,
)
from app.api.services.brokerage_history_import import import_brokerage_history_service
from app.core.exceptions import ImportMismatchError
from app.crud.broker_event_crud import rebuild_account_holdings_from_events
from app.crud.holding_crud import (
    HoldingQuantityExceeded,
    apply_conversion_to_holding_pair,
    apply_event_to_holding,
)
from app.models.enums import BrokerageEventKind, CapitalGainKind, Currency, InstrumentCurrency
from app.schemas.response import StockInstrumentRead
from app.schemas.schemas import BrokerageEventCreate, BrokerageHistoryImportRequest, BrokerageHistoryImportRow

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Brokerage event service separates holding-only events from cash and capital gain effects")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "capital-gains", "financial-data", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Brokerage CSV import creates events with creat_transaction=False. SELL events can "
    "still realize broker PnL with nullable transaction_id, while ADJUSTMENT events "
    "update holdings without creating cash transactions or capital gains."
)
class TestBrokerageEventService(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_stock_instrument_uses_injected_shared_stock_client(self) -> None:
        resolved = StockInstrumentRead(
            mic="XLON",
            symbol="LNGA.UK",
            shortname="LNGA.UK",
            name="WisdomTree Natural Gas",
            currency="USD",
            type="ETF",
            status="ACTIVE",
        )
        stock_client = Mock(resolve_instrument=AsyncMock(return_value=resolved))

        with patch("app.api.services.brokerage_event.StockClient") as stock_client_ctor:
            result = await resolve_stock_instrument(
                "xlon",
                "lnga.uk",
                stock_client=stock_client,
            )

        assert result is resolved
        stock_client.resolve_instrument.assert_awaited_once_with("xlon", "lnga.uk")
        stock_client_ctor.assert_not_called()

    async def test_stock_backed_mirror_uses_resolved_stock_instrument(self) -> None:
        session = Mock()
        resolved = StockInstrumentRead(
            mic="XLON",
            symbol="LNGA.UK",
            shortname="LNGA.UK",
            name="WisdomTree Natural Gas",
            currency="USD",
            type="ETF",
            status="ACTIVE",
        )
        instrument = SimpleNamespace(id=uuid4(), symbol="LNGA.UK")
        stock_client = object()

        with (
            patch(
                "app.api.services.brokerage_event.resolve_stock_instrument",
                new=AsyncMock(return_value=resolved),
            ) as resolve_mock,
            patch(
                "app.api.services.brokerage_event.get_or_create_instrument",
                new=AsyncMock(return_value=instrument),
            ) as mirror_mock,
        ):
            result = await get_or_create_stock_backed_instrument(
                session,
                mic="XLON",
                symbol="LNGA.UK",
                stock_client=stock_client,
            )

        assert result is instrument
        resolve_mock.assert_awaited_once_with("XLON", "LNGA.UK", stock_client=stock_client)
        mirror_mock.assert_awaited_once()
        call_kwargs = mirror_mock.await_args.kwargs
        assert call_kwargs["mic"] == "XLON"
        assert call_kwargs["symbol"] == "LNGA.UK"
        assert call_kwargs["name"] == "WisdomTree Natural Gas"
        assert call_kwargs["currency"] == Currency.USD
        assert call_kwargs["instrument_type"].value == "ETF"

    async def test_event_rejects_instrument_missing_from_stock_before_writes(self) -> None:
        brokerage_account_id = uuid4()
        payload = BrokerageEventCreate(
            brokerage_account_id=brokerage_account_id,
            instrument_symbol="LNGA.UK",
            instrument_mic="XLON",
            instrument_name="Raw import name",
            kind=BrokerageEventKind.TRADE_BUY,
            quantity=Decimal("10"),
            price=Decimal("1.00"),
            currency=Currency.USD,
            split_ratio=Decimal("0"),
            trade_at=datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc),
        )

        with (
            patch(
                "app.api.services.brokerage_event.get_brokerage_account",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.services.brokerage_event.resolve_stock_instrument",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Instrument must be created in stock first.",
                    )
                ),
            ),
            patch(
                "app.api.services.brokerage_event.create_brokerage_event",
                new=AsyncMock(),
            ) as create_event_mock,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_brokerage_event_and_update_holding(Mock(), payload)

        assert exc_info.value.status_code == 422
        assert "stock" in str(exc_info.value.detail).lower()
        create_event_mock.assert_not_called()

    async def test_duplicate_event_rejects_before_holding_cash_or_gain_writes(self) -> None:
        brokerage_account_id = uuid4()
        instrument_id = uuid4()
        payload = BrokerageEventCreate(
            brokerage_account_id=brokerage_account_id,
            instrument_symbol="PKOBP",
            instrument_mic="XWAR",
            instrument_name="PKO BP SA",
            kind=BrokerageEventKind.TRADE_BUY,
            quantity=Decimal("10"),
            price=Decimal("20.00"),
            currency=Currency.PLN,
            split_ratio=Decimal("0"),
            trade_at=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
        )

        with (
            patch(
                "app.api.services.brokerage_event.get_brokerage_account",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_stock_backed_instrument",
                new=AsyncMock(return_value=SimpleNamespace(id=instrument_id)),
            ),
            patch(
                "app.api.services.brokerage_event.find_duplicate_brokerage_event",
                new=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_holding",
                new=AsyncMock(),
            ) as holding_mock,
            patch(
                "app.api.services.brokerage_event.create_brokerage_event",
                new=AsyncMock(),
            ) as create_event_mock,
            patch(
                "app.api.services.brokerage_event.resolve_deposit_for_event",
                new=AsyncMock(),
            ) as resolve_deposit_mock,
            patch(
                "app.api.services.brokerage_event.create_capital_gain",
                new=AsyncMock(),
            ) as create_gain_mock,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_brokerage_event_and_update_holding(Mock(), payload)

        assert exc_info.value.status_code == 409
        assert "already exists" in str(exc_info.value.detail)
        holding_mock.assert_not_called()
        create_event_mock.assert_not_called()
        resolve_deposit_mock.assert_not_called()
        create_gain_mock.assert_not_called()

    async def test_import_sell_realized_pnl_allows_capital_gain_without_transaction(self) -> None:
        brokerage_account_id = uuid4()
        instrument_id = uuid4()
        deposit_id = uuid4()
        payload = BrokerageEventCreate(
            brokerage_account_id=brokerage_account_id,
            instrument_symbol="FEERUM",
            instrument_mic="XWAR",
            instrument_name="FEERUM SA",
            kind=BrokerageEventKind.TRADE_SELL,
            quantity=Decimal("10"),
            price=Decimal("12.00"),
            currency=Currency.PLN,
            split_ratio=Decimal("0"),
            trade_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
        )
        session = Mock()
        session.delete = AsyncMock()
        session.refresh = AsyncMock()
        holding = SimpleNamespace(quantity=Decimal("20"), avg_cost=Decimal("9.00"))
        event = SimpleNamespace(id=uuid4(), brokerage_account_id=brokerage_account_id)
        created_gain = SimpleNamespace(id=uuid4())
        captured_gain_payloads = []

        async def fake_create_capital_gain(_session, data):
            captured_gain_payloads.append(data)
            return created_gain

        with (
            patch(
                "app.api.services.brokerage_event.get_brokerage_account",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_stock_backed_instrument",
                new=AsyncMock(return_value=SimpleNamespace(id=instrument_id)),
            ),
            patch(
                "app.api.services.brokerage_event.find_duplicate_brokerage_event",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_holding",
                new=AsyncMock(return_value=holding),
            ),
            patch(
                "app.api.services.brokerage_event.create_brokerage_event",
                new=AsyncMock(return_value=event),
            ),
            patch(
                "app.api.services.brokerage_event.resolve_deposit_for_event",
                new=AsyncMock(return_value=SimpleNamespace(id=deposit_id)),
            ),
            patch(
                "app.api.services.brokerage_event.create_capital_gain",
                new=AsyncMock(side_effect=fake_create_capital_gain),
            ),
        ):
            result_event, result_holding = await create_brokerage_event_and_update_holding(
                session,
                payload,
                creat_transaction=False,
            )

        assert result_event is event
        assert result_holding is holding
        assert len(captured_gain_payloads) == 1
        gain_payload = captured_gain_payloads[0]
        assert gain_payload.kind == CapitalGainKind.BROKER_REALIZED_PNL
        assert gain_payload.amount == Decimal("30.00")
        assert gain_payload.currency == Currency.PLN
        assert gain_payload.deposit_account_id == deposit_id
        assert gain_payload.transaction_id is None

    async def test_import_sell_foreign_currency_settles_in_account_currency_via_fx_rate(self) -> None:
        """CHF-priced SELL settles cash/PnL in the account currency (PLN) via fx_rate."""
        brokerage_account_id = uuid4()
        instrument_id = uuid4()
        deposit_id = uuid4()
        payload = BrokerageEventCreate(
            brokerage_account_id=brokerage_account_id,
            instrument_symbol="UHRN",
            instrument_mic="XSWX",
            instrument_name="Swatch Group AG",
            kind=BrokerageEventKind.TRADE_SELL,
            quantity=Decimal("10"),
            price=Decimal("30.00"),
            currency=InstrumentCurrency.CHF,
            split_ratio=Decimal("0"),
            trade_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            settlement_currency=Currency.PLN,
            fx_rate=Decimal("4.5"),
        )
        session = Mock()
        session.delete = AsyncMock()
        session.refresh = AsyncMock()
        holding = SimpleNamespace(quantity=Decimal("20"), avg_cost=Decimal("20.00"))
        event = SimpleNamespace(id=uuid4(), brokerage_account_id=brokerage_account_id)
        captured_deposit_currencies = []
        captured_gain_payloads = []

        async def fake_resolve_deposit(_session, brokerage_account_id, currency):
            captured_deposit_currencies.append(currency)
            return SimpleNamespace(id=deposit_id)

        async def fake_create_capital_gain(_session, data):
            captured_gain_payloads.append(data)
            return SimpleNamespace(id=uuid4())

        with (
            patch(
                "app.api.services.brokerage_event.get_brokerage_account",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_stock_backed_instrument",
                new=AsyncMock(return_value=SimpleNamespace(id=instrument_id)),
            ),
            patch(
                "app.api.services.brokerage_event.find_duplicate_brokerage_event",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_holding",
                new=AsyncMock(return_value=holding),
            ),
            patch(
                "app.api.services.brokerage_event.create_brokerage_event",
                new=AsyncMock(return_value=event),
            ),
            patch(
                "app.api.services.brokerage_event.resolve_deposit_for_event",
                new=AsyncMock(side_effect=fake_resolve_deposit),
            ),
            patch(
                "app.api.services.brokerage_event.create_capital_gain",
                new=AsyncMock(side_effect=fake_create_capital_gain),
            ),
        ):
            await create_brokerage_event_and_update_holding(
                session,
                payload,
                creat_transaction=False,
            )

        # Deposit is resolved in the account (settlement) currency, not CHF.
        assert captured_deposit_currencies == [Currency.PLN]
        # Realized PnL (10 * (30 - 20) = 100 CHF) converted to PLN via fx_rate 4.5.
        assert len(captured_gain_payloads) == 1
        gain_payload = captured_gain_payloads[0]
        assert gain_payload.currency == Currency.PLN
        assert gain_payload.amount == Decimal("450.0")

    async def test_foreign_currency_trade_requires_settlement_currency_and_fx_rate_before_holding_update(self) -> None:
        brokerage_account_id = uuid4()
        instrument_id = uuid4()
        payloads = [
            BrokerageEventCreate(
                brokerage_account_id=brokerage_account_id,
                instrument_symbol="UHRN",
                instrument_mic="XSWX",
                instrument_name="Swatch Group AG",
                kind=BrokerageEventKind.TRADE_BUY,
                quantity=Decimal("10"),
                price=Decimal("30.00"),
                currency=InstrumentCurrency.CHF,
                split_ratio=Decimal("0"),
                trade_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            ),
            BrokerageEventCreate(
                brokerage_account_id=brokerage_account_id,
                instrument_symbol="UHRN",
                instrument_mic="XSWX",
                instrument_name="Swatch Group AG",
                kind=BrokerageEventKind.TRADE_SELL,
                quantity=Decimal("10"),
                price=Decimal("30.00"),
                currency=InstrumentCurrency.CHF,
                split_ratio=Decimal("0"),
                trade_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
                settlement_currency=Currency.PLN,
            ),
        ]

        for payload in payloads:
            with self.subTest(kind=payload.kind, settlement_currency=payload.settlement_currency):
                with (
                    patch(
                        "app.api.services.brokerage_event.get_brokerage_account",
                        new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
                    ),
                    patch(
                        "app.api.services.brokerage_event.get_or_create_stock_backed_instrument",
                        new=AsyncMock(return_value=SimpleNamespace(id=instrument_id)),
                    ),
                    patch(
                        "app.api.services.brokerage_event.find_duplicate_brokerage_event",
                        new=AsyncMock(return_value=None),
                    ),
                    patch(
                        "app.api.services.brokerage_event.get_or_create_holding",
                        new=AsyncMock(),
                    ) as get_holding_mock,
                    patch(
                        "app.api.services.brokerage_event.create_brokerage_event",
                        new=AsyncMock(),
                    ) as create_event_mock,
                    patch(
                        "app.api.services.brokerage_event.resolve_deposit_for_event",
                        new=AsyncMock(),
                    ) as resolve_deposit_mock,
                    patch(
                        "app.api.services.brokerage_event.create_capital_gain",
                        new=AsyncMock(),
                    ) as create_gain_mock,
                ):
                    with pytest.raises(HTTPException) as exc_info:
                        await create_brokerage_event_and_update_holding(Mock(), payload)

                assert exc_info.value.status_code == 400
                assert "settlement" in str(exc_info.value.detail)
                get_holding_mock.assert_not_called()
                create_event_mock.assert_not_called()
                resolve_deposit_mock.assert_not_called()
                create_gain_mock.assert_not_called()

    async def test_adjustment_updates_holding_without_cash_transaction_or_capital_gain(self) -> None:
        brokerage_account_id = uuid4()
        instrument_id = uuid4()
        payload = BrokerageEventCreate(
            brokerage_account_id=brokerage_account_id,
            instrument_symbol="COMP",
            instrument_mic="XWAR",
            instrument_name="COMP SA",
            kind=BrokerageEventKind.ADJUSTMENT,
            quantity=Decimal("13"),
            price=Decimal("50.00"),
            currency=Currency.PLN,
            split_ratio=Decimal("0"),
            note="Korekta po scaleniu, stara nazwa: ELZAB",
            trade_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
        )
        session = Mock()
        session.delete = AsyncMock()
        session.refresh = AsyncMock()
        holding = SimpleNamespace(quantity=Decimal("0"), avg_cost=Decimal("0"))
        event = SimpleNamespace(id=uuid4(), brokerage_account_id=brokerage_account_id)

        resolve_deposit = AsyncMock()
        create_capital_gain_mock = AsyncMock()
        create_transaction_mock = AsyncMock()

        with (
            patch(
                "app.api.services.brokerage_event.get_brokerage_account",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_stock_backed_instrument",
                new=AsyncMock(return_value=SimpleNamespace(id=instrument_id)),
            ),
            patch(
                "app.api.services.brokerage_event.find_duplicate_brokerage_event",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_holding",
                new=AsyncMock(return_value=holding),
            ),
            patch(
                "app.api.services.brokerage_event.create_brokerage_event",
                new=AsyncMock(return_value=event),
            ),
            patch("app.api.services.brokerage_event.resolve_deposit_for_event", new=resolve_deposit),
            patch("app.api.services.brokerage_event.create_capital_gain", new=create_capital_gain_mock),
            patch("app.api.services.brokerage_event.create_transactions_service", new=create_transaction_mock),
        ):
            result_event, result_holding = await create_brokerage_event_and_update_holding(
                session,
                payload,
            )

        assert result_event is event
        assert result_holding is holding
        assert holding.quantity == Decimal("13")
        assert holding.avg_cost == Decimal("50.00")
        resolve_deposit.assert_not_called()
        create_capital_gain_mock.assert_not_called()
        create_transaction_mock.assert_not_called()

    async def test_conversion_moves_holding_to_target_without_cash_transaction_or_capital_gain(self) -> None:
        brokerage_account_id = uuid4()
        source_instrument_id = uuid4()
        target_instrument_id = uuid4()
        payload = BrokerageEventCreate(
            brokerage_account_id=brokerage_account_id,
            instrument_symbol="WORK",
            instrument_mic="XWAR",
            instrument_name="WORKSERV SA",
            target_instrument_symbol="GIG",
            target_instrument_mic="XWAR",
            target_instrument_name="GIGROUP SA",
            kind=BrokerageEventKind.CONVERSION,
            quantity=Decimal("1000"),
            price=Decimal("0"),
            currency=Currency.PLN,
            split_ratio=Decimal("0.2"),
            note="WORKSERV -> GIGROUP, scalenie 1:5",
            trade_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
        )
        session = Mock()
        session.delete = AsyncMock()
        session.refresh = AsyncMock()
        source_holding = SimpleNamespace(quantity=Decimal("1000"), avg_cost=Decimal("2.00"))
        target_holding = SimpleNamespace(quantity=Decimal("0"), avg_cost=Decimal("0"))
        event = SimpleNamespace(id=uuid4(), brokerage_account_id=brokerage_account_id)
        created_event_args = []

        async def fake_get_or_create_stock_backed_instrument(_session, *, mic, symbol, stock_client=None):
            if symbol == "WORK":
                return SimpleNamespace(id=source_instrument_id, symbol=symbol)
            if symbol == "GIG":
                return SimpleNamespace(id=target_instrument_id, symbol=symbol)
            raise AssertionError(f"unexpected instrument {symbol}")

        async def fake_get_or_create_holding(_session, *, account_id, instrument_id):
            assert account_id == brokerage_account_id
            if instrument_id == target_instrument_id:
                return target_holding
            raise AssertionError(f"unexpected get_or_create_holding {instrument_id}")

        async def fake_create_brokerage_event(_session, data, instrument_id, target_instrument_id=None):
            created_event_args.append((data, instrument_id, target_instrument_id))
            return event

        resolve_deposit = AsyncMock()
        create_capital_gain_mock = AsyncMock()
        create_transaction_mock = AsyncMock()

        with (
            patch(
                "app.api.services.brokerage_event.get_brokerage_account",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_stock_backed_instrument",
                new=AsyncMock(side_effect=fake_get_or_create_stock_backed_instrument),
            ),
            patch(
                "app.api.services.brokerage_event.find_duplicate_brokerage_event",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.brokerage_event.get_holding_by_keys",
                new=AsyncMock(return_value=source_holding),
            ),
            patch(
                "app.api.services.brokerage_event.get_or_create_holding",
                new=AsyncMock(side_effect=fake_get_or_create_holding),
            ),
            patch(
                "app.api.services.brokerage_event.create_brokerage_event",
                new=AsyncMock(side_effect=fake_create_brokerage_event),
            ),
            patch("app.api.services.brokerage_event.resolve_deposit_for_event", new=resolve_deposit),
            patch("app.api.services.brokerage_event.create_capital_gain", new=create_capital_gain_mock),
            patch("app.api.services.brokerage_event.create_transactions_service", new=create_transaction_mock),
        ):
            result_event, result_holding = await create_brokerage_event_and_update_holding(
                session,
                payload,
            )

        assert result_event is event
        assert result_holding is target_holding
        assert source_holding.quantity == Decimal("0")
        assert source_holding.avg_cost == Decimal("0")
        assert target_holding.quantity == Decimal("200.0")
        assert target_holding.avg_cost == Decimal("10.0")
        session.delete.assert_awaited_once_with(source_holding)
        session.refresh.assert_awaited_once_with(target_holding)
        assert created_event_args == [(payload, source_instrument_id, target_instrument_id)]
        resolve_deposit.assert_not_called()
        create_capital_gain_mock.assert_not_called()
        create_transaction_mock.assert_not_called()


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Brokerage holding rules preserve split, adjustment, and sell validation invariants")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "holdings", "money", "financial-data", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Validates holding-only brokerage rules without a database: split/reverse split "
    "adjust quantity and average cost, adjustment sets an audited baseline, and "
    "overselling returns row-level diagnostic context."
)
class TestBrokerageHoldingRules(unittest.TestCase):
    @staticmethod
    def _payload(
        kind: BrokerageEventKind,
        quantity: str = "0",
        price: str = "0",
        split_ratio: str = "0",
        symbol: str = "GIGRO",
        trade_at: datetime | None = None,
        note: str | None = None,
    ) -> BrokerageEventCreate:
        return BrokerageEventCreate(
            brokerage_account_id=uuid4(),
            instrument_symbol=symbol,
            instrument_mic="XWAR",
            instrument_name=f"{symbol} SA",
            kind=kind,
            quantity=Decimal(quantity),
            price=Decimal(price),
            currency=Currency.PLN,
            split_ratio=Decimal(split_ratio),
            note=note,
            trade_at=trade_at or datetime(2026, 6, 4, 9, 0, tzinfo=timezone.utc),
        )

    def test_split_and_reverse_split_preserve_position_value_basis(self) -> None:
        holding = SimpleNamespace(quantity=Decimal("10"), avg_cost=Decimal("20.00"))

        apply_event_to_holding(
            holding,
            self._payload(kind=BrokerageEventKind.SPLIT, split_ratio="2"),
        )
        self.assertEqual(holding.quantity, Decimal("20"))
        self.assertEqual(holding.avg_cost, Decimal("10.00"))

        apply_event_to_holding(
            holding,
            self._payload(kind=BrokerageEventKind.SPLIT, split_ratio="0.1"),
        )
        self.assertEqual(holding.quantity, Decimal("2.0"))
        self.assertEqual(holding.avg_cost, Decimal("100.00"))

    def test_split_rejects_zero_and_negative_ratios(self) -> None:
        for ratio in ("0", "-0.5"):
            with self.subTest(ratio=ratio):
                holding = SimpleNamespace(quantity=Decimal("10"), avg_cost=Decimal("20.00"))

                with self.assertRaises(HTTPException) as ctx:
                    apply_event_to_holding(
                        holding,
                        self._payload(kind=BrokerageEventKind.SPLIT, split_ratio=ratio),
                    )

                self.assertEqual(ctx.exception.status_code, 400)
                self.assertEqual(ctx.exception.detail, "Split ratio must be > 0.")
                self.assertEqual(holding.quantity, Decimal("10"))
                self.assertEqual(holding.avg_cost, Decimal("20.00"))

    def test_adjustment_sets_quantity_and_average_cost(self) -> None:
        holding = SimpleNamespace(quantity=Decimal("0"), avg_cost=Decimal("0"))

        apply_event_to_holding(
            holding,
            self._payload(
                kind=BrokerageEventKind.ADJUSTMENT,
                quantity="1269",
                price="3.50",
                symbol="GIGRO",
                note="Korekta po scaleniu, stara nazwa: WORKSERV",
            ),
        )

        self.assertEqual(holding.quantity, Decimal("1269"))
        self.assertEqual(holding.avg_cost, Decimal("3.50"))

    def test_conversion_moves_quantity_and_cost_basis_to_target_holding(self) -> None:
        source = SimpleNamespace(quantity=Decimal("1000"), avg_cost=Decimal("2.00"))
        target = SimpleNamespace(quantity=Decimal("0"), avg_cost=Decimal("0"))

        apply_conversion_to_holding_pair(
            source,
            target,
            self._payload(
                kind=BrokerageEventKind.CONVERSION,
                quantity="1000",
                split_ratio="0.2",
                symbol="WORK",
                note="WORKSERV -> GIGROUP, scalenie 1:5",
            ),
        )

        self.assertEqual(source.quantity, Decimal("0"))
        self.assertEqual(source.avg_cost, Decimal("0"))
        self.assertEqual(target.quantity, Decimal("200.0"))
        self.assertEqual(target.avg_cost, Decimal("10.0"))

    def test_conversion_rejects_invalid_quantity_ratio_and_missing_note(self) -> None:
        cases = [
            (
                self._payload(kind=BrokerageEventKind.CONVERSION, quantity="0", split_ratio="0.2", note="WORK -> GIG"),
                "CONVERSION source quantity must be positive.",
            ),
            (
                self._payload(kind=BrokerageEventKind.CONVERSION, quantity="10", split_ratio="0", note="WORK -> GIG"),
                "CONVERSION ratio must be > 0.",
            ),
            (
                self._payload(kind=BrokerageEventKind.CONVERSION, quantity="10", split_ratio="0.2", note=None),
                "CONVERSION note is required.",
            ),
        ]

        for payload, detail in cases:
            with self.subTest(detail=detail):
                source = SimpleNamespace(quantity=Decimal("100"), avg_cost=Decimal("2.00"))
                target = SimpleNamespace(quantity=Decimal("0"), avg_cost=Decimal("0"))

                with self.assertRaises(HTTPException) as ctx:
                    apply_conversion_to_holding_pair(source, target, payload)

                self.assertEqual(ctx.exception.status_code, 400)
                self.assertEqual(ctx.exception.detail, detail)
                self.assertEqual(source.quantity, Decimal("100"))
                self.assertEqual(source.avg_cost, Decimal("2.00"))
                self.assertEqual(target.quantity, Decimal("0"))
                self.assertEqual(target.avg_cost, Decimal("0"))

    def test_oversell_error_contains_instrument_date_and_missing_quantity(self) -> None:
        trade_at = datetime(2021, 12, 23, 15, 13, 53, tzinfo=timezone.utc)
        holding = SimpleNamespace(quantity=Decimal("0"), avg_cost=Decimal("0"))

        with self.assertRaises(HoldingQuantityExceeded) as ctx:
            apply_event_to_holding(
                holding,
                self._payload(
                    kind=BrokerageEventKind.TRADE_SELL,
                    quantity="1269",
                    price="1.00",
                    symbol="GIGRO",
                    trade_at=trade_at,
                ),
            )

        exc = ctx.exception
        self.assertIn("GIGRO", str(exc.detail))
        self.assertIn("2021-12-23", str(exc.detail))
        self.assertEqual(exc.context["instrument_symbol"], "GIGRO")
        self.assertEqual(exc.context["quantity"], Decimal("1269"))
        self.assertEqual(exc.context["held_quantity"], Decimal("0"))
        self.assertEqual(exc.context["missing_quantity"], Decimal("1269"))
        self.assertEqual(exc.context["reason_code"], "holding_quantity_exceeded")


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("BoSSA brokerage history import validates cash links and holding state before persisting")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "bossa", "cash-links", "financial-data", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Protects the BoSSA full-history import contract: every cash currency must be "
    "linked to the brokerage account before writes, and overselling rows expose "
    "instrument/date/quantity diagnostics without creating cash transactions."
)
class TestBrokerageHistoryImportService(unittest.IsolatedAsyncioTestCase):
    async def test_needs_review_blocks_history_import_before_writes(self) -> None:
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=uuid4(),
            rows=[
                BrokerageHistoryImportRow(
                    row_number=13,
                    operation_type="NEEDS_REVIEW",
                    trade_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
                    currency=Currency.USD,
                    amount=Decimal("12.34"),
                    amount_after=Decimal("12.34"),
                    description="WisdomTree Natural Gas",
                    instrument_name="WisdomTree Natural Gas",
                    review_reason="Nie znaleziono instrumentu WisdomTree Natural Gas (ISIN: IE00TEST0001), waluta USD.",
                )
            ],
        )

        with (
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(),
            ) as links_mock,
            patch(
                "app.api.services.brokerage_history_import.create_brokerage_event_and_update_holding",
                new=AsyncMock(),
            ) as create_event_mock,
            patch(
                "app.api.services.brokerage_history_import.create_transactions_rebalance_service",
                new=AsyncMock(),
            ) as create_transactions_mock,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await import_brokerage_history_service(
                    session=Mock(),
                    user_id=uuid4(),
                    payload=payload,
                )

        assert exc_info.value.status_code == 422
        assert "WisdomTree Natural Gas" in str(exc_info.value.detail)
        links_mock.assert_not_called()
        create_event_mock.assert_not_called()
        create_transactions_mock.assert_not_called()

    async def test_trade_without_instrument_fields_blocks_history_import_before_writes(self) -> None:
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=uuid4(),
            rows=[
                BrokerageHistoryImportRow(
                    row_number=21,
                    operation_type="BUY",
                    trade_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
                    currency=Currency.USD,
                    amount=Decimal("-10.00"),
                    amount_after=Decimal("90.00"),
                    description="Rozliczenie transakcji kupna",
                    event_kind=BrokerageEventKind.TRADE_BUY,
                    quantity=Decimal("1"),
                    price=Decimal("10.00"),
                )
            ],
        )

        with patch(
            "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
            new=AsyncMock(),
        ) as links_mock:
            with pytest.raises(HTTPException) as exc_info:
                await import_brokerage_history_service(
                    session=Mock(),
                    user_id=uuid4(),
                    payload=payload,
                )

        assert exc_info.value.status_code == 422
        assert "missing instrument_symbol" in str(exc_info.value.detail)
        links_mock.assert_not_called()

    async def test_stock_missing_instrument_blocks_history_import_before_writes(self) -> None:
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=uuid4(),
            rows=[
                BrokerageHistoryImportRow(
                    row_number=22,
                    operation_type="BUY",
                    trade_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
                    currency=Currency.USD,
                    amount=Decimal("-10.00"),
                    amount_after=Decimal("90.00"),
                    description="Rozliczenie transakcji kupna LNGA.UK",
                    instrument_symbol="LNGA.UK",
                    instrument_mic="XLON",
                    instrument_name="WisdomTree Natural Gas",
                    event_kind=BrokerageEventKind.TRADE_BUY,
                    quantity=Decimal("1"),
                    price=Decimal("10.00"),
                )
            ],
        )

        with (
            patch(
                "app.api.services.brokerage_history_import.resolve_stock_instrument",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Instrument must be created in stock first.",
                    )
                ),
            ),
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(),
            ) as links_mock,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await import_brokerage_history_service(
                    session=Mock(),
                    user_id=uuid4(),
                    payload=payload,
                )

        assert exc_info.value.status_code == 422
        assert "LNGA.UK" in str(exc_info.value.detail)
        links_mock.assert_not_called()

    async def test_missing_currency_cash_link_blocks_import_before_writes(self) -> None:
        brokerage_account_id = uuid4()
        deposit_id = uuid4()
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=brokerage_account_id,
            rows=[
                BrokerageHistoryImportRow(
                    row_number=7,
                    operation_type="TRANSFER",
                    trade_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
                    currency=Currency.USD,
                    amount=Decimal("100.00"),
                    amount_after=Decimal("100.00"),
                    description="Przelew do DM BOŚ USD",
                )
            ],
        )
        session = Mock()

        with (
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(currency=Currency.PLN, deposit_account_id=deposit_id),
                    ]
                ),
            ),
            patch(
                "app.api.services.brokerage_history_import.create_brokerage_event_and_update_holding",
                new=AsyncMock(),
            ) as create_event_mock,
            patch(
                "app.api.services.brokerage_history_import.create_transactions_rebalance_service",
                new=AsyncMock(),
            ) as create_transactions_mock,
        ):
            with pytest.raises(Exception) as exc_info:
                await import_brokerage_history_service(
                    session=session,
                    user_id=uuid4(),
                    payload=payload,
                )

        assert getattr(exc_info.value, "status_code", None) == 422
        assert "USD" in str(getattr(exc_info.value, "detail", ""))
        create_event_mock.assert_not_called()
        create_transactions_mock.assert_not_called()

    async def test_sell_without_holding_returns_diagnostics_and_skips_cash_transaction(self) -> None:
        brokerage_account_id = uuid4()
        deposit_id = uuid4()
        instrument_id = uuid4()
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=brokerage_account_id,
            rows=[
                BrokerageHistoryImportRow(
                    row_number=246,
                    operation_type="SELL",
                    trade_at=datetime(2021, 12, 23, 10, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("126.90"),
                    amount_after=Decimal("126.90"),
                    description="Rozliczenie transakcji sprzedaży GIGROUP",
                    instrument_symbol="GIGRO",
                    instrument_mic="XWAR",
                    instrument_name="GIGROUP",
                    event_kind=BrokerageEventKind.TRADE_SELL,
                    quantity=Decimal("1269"),
                    price=Decimal("0.10"),
                )
            ],
        )
        session = Mock()

        with (
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(currency=Currency.PLN, deposit_account_id=deposit_id),
                    ]
                ),
            ),
            patch(
                "app.api.services.brokerage_history_import.resolve_stock_instrument",
                new=AsyncMock(return_value=SimpleNamespace(symbol="GIGRO", mic="XWAR")),
            ),
            patch(
                "app.api.services.brokerage_history_import.get_or_create_stock_backed_instrument",
                new=AsyncMock(return_value=SimpleNamespace(id=instrument_id)),
            ),
            patch(
                "app.api.services.brokerage_history_import.get_holding_by_keys",
                new=AsyncMock(return_value=SimpleNamespace(quantity=Decimal("0"))),
            ),
            patch(
                "app.api.services.brokerage_history_import.create_brokerage_event_and_update_holding",
                new=AsyncMock(),
            ) as create_event_mock,
            patch(
                "app.api.services.brokerage_history_import.create_transactions_rebalance_service",
                new=AsyncMock(),
            ) as create_transactions_mock,
        ):
            summary = await import_brokerage_history_service(
                session=session,
                user_id=uuid4(),
                payload=payload,
            )

        assert summary.failed == 1
        assert summary.cash_transactions_created == 0
        row = summary.rows[0]
        assert row.status == "failed"
        assert row.reason_code == "holding_quantity_exceeded"
        assert row.instrument_symbol == "GIGRO"
        assert row.held_quantity == Decimal("0")
        assert row.missing_quantity == Decimal("1269")
        assert "2021-12-23" in (row.message or "")
        create_event_mock.assert_not_called()
        create_transactions_mock.assert_not_called()

    async def test_descending_cash_rows_are_imported_in_balance_chain_order(self) -> None:
        brokerage_account_id = uuid4()
        deposit_id = uuid4()
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=brokerage_account_id,
            rows=[
                BrokerageHistoryImportRow(
                    row_number=2,
                    operation_type="TRANSFER",
                    trade_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("-40.00"),
                    amount_after=Decimal("60.00"),
                    description="Wypłata z rachunku maklerskiego",
                ),
                BrokerageHistoryImportRow(
                    row_number=1,
                    operation_type="TRANSFER",
                    trade_at=datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("100.00"),
                    amount_after=Decimal("100.00"),
                    description="Wpłata na rachunek maklerski",
                ),
            ],
        )
        transaction_ids = [uuid4(), uuid4()]

        with (
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(currency=Currency.PLN, deposit_account_id=deposit_id),
                    ]
                ),
            ),
            patch(
                "app.api.services.brokerage_history_import.find_duplicate_transaction",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.brokerage_history_import.create_transactions_rebalance_service",
                new=AsyncMock(return_value={"created": 2, "transaction_ids": transaction_ids}),
            ) as create_transactions_mock,
        ):
            summary = await import_brokerage_history_service(
                session=Mock(),
                user_id=uuid4(),
                payload=payload,
            )

        assert summary.created == 2
        assert summary.cash_transactions_created == 2
        assert [row.status for row in summary.rows] == ["created", "created"]
        assert [row.transaction_id for row in summary.rows] == transaction_ids
        create_payload = create_transactions_mock.await_args.kwargs["payload"]
        assert create_payload.account_id == deposit_id
        assert [transaction.amount for transaction in create_payload.transactions] == [
            Decimal("100.00"),
            Decimal("-40.00"),
        ]

    async def test_duplicate_cash_row_is_skipped_while_new_cash_row_is_created(self) -> None:
        brokerage_account_id = uuid4()
        deposit_id = uuid4()
        new_transaction_id = uuid4()
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=brokerage_account_id,
            rows=[
                BrokerageHistoryImportRow(
                    row_number=1,
                    operation_type="TRANSFER",
                    trade_at=datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("100.00"),
                    amount_after=Decimal("100.00"),
                    description="Duplikat wpłaty",
                ),
                BrokerageHistoryImportRow(
                    row_number=2,
                    operation_type="TRANSFER",
                    trade_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("25.00"),
                    amount_after=Decimal("125.00"),
                    description="Nowa wpłata",
                ),
            ],
        )

        duplicate = SimpleNamespace(id=uuid4())

        async def duplicate_side_effect(_session, tx_data):
            return duplicate if tx_data.description == "Duplikat wpłaty" else None

        with (
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(currency=Currency.PLN, deposit_account_id=deposit_id),
                    ]
                ),
            ),
            patch(
                "app.api.services.brokerage_history_import.find_duplicate_transaction",
                new=AsyncMock(side_effect=duplicate_side_effect),
            ),
            patch(
                "app.api.services.brokerage_history_import.create_transactions_rebalance_service",
                new=AsyncMock(return_value={"created": 1, "transaction_ids": [new_transaction_id]}),
            ) as create_transactions_mock,
        ):
            summary = await import_brokerage_history_service(
                session=Mock(),
                user_id=uuid4(),
                payload=payload,
            )

        assert summary.created == 1
        assert summary.skipped_duplicates == 1
        assert summary.cash_transactions_created == 1
        assert summary.rows[0].status == "skipped_duplicate"
        assert summary.rows[1].status == "created"
        assert summary.rows[1].transaction_id == new_transaction_id
        create_payload = create_transactions_mock.await_args.kwargs["payload"]
        assert len(create_payload.transactions) == 1
        assert create_payload.transactions[0].description == "Nowa wpłata"

    async def test_bad_cash_balance_chain_returns_422_before_marking_rows_created(self) -> None:
        brokerage_account_id = uuid4()
        deposit_id = uuid4()
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=brokerage_account_id,
            rows=[
                BrokerageHistoryImportRow(
                    row_number=8,
                    operation_type="TRANSFER",
                    trade_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                    currency=Currency.USD,
                    amount=Decimal("50.00"),
                    amount_after=Decimal("999.00"),
                    description="Błędny łańcuch salda USD",
                )
            ],
        )

        with (
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(currency=Currency.USD, deposit_account_id=deposit_id),
                    ]
                ),
            ),
            patch(
                "app.api.services.brokerage_history_import.find_duplicate_transaction",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.brokerage_history_import.create_transactions_rebalance_service",
                new=AsyncMock(side_effect=ImportMismatchError("USD row 8 balance mismatch")),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await import_brokerage_history_service(
                    session=Mock(),
                    user_id=uuid4(),
                    payload=payload,
                )

        assert exc_info.value.status_code == 422
        assert "USD row 8 balance mismatch" in str(exc_info.value.detail)

    async def test_forced_sell_uses_current_holding_quantity_and_cash_settlement(self) -> None:
        brokerage_account_id = uuid4()
        deposit_id = uuid4()
        instrument_id = uuid4()
        event_id = uuid4()
        transaction_id = uuid4()
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=brokerage_account_id,
            rows=[
                BrokerageHistoryImportRow(
                    row_number=44,
                    operation_type="FORCED_SELL",
                    trade_at=datetime(2026, 2, 12, 9, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("125.00"),
                    amount_after=Decimal("125.00"),
                    description="Wykup przymusowy OLDCO",
                    instrument_symbol="OLD",
                    instrument_mic="XWAR",
                    instrument_name="OLDCO",
                )
            ],
        )

        with (
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(currency=Currency.PLN, deposit_account_id=deposit_id),
                    ]
                ),
            ),
            patch(
                "app.api.services.brokerage_history_import.resolve_stock_instrument",
                new=AsyncMock(return_value=SimpleNamespace(symbol="OLD", mic="XWAR")),
            ),
            patch(
                "app.api.services.brokerage_history_import.get_or_create_stock_backed_instrument",
                new=AsyncMock(return_value=SimpleNamespace(id=instrument_id)),
            ),
            patch(
                "app.api.services.brokerage_history_import.get_holding_by_keys",
                new=AsyncMock(return_value=SimpleNamespace(quantity=Decimal("5"))),
            ),
            patch(
                "app.api.services.brokerage_history_import.create_brokerage_event_and_update_holding",
                new=AsyncMock(return_value=(SimpleNamespace(id=event_id), SimpleNamespace())),
            ) as create_event_mock,
            patch(
                "app.api.services.brokerage_history_import.find_duplicate_transaction",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.brokerage_history_import.create_transactions_rebalance_service",
                new=AsyncMock(return_value={"created": 1, "transaction_ids": [transaction_id]}),
            ),
        ):
            summary = await import_brokerage_history_service(
                session=Mock(),
                user_id=uuid4(),
                payload=payload,
            )

        assert summary.created == 1
        assert summary.cash_transactions_created == 1
        row = summary.rows[0]
        assert row.brokerage_event_id == event_id
        assert row.transaction_id == transaction_id
        event_payload = create_event_mock.await_args.args[1]
        assert event_payload.kind == BrokerageEventKind.TRADE_SELL
        assert event_payload.quantity == Decimal("5.00")
        assert event_payload.price == Decimal("25.00")
        assert "Wykup przymusowy" in (event_payload.note or "")

    async def test_forced_sell_without_holding_is_needs_review_without_cash_transaction(self) -> None:
        brokerage_account_id = uuid4()
        deposit_id = uuid4()
        instrument_id = uuid4()
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=brokerage_account_id,
            rows=[
                BrokerageHistoryImportRow(
                    row_number=45,
                    operation_type="FORCED_SELL",
                    trade_at=datetime(2026, 2, 12, 9, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("125.00"),
                    amount_after=Decimal("125.00"),
                    description="Wykup przymusowy MISSING",
                    instrument_symbol="MIS",
                    instrument_mic="XWAR",
                    instrument_name="MISSING",
                )
            ],
        )

        with (
            patch(
                "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(currency=Currency.PLN, deposit_account_id=deposit_id),
                    ]
                ),
            ),
            patch(
                "app.api.services.brokerage_history_import.resolve_stock_instrument",
                new=AsyncMock(return_value=SimpleNamespace(symbol="MIS", mic="XWAR")),
            ),
            patch(
                "app.api.services.brokerage_history_import.get_or_create_stock_backed_instrument",
                new=AsyncMock(return_value=SimpleNamespace(id=instrument_id)),
            ),
            patch(
                "app.api.services.brokerage_history_import.get_holding_by_keys",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.services.brokerage_history_import.create_brokerage_event_and_update_holding",
                new=AsyncMock(),
            ) as create_event_mock,
            patch(
                "app.api.services.brokerage_history_import.create_transactions_rebalance_service",
                new=AsyncMock(),
            ) as create_transactions_mock,
        ):
            summary = await import_brokerage_history_service(
                session=Mock(),
                user_id=uuid4(),
                payload=payload,
            )

        assert summary.created == 0
        assert summary.needs_review == 1
        assert summary.cash_transactions_created == 0
        assert summary.rows[0].status == "needs_review"
        assert "forced buyout" in (summary.rows[0].message or "")
        create_event_mock.assert_not_called()
        create_transactions_mock.assert_not_called()

    async def test_unrecognized_history_row_is_not_silently_marked_created(self) -> None:
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=uuid4(),
            rows=[
                BrokerageHistoryImportRow(
                    row_number=99,
                    operation_type="BROKER_NOTE",
                    trade_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("0.00"),
                    amount_after=Decimal("0.00"),
                    description="Informacja bez skutku gotówkowego",
                )
            ],
        )

        with patch(
            "app.api.services.brokerage_history_import.list_brokerage_deposit_links",
            new=AsyncMock(return_value=[]),
        ):
            summary = await import_brokerage_history_service(
                session=Mock(),
                user_id=uuid4(),
                payload=payload,
            )

        assert summary.created == 0
        assert summary.needs_review == 1
        assert summary.rows[0].status == "needs_review"
        assert "no recognized import action" in (summary.rows[0].message or "")


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Brokerage holding replay rebuilds account state from auditable event history")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "holdings", "financial-data", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies that account-level holding rebuild replays BUY, SELL, SPLIT, "
    "CONVERSION and ADJUSTMENT events into deterministic final quantities and "
    "average costs, while removing stale holdings first."
)
class TestBrokerageHoldingReplay(unittest.IsolatedAsyncioTestCase):
    class _ScalarRows:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return TestBrokerageHoldingReplay._ScalarRows(self._rows)

    def _session_for_rebuild(self, events, existing_holdings=None):
        session = Mock()
        session.execute = AsyncMock(
            side_effect=[
                self._Result(events),
                self._Result(existing_holdings or []),
            ]
        )
        session.delete = AsyncMock()
        session.flush = AsyncMock()
        session.add = Mock()
        return session

    async def test_rebuild_account_holdings_replays_split_conversion_and_adjustment(self) -> None:
        account_id = uuid4()
        source_id = uuid4()
        target_id = uuid4()

        def event(
            *,
            instrument_id,
            kind,
            quantity,
            price,
            split_ratio="0",
            target_instrument_id=None,
            note=None,
            order=0,
        ):
            return SimpleNamespace(
                id=uuid4(),
                brokerage_account_id=account_id,
                instrument_id=instrument_id,
                target_instrument_id=target_instrument_id,
                kind=kind,
                quantity=Decimal(quantity),
                price=Decimal(price),
                split_ratio=Decimal(split_ratio),
                note=note,
                trade_at=datetime(2026, 1, 1, 10, order, tzinfo=timezone.utc),
            )

        events = [
            event(
                instrument_id=source_id,
                kind=BrokerageEventKind.TRADE_BUY,
                quantity="10",
                price="5",
                order=1,
            ),
            event(
                instrument_id=source_id,
                kind=BrokerageEventKind.TRADE_BUY,
                quantity="10",
                price="7",
                order=2,
            ),
            event(
                instrument_id=source_id,
                kind=BrokerageEventKind.TRADE_SELL,
                quantity="5",
                price="9",
                order=3,
            ),
            event(
                instrument_id=source_id,
                kind=BrokerageEventKind.SPLIT,
                quantity="0",
                price="0",
                split_ratio="2",
                order=4,
            ),
            event(
                instrument_id=source_id,
                kind=BrokerageEventKind.CONVERSION,
                quantity="10",
                price="0",
                split_ratio="0.5",
                target_instrument_id=target_id,
                note="WORKSERV -> GIGROUP",
                order=5,
            ),
        ]
        existing_holdings = [
            SimpleNamespace(account_id=account_id, instrument_id=source_id),
            SimpleNamespace(account_id=account_id, instrument_id=target_id),
        ]

        session = self._session_for_rebuild(events, existing_holdings)

        await rebuild_account_holdings_from_events(session=session, account_id=account_id)

        assert session.delete.await_count == 2
        assert session.flush.await_count == 2
        added = [call.args[0] for call in session.add.call_args_list]
        added_by_instrument = {holding.instrument_id: holding for holding in added}
        assert set(added_by_instrument) == {source_id, target_id}
        assert added_by_instrument[source_id].quantity == Decimal("20")
        assert added_by_instrument[source_id].avg_cost == Decimal("3")
        assert added_by_instrument[target_id].quantity == Decimal("5.0")
        assert added_by_instrument[target_id].avg_cost == Decimal("6")

    async def test_rebuild_account_holdings_rejects_oversell_like_live_event_path(self) -> None:
        account_id = uuid4()
        instrument_id = uuid4()
        events = [
            SimpleNamespace(
                id=uuid4(),
                brokerage_account_id=account_id,
                instrument_id=instrument_id,
                target_instrument_id=None,
                instrument_symbol="PKO",
                kind=BrokerageEventKind.TRADE_SELL,
                quantity=Decimal("3"),
                price=Decimal("1"),
                split_ratio=Decimal("0"),
                note=None,
                trade_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            )
        ]
        session = self._session_for_rebuild(events)

        with pytest.raises(HoldingQuantityExceeded) as exc_info:
            await rebuild_account_holdings_from_events(session=session, account_id=account_id)

        assert "Cannot sell 3 PKO" in exc_info.value.detail
        assert session.delete.await_count == 0
        assert session.flush.await_count == 1
        session.add.assert_not_called()

    async def test_rebuild_account_holdings_rejects_conversion_above_source_quantity_like_live_event_path(self) -> None:
        account_id = uuid4()
        source_id = uuid4()
        target_id = uuid4()
        events = [
            SimpleNamespace(
                id=uuid4(),
                brokerage_account_id=account_id,
                instrument_id=source_id,
                target_instrument_id=None,
                instrument_symbol="WORK",
                kind=BrokerageEventKind.TRADE_BUY,
                quantity=Decimal("5"),
                price=Decimal("10"),
                split_ratio=Decimal("0"),
                note=None,
                trade_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=uuid4(),
                brokerage_account_id=account_id,
                instrument_id=source_id,
                target_instrument_id=target_id,
                instrument_symbol="WORK",
                kind=BrokerageEventKind.CONVERSION,
                quantity=Decimal("10"),
                price=Decimal("0"),
                split_ratio=Decimal("1"),
                note="WORK -> GIG",
                trade_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
            ),
        ]
        session = self._session_for_rebuild(events)

        with pytest.raises(HoldingQuantityExceeded) as exc_info:
            await rebuild_account_holdings_from_events(session=session, account_id=account_id)

        assert "Cannot sell 10 WORK" in exc_info.value.detail
        assert session.flush.await_count == 1
        session.add.assert_not_called()
