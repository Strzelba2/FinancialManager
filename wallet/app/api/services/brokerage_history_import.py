from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.services.brokerage_event import (
    create_brokerage_event_and_update_holding,
    get_or_create_stock_backed_instrument,
    resolve_stock_instrument,
)
from app.api.services.transactions import (
    create_transactions_rebalance_service,
    normalize_transaction_rows_order,
)
from app.core.exceptions import DuplicateTransactionError, ImportMismatchError, UnknownAccountError
from app.crud.brokerage_deposit_link_crud import list_brokerage_deposit_links
from app.crud.holding_crud import HoldingQuantityExceeded, get_holding_by_keys
from app.crud.transaction_crud import find_duplicate_transaction
from app.models.enums import BrokerageEventKind, Currency
from app.schemas.response import BrokerageEventsImportSummary
from app.schemas.schemas import (
    BrokerageEventCreate,
    BrokerageHistoryImportRequest,
    BrokerageHistoryImportRow,
    CreateTransactionsRequest,
    TransactionCreate,
    TransactionIn,
)
from app.clients.stock_client import StockClient


_CASH_OPERATION_TYPES = {"BUY", "SELL", "FORCED_SELL", "DIVIDEND", "TRANSFER", "FX"}
_TRADE_OPERATION_TYPES = {"BUY", "SELL", "FORCED_SELL"}


def _money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _price(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"))


def _row_context(row: BrokerageHistoryImportRow) -> dict:
    return {
        "row": row.row_number,
        "instrument_symbol": row.instrument_symbol,
        "instrument_name": row.instrument_name,
        "kind": row.event_kind,
        "trade_at": row.trade_at,
        "currency": row.currency,
        "quantity": row.quantity,
    }


def _order_history_rows(rows: list[BrokerageHistoryImportRow]) -> list[BrokerageHistoryImportRow]:
    if len(rows) <= 1:
        return list(rows)

    is_ascending = all(rows[i].trade_at <= rows[i + 1].trade_at for i in range(len(rows) - 1))
    if is_ascending:
        return list(rows)

    is_descending = all(rows[i].trade_at >= rows[i + 1].trade_at for i in range(len(rows) - 1))
    if is_descending:
        return list(reversed(rows))

    return sorted(rows, key=lambda row: (row.trade_at, row.row_number))


def _is_cash_row(row: BrokerageHistoryImportRow) -> bool:
    return row.operation_type.upper() in _CASH_OPERATION_TYPES


async def _preflight_blocking_rows(
    rows: list[BrokerageHistoryImportRow],
    stock_client: StockClient | None = None,
) -> None:
    errors: list[str] = []
    stock_checks: dict[tuple[str, str], int] = {}

    for row in rows:
        operation_type = row.operation_type.upper()
        if operation_type == "NEEDS_REVIEW":
            reason = row.review_reason or "Row requires manual review."
            errors.append(f"Row {row.row_number}: {reason}")
            continue

        if operation_type in _TRADE_OPERATION_TYPES:
            if not row.instrument_symbol or not row.instrument_mic:
                errors.append(
                    f"Row {row.row_number}: trade row is missing instrument_symbol or instrument_mic."
                )
                continue
            key = (row.instrument_mic.strip().upper(), row.instrument_symbol.strip().upper())
            stock_checks.setdefault(key, row.row_number)

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Blocking BoSSA import rows: " + " | ".join(errors),
        )

    for (mic, symbol), row_number in stock_checks.items():
        try:
            await resolve_stock_instrument(mic, symbol, stock_client=stock_client)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
                errors.append(
                    f"Row {row_number}: {symbol} ({mic}) must be created in stock first."
                )
            else:
                raise

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Blocking BoSSA import rows: " + " | ".join(errors),
        )


async def _find_duplicate_cash_rows(
    session: AsyncSession,
    account_id: uuid.UUID,
    rows: list[tuple[BrokerageHistoryImportRow, TransactionIn]],
) -> set[int]:
    ordered_transactions = normalize_transaction_rows_order([transaction for _, transaction in rows])
    transaction_to_row: dict[int, BrokerageHistoryImportRow] = {
        id(transaction): row for row, transaction in rows
    }
    duplicate_rows: set[int] = set()

    for idx, transaction in enumerate(ordered_transactions):
        row = transaction_to_row[id(transaction)]
        tx_data = TransactionCreate(
            account_id=account_id,
            amount=transaction.amount,
            description=transaction.description,
            balance_before=Decimal("0"),
            balance_after=transaction.amount_after,
            date_transaction=transaction.date + timedelta(microseconds=idx),
        )
        if await find_duplicate_transaction(session, tx_data) is not None:
            duplicate_rows.add(row.row_number)

    return duplicate_rows


async def _build_forced_sell_payload(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    row: BrokerageHistoryImportRow,
    stock_client: StockClient | None = None,
) -> BrokerageEventCreate | None:
    if not row.instrument_symbol or not row.instrument_mic:
        return None

    instrument = await get_or_create_stock_backed_instrument(
        session,
        mic=row.instrument_mic,
        symbol=row.instrument_symbol,
        stock_client=stock_client,
    )
    holding = await get_holding_by_keys(
        session,
        account_id=brokerage_account_id,
        instrument_id=instrument.id,
    )
    if holding is None or Decimal(str(holding.quantity)) <= 0:
        return None

    quantity = _money(holding.quantity)
    price = _price(abs(Decimal(str(row.amount))) / quantity) if quantity else Decimal("0.000")
    return BrokerageEventCreate(
        brokerage_account_id=brokerage_account_id,
        instrument_symbol=row.instrument_symbol,
        instrument_mic=row.instrument_mic,
        instrument_name=row.instrument_name or row.instrument_symbol,
        kind=BrokerageEventKind.TRADE_SELL,
        quantity=quantity,
        price=price,
        currency=row.currency,
        split_ratio=Decimal("0"),
        note=f"Wykup przymusowy: {row.description}",
        trade_at=row.trade_at,
    )


def _build_event_payload(
    brokerage_account_id: uuid.UUID,
    row: BrokerageHistoryImportRow,
) -> BrokerageEventCreate | None:
    if row.event_kind not in (BrokerageEventKind.TRADE_BUY, BrokerageEventKind.TRADE_SELL):
        return None
    if not row.instrument_symbol or not row.instrument_mic or row.quantity is None or row.price is None:
        return None

    return BrokerageEventCreate(
        brokerage_account_id=brokerage_account_id,
        instrument_symbol=row.instrument_symbol,
        instrument_mic=row.instrument_mic,
        instrument_name=row.instrument_name or row.instrument_symbol,
        kind=row.event_kind,
        quantity=row.quantity,
        price=row.price,
        currency=row.currency,
        split_ratio=row.split_ratio or Decimal("0"),
        note=row.description,
        trade_at=row.trade_at,
    )


async def _sell_precheck_context(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    event_payload: BrokerageEventCreate,
    stock_client: StockClient | None = None,
) -> dict | None:
    if event_payload.kind != BrokerageEventKind.TRADE_SELL:
        return None

    instrument = await get_or_create_stock_backed_instrument(
        session,
        mic=event_payload.instrument_mic,
        symbol=event_payload.instrument_symbol,
        stock_client=stock_client,
    )
    holding = await get_holding_by_keys(
        session,
        account_id=brokerage_account_id,
        instrument_id=instrument.id,
    )
    held_quantity = Decimal(str(holding.quantity)) if holding is not None else Decimal("0")
    requested_quantity = Decimal(str(event_payload.quantity))
    if held_quantity >= requested_quantity:
        return None

    exc = HoldingQuantityExceeded(
        payload=event_payload,
        held_quantity=held_quantity,
        requested_quantity=requested_quantity,
    )
    return {"message": f"HTTP {exc.status_code} - {exc.detail}", **exc.context}


async def import_brokerage_history_service(
    session: AsyncSession,
    user_id: uuid.UUID,
    payload: BrokerageHistoryImportRequest,
    stock_client: StockClient | None = None,
) -> BrokerageEventsImportSummary:
    await _preflight_blocking_rows(list(payload.rows), stock_client=stock_client)

    links = await list_brokerage_deposit_links(
        session=session,
        brokerage_account_id=payload.brokerage_account_id,
        limit=10,
    )
    deposit_by_currency = {link.currency: link.deposit_account_id for link in links}

    required_currencies = {
        row.currency for row in payload.rows if _is_cash_row(row)
    }
    missing_currencies = sorted(
        currency.value for currency in required_currencies if currency not in deposit_by_currency
    )
    if missing_currencies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Missing brokerage cash subaccounts for currencies: "
                + ", ".join(missing_currencies)
            ),
        )

    result_by_row: dict[int, dict] = {}
    cash_rows_by_currency: dict[Currency, list[tuple[BrokerageHistoryImportRow, TransactionIn]]] = defaultdict(list)
    errors: list[str] = []

    for row in payload.rows:
        result_by_row[row.row_number] = {
            **_row_context(row),
            "status": "pending",
            "message": None,
        }

    for row in _order_history_rows(list(payload.rows)):
        operation_type = row.operation_type.upper()
        result = result_by_row[row.row_number]

        if operation_type == "NEEDS_REVIEW":
            result["status"] = "needs_review"
            result["message"] = row.review_reason or "Row requires manual review."
            result["reason_code"] = "needs_review"
            continue

        event_payload = None
        if operation_type == "FORCED_SELL":
            event_payload = await _build_forced_sell_payload(
                session=session,
                brokerage_account_id=payload.brokerage_account_id,
                row=row,
                stock_client=stock_client,
            )
            if event_payload is None:
                result["status"] = "needs_review"
                result["message"] = (
                    f"Row {row.row_number}: {row.instrument_symbol or row.instrument_name or 'instrument'} "
                    "requires manual review before forced buyout."
                )
                result["reason_code"] = "needs_review"
                continue
        else:
            event_payload = _build_event_payload(payload.brokerage_account_id, row)

        if event_payload is not None:
            sell_error_context = await _sell_precheck_context(
                session=session,
                brokerage_account_id=payload.brokerage_account_id,
                event_payload=event_payload,
                stock_client=stock_client,
            )
            if sell_error_context is not None:
                message = f"Row {row.row_number}: {sell_error_context['message']}"
                result.update(
                    {
                        "status": "failed",
                        "message": message,
                        **{k: v for k, v in sell_error_context.items() if k != "message"},
                    }
                )
                errors.append(message)
                continue

            try:
                event, _holding = await create_brokerage_event_and_update_holding(
                    session,
                    event_payload,
                    creat_transaction=False,
                    stock_client=stock_client,
                )
                result["brokerage_event_id"] = event.id
            except HoldingQuantityExceeded as exc:
                message = f"Row {row.row_number}: HTTP {exc.status_code} - {exc.detail}"
                result.update(
                    {
                        "status": "failed",
                        "message": message,
                        **exc.context,
                    }
                )
                errors.append(message)
                continue
            except HTTPException as exc:
                if exc.status_code == status.HTTP_409_CONFLICT:
                    result["status"] = "skipped_duplicate"
                    result["message"] = str(exc.detail)
                else:
                    message = f"Row {row.row_number}: HTTP {exc.status_code} - {exc.detail}"
                    result["status"] = "failed"
                    result["message"] = message
                    errors.append(message)
                    continue

        if _is_cash_row(row):
            cash_rows_by_currency[row.currency].append(
                (
                    row,
                    TransactionIn(
                        date=row.trade_at,
                        amount=row.amount,
                        description=row.description,
                        amount_after=row.amount_after,
                        capital_gain_kind=row.capital_gain_kind,
                    ),
                )
            )

    cash_transactions_created = 0
    for currency, rows in cash_rows_by_currency.items():
        account_id = deposit_by_currency[currency]
        duplicate_row_numbers = await _find_duplicate_cash_rows(session, account_id, rows)
        rows_to_import = [
            (row, transaction)
            for row, transaction in rows
            if row.row_number not in duplicate_row_numbers
            and result_by_row[row.row_number]["status"] not in {"failed", "needs_review"}
        ]

        for row_number in duplicate_row_numbers:
            result = result_by_row[row_number]
            if result["status"] == "pending":
                result["status"] = "skipped_duplicate"
                result["message"] = "Cash transaction already exists."

        if not rows_to_import:
            continue

        try:
            transaction_summary = await create_transactions_rebalance_service(
                session=session,
                user_id=user_id,
                payload=CreateTransactionsRequest(
                    account_id=account_id,
                    transactions=[transaction for _, transaction in rows_to_import],
                ),
                verify_amount_after=True,
            )
        except (DuplicateTransactionError, ImportMismatchError, UnknownAccountError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        transaction_ids = transaction_summary.get("transaction_ids", [])
        cash_transactions_created += int(transaction_summary.get("created", 0))
        ordered_transactions = normalize_transaction_rows_order([transaction for _, transaction in rows_to_import])
        transaction_to_row = {id(transaction): row for row, transaction in rows_to_import}

        for transaction, transaction_id in zip(ordered_transactions, transaction_ids):
            row = transaction_to_row[id(transaction)]
            result_by_row[row.row_number]["transaction_id"] = transaction_id

    rows_out = []
    for row in sorted(payload.rows, key=lambda item: item.row_number):
        result = result_by_row[row.row_number]
        if result["status"] == "pending":
            result["status"] = "created"
        elif result["status"] == "skipped_duplicate" and result.get("transaction_id"):
            result["status"] = "created"
        if result["status"] == "created" and not (result.get("brokerage_event_id") or result.get("transaction_id")):
            result["status"] = "needs_review"
            result["message"] = result.get("message") or "Row has no recognized import action."
            result["reason_code"] = "needs_review"
        rows_out.append(result)

    return BrokerageEventsImportSummary(
        total=len(payload.rows),
        created=sum(1 for row in rows_out if row["status"] == "created"),
        cash_transactions_created=cash_transactions_created,
        skipped_duplicates=sum(1 for row in rows_out if row["status"] == "skipped_duplicate"),
        needs_review=sum(1 for row in rows_out if row["status"] == "needs_review"),
        failed=sum(1 for row in rows_out if row["status"] == "failed"),
        errors=errors,
        rows=rows_out,
    )
