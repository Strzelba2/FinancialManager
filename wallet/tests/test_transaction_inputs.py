from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest
from pydantic import ValidationError

from app.api.services.transactions import (
    create_transactions_service,
    create_transactions_rebalance_service,
    normalize_transaction_rows_order,
)
from app.core.exceptions import DuplicateTransactionError, ImportMismatchError, UnknownAccountError
from app.crud.transaction_crud import (
    batch_update_transactions,
    create_transaction_uow,
    delete_transaction_for_user_rebalance,
)
from app.models.enums import AccountType, CapitalGainKind
from app.models.models import DepositAccount, Transaction, Wallet
from app.schemas.response import BatchUpdateTransactionsRequest, TransactionPatchIn
from app.schemas.schemas import CreateTransactionsRequest, TransactionCreate, TransactionIn

pytestmark = pytest.mark.unit


def _tx_row(
    date: datetime,
    amount: str = "10.005",
    amount_after: str = "100.005",
    description: str = "Deterministic transaction",
    capital_gain_kind: CapitalGainKind | None = None,
) -> TransactionIn:
    return TransactionIn(
        date=date,
        amount=Decimal(amount),
        description=description,
        amount_after=Decimal(amount_after),
        capital_gain_kind=capital_gain_kind,
    )


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Transaction input models preserve financial import fields")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("transactions", "money", "financial-data", "validation")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Covers transaction row ordering, decimal precision, capital gain kind, and "
    "category/status partial update normalization before API/component tests exercise "
    "persisted behavior."
)
class TransactionInputTests(unittest.TestCase):
    def test_transaction_in_rounds_money_and_accepts_capital_gain_kind(self) -> None:
        row = _tx_row(
            datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc),
            capital_gain_kind=CapitalGainKind.DEPOSIT_INTEREST,
        )

        self.assertEqual(row.amount, Decimal("10.01"))
        self.assertEqual(row.amount_after, Decimal("100.01"))
        self.assertEqual(row.capital_gain_kind, CapitalGainKind.DEPOSIT_INTEREST)

    def test_transaction_patch_normalizes_empty_optional_text_to_none(self) -> None:
        patch = TransactionPatchIn(
            id="11111111-1111-4111-8111-111111111111",
            description="   ",
            category="   ",
            status="",
        )

        self.assertIsNone(patch.description)
        self.assertIsNone(patch.category)
        self.assertIsNone(patch.status)

    def test_transaction_patch_rejects_empty_patch(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Provide at least one of"):
            TransactionPatchIn(id="11111111-1111-4111-8111-111111111111")

    def test_transaction_batch_patch_rejects_financial_fields(self) -> None:
        for field in ("amount", "balance_before", "balance_after"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValidationError, "Extra inputs are not permitted"):
                    TransactionPatchIn(
                        id="11111111-1111-4111-8111-111111111111",
                        **{field: "-1.00"},
                    )

    def test_import_order_keeps_ascending_rows_as_is(self) -> None:
        first = _tx_row(datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc), description="first")
        second = _tx_row(datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc), description="second")

        result = normalize_transaction_rows_order([first, second])

        self.assertEqual([row.description for row in result], ["first", "second"])

    def test_import_order_reverses_descending_rows(self) -> None:
        newer = _tx_row(datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc), description="newer")
        older = _tx_row(datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc), description="older")

        result = normalize_transaction_rows_order([newer, older])

        self.assertEqual([row.description for row in result], ["older", "newer"])

    def test_import_order_reverses_descending_date_groups_without_reordering_same_day_items(self) -> None:
        newer_principal = _tx_row(
            datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc),
            amount="100.00",
            amount_after="110.00",
            description="newer-principal",
        )
        newer_interest = _tx_row(
            datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc),
            amount="10.00",
            amount_after="120.00",
            description="newer-interest",
        )
        older_principal = _tx_row(
            datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
            amount="50.00",
            amount_after="50.00",
            description="older-principal",
        )
        older_interest = _tx_row(
            datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
            amount="5.00",
            amount_after="55.00",
            description="older-interest",
        )

        result = normalize_transaction_rows_order([newer_principal, newer_interest, older_principal, older_interest])

        self.assertEqual(
            [row.description for row in result],
            ["older-principal", "older-interest", "newer-principal", "newer-interest"],
        )

    def test_import_order_uses_balance_chain_inside_same_day_groups(self) -> None:
        same_date = datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc)
        next_day = datetime(2026, 5, 3, 0, 0, tzinfo=timezone.utc)
        withdrawal = _tx_row(
            same_date,
            amount="-110.00",
            amount_after="10.00",
            description="same-day-withdrawal",
        )
        principal = _tx_row(
            same_date,
            amount="100.00",
            amount_after="100.00",
            description="same-day-principal",
        )
        interest = _tx_row(
            same_date,
            amount="20.00",
            amount_after="120.00",
            description="same-day-interest",
            capital_gain_kind=CapitalGainKind.DEPOSIT_INTEREST,
        )
        later = _tx_row(
            next_day,
            amount="10.00",
            amount_after="20.00",
            description="later",
        )

        result = normalize_transaction_rows_order([later, withdrawal, principal, interest])

        self.assertEqual(
            [row.description for row in result],
            ["same-day-principal", "same-day-interest", "same-day-withdrawal", "later"],
        )

    def test_import_order_uses_balance_chain_for_credit_card_negative_balances(self) -> None:
        same_booking_date = datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc)
        later_statement_row = _tx_row(
            same_booking_date,
            amount="-39.69",
            amount_after="-780.61",
            description="credit-card-later-row",
        )
        earlier_statement_row = _tx_row(
            same_booking_date,
            amount="-20.31",
            amount_after="-740.92",
            description="credit-card-earlier-row",
        )

        result = normalize_transaction_rows_order([later_statement_row, earlier_statement_row])

        self.assertEqual(
            [row.description for row in result],
            ["credit-card-earlier-row", "credit-card-later-row"],
        )

    def test_import_order_backtracks_when_same_day_balance_values_repeat(self) -> None:
        same_date = datetime(2025, 6, 12, 0, 0, tzinfo=timezone.utc)
        latest_withdrawal = _tx_row(
            same_date,
            amount="-2500.00",
            amount_after="1999.41",
            description="latest-withdrawal",
        )
        middle_withdrawal = _tx_row(
            same_date,
            amount="-1500.00",
            amount_after="4499.41",
            description="middle-withdrawal",
        )
        middle_income = _tx_row(
            same_date,
            amount="1500.00",
            amount_after="5999.41",
            description="middle-income",
        )
        earliest_income = _tx_row(
            same_date,
            amount="3500.00",
            amount_after="4499.41",
            description="earliest-income",
        )

        result = normalize_transaction_rows_order([
            latest_withdrawal,
            middle_withdrawal,
            middle_income,
            earliest_income,
        ])

        self.assertEqual(
            [row.description for row in result],
            ["earliest-income", "middle-income", "middle-withdrawal", "latest-withdrawal"],
        )

    def test_import_order_prefers_bottom_to_top_source_order_for_descending_same_day_balance_loop(self) -> None:
        older_date = datetime(2025, 11, 20, 0, 0, tzinfo=timezone.utc)
        same_date = datetime(2025, 11, 23, 0, 0, tzinfo=timezone.utc)
        newer_date = datetime(2025, 11, 25, 0, 0, tzinfo=timezone.utc)
        newer = _tx_row(
            newer_date,
            amount="5.00",
            amount_after="639.79",
            description="newer-row",
        )
        return_later = _tx_row(
            same_date,
            amount="-98000.00",
            amount_after="634.79",
            description="return-later",
        )
        return_earlier = _tx_row(
            same_date,
            amount="98000.00",
            amount_after="98634.79",
            description="return-earlier",
        )
        second_withdrawal = _tx_row(
            same_date,
            amount="-50000.00",
            amount_after="634.79",
            description="second-withdrawal",
        )
        first_withdrawal = _tx_row(
            same_date,
            amount="-50000.00",
            amount_after="50634.79",
            description="first-withdrawal",
        )
        deposit = _tx_row(
            same_date,
            amount="100000.00",
            amount_after="100634.79",
            description="deposit",
        )
        older = _tx_row(
            older_date,
            amount="10.00",
            amount_after="634.79",
            description="older-row",
        )

        result = normalize_transaction_rows_order([
            newer,
            return_later,
            return_earlier,
            second_withdrawal,
            first_withdrawal,
            deposit,
            older,
        ])

        self.assertEqual(
            [row.description for row in result],
            [
                "older-row",
                "deposit",
                "first-withdrawal",
                "second-withdrawal",
                "return-earlier",
                "return-later",
                "newer-row",
            ],
        )

    def test_import_order_stably_sorts_mixed_rows_without_reordering_same_day_items(self) -> None:
        later = _tx_row(datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc), description="later")
        same_day_first = _tx_row(datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc), description="same-day-first")
        middle = _tx_row(datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc), description="middle")
        same_day_second = _tx_row(datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc), description="same-day-second")

        result = normalize_transaction_rows_order([later, same_day_first, middle, same_day_second])

        self.assertEqual(
            [row.description for row in result],
            ["same-day-first", "same-day-second", "middle", "later"],
        )

    def test_import_order_returns_group_unchanged_when_any_amount_after_is_missing(self) -> None:
        same_date = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        row_with = _tx_row(same_date, amount="100.00", amount_after="200.00", description="has-after")
        row_without = TransactionIn(
            date=same_date, amount=Decimal("50.00"), description="no-after"
        )

        result = normalize_transaction_rows_order([row_without, row_with])

        # Guard fires when any row lacks amount_after: group returned in original order
        self.assertEqual([r.description for r in result], ["no-after", "has-after"])

    def test_import_order_falls_back_to_source_when_balance_chain_is_disconnected(self) -> None:
        same_date = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        # row_a.before=100, row_b.before=949 — neither links to the other's after-value
        row_a = _tx_row(same_date, amount="100.00", amount_after="200.00", description="disconnected-a")
        row_b = _tx_row(same_date, amount="50.00", amount_after="999.00", description="disconnected-b")

        result = normalize_transaction_rows_order([row_a, row_b])

        # No valid complete chain → falls back to source order
        self.assertEqual([r.description for r in result], ["disconnected-a", "disconnected-b"])

    def test_import_order_threads_opening_balance_to_resolve_loop_across_days(self) -> None:
        day1 = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 6, 2, 0, 0, tzinfo=timezone.utc)
        row_day1 = _tx_row(day1, amount="100.00", amount_after="100.00", description="day1")
        # Day 2: loop — all before-values are in after-values, no natural start node
        # Opening balance 100 from day1 breaks the tie and picks row_a as the start
        row_a = _tx_row(day2, amount="-50.00", amount_after="50.00", description="day2-a")
        row_b = _tx_row(day2, amount="50.00", amount_after="100.00", description="day2-b")
        row_c = _tx_row(day2, amount="100.00", amount_after="200.00", description="day2-c")

        result = normalize_transaction_rows_order([row_c, row_b, row_a, row_day1])

        self.assertEqual(
            [r.description for r in result],
            ["day1", "day2-a", "day2-b", "day2-c"],
        )


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Transaction unit of work accepts omitted optional classification fields")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("transactions", "money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TransactionCrudUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_transaction_uow_accepts_missing_category_and_status_as_none(self) -> None:
        session = Mock()
        session.add = Mock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        data = TransactionCreate(
            account_id=uuid4(),
            amount=Decimal("12.34"),
            description="Unit of work transaction",
            balance_before=Decimal("0.00"),
            balance_after=Decimal("12.34"),
            date_transaction=datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc),
        )

        tx = await create_transaction_uow(session, data)

        self.assertIsNone(tx.category)
        self.assertIsNone(tx.status)
        self.assertEqual(tx.description, "Unit of work transaction")
        session.add.assert_called_once_with(tx)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(tx)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Transaction rebalance service reports missing accounts with the account error contract")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("transactions", "money", "financial-data", "validation")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TransactionServiceUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_transactions_rebalance_raises_unknown_account_for_missing_account(self) -> None:
        session = Mock()
        account_id = uuid4()
        user_id = uuid4()
        payload = CreateTransactionsRequest(
            account_id=account_id,
            transactions=[_tx_row(datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc))],
        )

        with (
            patch("app.api.services.transactions.get_deposit_account", new=AsyncMock(return_value=None)) as get_account,
            patch(
                "app.api.services.transactions.get_deposit_account_for_user_for_update",
                new=AsyncMock(),
            ) as get_account_for_user,
        ):
            with self.assertRaisesRegex(UnknownAccountError, "Unknown account_id"):
                await create_transactions_rebalance_service(session, user_id, payload)

        get_account.assert_awaited_once_with(session, account_id)
        get_account_for_user.assert_not_awaited()

    async def test_create_transactions_rebalance_checks_duplicate_before_allocating_unique_datetime(self) -> None:
        session = Mock()
        account_id = uuid4()
        user_id = uuid4()
        account = Mock(id=account_id, account_type=AccountType.CURRENT, currency="PLN")
        balance = Mock(available=Decimal("0.00"))
        payload = CreateTransactionsRequest(
            account_id=account_id,
            transactions=[
                _tx_row(
                    datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc),
                    amount="10.00",
                    amount_after="10.00",
                    description="Replay-protected import",
                )
            ],
        )

        with (
            patch("app.api.services.transactions.get_deposit_account", new=AsyncMock(return_value=account)),
            patch(
                "app.api.services.transactions.get_deposit_account_for_user_for_update",
                new=AsyncMock(return_value=account),
            ),
            patch(
                "app.api.services.transactions.get_or_create_balance_for_update",
                new=AsyncMock(return_value=balance),
            ),
            patch("app.api.services.transactions.get_prev_tx_for_update", new=AsyncMock(return_value=None)),
            patch("app.api.services.transactions.list_chain_from_dt_for_update", new=AsyncMock(return_value=[])),
            patch(
                "app.api.services.transactions.find_duplicate_transaction",
                new=AsyncMock(return_value=Mock()),
            ) as find_duplicate,
            patch("app.api.services.transactions.ensure_unique_dt", new=AsyncMock()) as ensure_unique,
            patch("app.api.services.transactions.create_transaction_uow", new=AsyncMock()) as create_transaction,
        ):
            with self.assertRaisesRegex(DuplicateTransactionError, "Duplicate transaction"):
                await create_transactions_rebalance_service(session, user_id, payload)

        find_duplicate.assert_awaited_once()
        ensure_unique.assert_not_awaited()
        create_transaction.assert_not_awaited()

    async def test_create_transactions_rebalance_allocates_unique_datetime_after_duplicate_check(self) -> None:
        session = Mock()
        account_id = uuid4()
        user_id = uuid4()
        account = Mock(id=account_id, account_type=AccountType.CURRENT, currency="PLN")
        balance = Mock(available=Decimal("0.00"))
        transaction_dt = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
        unique_dt = datetime(2026, 5, 25, 12, 0, 0, 1, tzinfo=timezone.utc)
        events: list[str] = []
        payload = CreateTransactionsRequest(
            account_id=account_id,
            transactions=[
                _tx_row(
                    transaction_dt,
                    amount="10.00",
                    amount_after="10.00",
                    description="Unique import",
                )
            ],
        )

        async def find_duplicate(*args, **kwargs):
            events.append("find_duplicate")
            return None

        async def ensure_unique(*args, **kwargs):
            events.append("ensure_unique")
            return unique_dt

        async def create_transaction(*args, **kwargs):
            events.append("create_transaction")
            raise RuntimeError("stop after create call")

        with (
            patch("app.api.services.transactions.get_deposit_account", new=AsyncMock(return_value=account)),
            patch(
                "app.api.services.transactions.get_deposit_account_for_user_for_update",
                new=AsyncMock(return_value=account),
            ),
            patch(
                "app.api.services.transactions.get_or_create_balance_for_update",
                new=AsyncMock(return_value=balance),
            ),
            patch("app.api.services.transactions.get_prev_tx_for_update", new=AsyncMock(return_value=None)),
            patch("app.api.services.transactions.list_chain_from_dt_for_update", new=AsyncMock(return_value=[])),
            patch("app.api.services.transactions.find_duplicate_transaction", new=AsyncMock(side_effect=find_duplicate)),
            patch("app.api.services.transactions.ensure_unique_dt", new=AsyncMock(side_effect=ensure_unique)),
            patch("app.api.services.transactions.create_transaction_uow", new=AsyncMock(side_effect=create_transaction)),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop after create call"):
                await create_transactions_rebalance_service(session, user_id, payload)

        self.assertEqual(events, ["find_duplicate", "ensure_unique", "create_transaction"])


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Transaction batch update clears nullable classification fields")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("transactions", "money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TransactionBatchUpdateUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_update_transactions_clears_explicit_null_category_and_status(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        account_id = uuid4()
        tx_id = uuid4()
        tx = Mock(account_id=account_id, category="FOOD", status="EXPENSE")
        account = Mock(wallet_id=wallet_id)
        wallet = Mock(user_id=user_id)
        session = Mock()
        session.commit = AsyncMock()

        async def get_model(model, key):
            if model is Transaction and key == tx_id:
                return tx
            if model is DepositAccount and key == account_id:
                return account
            if model is Wallet and key == wallet_id:
                return wallet
            return None

        session.get = AsyncMock(side_effect=get_model)
        request = BatchUpdateTransactionsRequest(
            items=[
                TransactionPatchIn(
                    id=tx_id,
                    category=None,
                    status=None,
                )
            ]
        )

        response = await batch_update_transactions(session, user_id, request)

        self.assertEqual(response.updated, 1)
        self.assertIsNone(tx.category)
        self.assertIsNone(tx.status)
        session.commit.assert_awaited_once()


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("create_transactions_service enforces balance rules and detects duplicates")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("transactions", "money", "financial-data", "validation")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Unit-tests the non-rebalance transaction import service: balance mismatch raises "
    "ImportMismatchError when verify_amount_after=True; CREDIT accounts are allowed to "
    "carry a negative balance; duplicate detection raises ValueError."
)
class TransactionCreateServiceUnitTests(unittest.IsolatedAsyncioTestCase):
    def _make_session(self) -> Mock:
        session = Mock()
        session.add = Mock()
        session.flush = AsyncMock()
        return session

    def _make_account(self, account_type: AccountType = AccountType.CURRENT) -> Mock:
        account = Mock()
        account.id = uuid4()
        account.account_type = account_type
        account.currency = "PLN"
        return account

    def _make_balance(self, available: str = "100.00") -> Mock:
        bal = Mock()
        bal.available = Decimal(available)
        return bal

    async def test_create_transactions_service_raises_mismatch_when_amount_after_is_wrong(self) -> None:
        account = self._make_account()
        balance = self._make_balance("100.00")
        session = self._make_session()
        payload = CreateTransactionsRequest(
            account_id=account.id,
            transactions=[
                _tx_row(
                    datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
                    amount="5.00",
                    amount_after="99.00",
                    description="Mismatch transaction",
                )
            ],
        )

        with (
            patch("app.api.services.transactions.get_deposit_account", new=AsyncMock(return_value=account)),
            patch("app.api.services.transactions.get_deposit_account_balance", new=AsyncMock(return_value=balance)),
            patch("app.api.services.transactions.account_has_transactions", new=AsyncMock(return_value=True)),
        ):
            with self.assertRaisesRegex(ImportMismatchError, "nie zgadza się"):
                await create_transactions_service(session, payload, verify_amount_after=True)

    async def test_create_transactions_service_allows_credit_account_to_go_negative(self) -> None:
        account = self._make_account(account_type=AccountType.CREDIT)
        balance = self._make_balance("50.00")
        session = self._make_session()
        tx_mock = Mock()
        tx_mock.id = uuid4()
        tx_mock.date_transaction = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
        payload = CreateTransactionsRequest(
            account_id=account.id,
            transactions=[
                _tx_row(
                    datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
                    amount="-200.00",
                    amount_after="-150.00",
                    description="Credit card purchase",
                )
            ],
        )

        with (
            patch("app.api.services.transactions.get_deposit_account", new=AsyncMock(return_value=account)),
            patch("app.api.services.transactions.get_deposit_account_balance", new=AsyncMock(return_value=balance)),
            patch("app.api.services.transactions.account_has_transactions", new=AsyncMock(return_value=True)),
            patch("app.api.services.transactions.find_duplicate_transaction", new=AsyncMock(return_value=None)),
            patch("app.api.services.transactions.create_transaction_uow", new=AsyncMock(return_value=tx_mock)),
        ):
            result = await create_transactions_service(session, payload, verify_amount_after=False)

        self.assertEqual(result["created"], 1)
        self.assertEqual(Decimal(str(result["final_balance"])), Decimal("-150.00"))

    async def test_create_transactions_service_raises_value_error_on_duplicate(self) -> None:
        account = self._make_account()
        balance = self._make_balance("100.00")
        session = self._make_session()
        payload = CreateTransactionsRequest(
            account_id=account.id,
            transactions=[
                _tx_row(
                    datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
                    amount="20.00",
                    amount_after="120.00",
                    description="Duplicate transaction",
                )
            ],
        )

        with (
            patch("app.api.services.transactions.get_deposit_account", new=AsyncMock(return_value=account)),
            patch("app.api.services.transactions.get_deposit_account_balance", new=AsyncMock(return_value=balance)),
            patch("app.api.services.transactions.account_has_transactions", new=AsyncMock(return_value=True)),
            patch("app.api.services.transactions.find_duplicate_transaction", new=AsyncMock(return_value=Mock())),
        ):
            with self.assertRaisesRegex(ValueError, "Duplicate transaction"):
                await create_transactions_service(session, payload, verify_amount_after=False)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("delete_transaction_for_user_rebalance raises domain exception for negative balance")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("transactions", "money", "financial-data", "validation")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies that the CRUD layer raises ImportMismatchError (not HTTPException) when "
    "deleting a transaction from a CURRENT account would make the rebalanced chain "
    "go negative. The route handler is responsible for translating this to HTTP 400."
)
class TransactionDeleteCrudUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_raises_import_mismatch_error_when_chain_would_go_negative(self) -> None:
        user_id = uuid4()
        acc_id = uuid4()
        tx_id = uuid4()

        tx = Mock()
        tx.id = tx_id
        tx.account_id = acc_id
        tx.date_transaction = datetime(2026, 7, 1, tzinfo=timezone.utc)
        tx.balance_before = Decimal("100.00")
        tx.amount = Decimal("50.00")

        later_tx = Mock()
        later_tx.amount = Decimal("-120.00")

        bal = Mock()
        bal.available = Decimal("30.00")

        scalars_result = Mock()
        scalars_result.all = Mock(return_value=[later_tx])

        session = Mock()
        session.scalar = AsyncMock(side_effect=[
            tx,                  # ownership check
            AccountType.CURRENT, # account type
            bal,                 # balance row
            None,                # prev tx (none — tx is first)
        ])
        session.scalars = AsyncMock(return_value=scalars_result)
        session.execute = AsyncMock()
        session.delete = AsyncMock()
        session.flush = AsyncMock()
        session.add = Mock()

        with self.assertRaises(ImportMismatchError):
            await delete_transaction_for_user_rebalance(session, user_id, tx_id)
