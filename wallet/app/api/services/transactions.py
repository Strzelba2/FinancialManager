from sqlmodel.ext.asyncio.session import AsyncSession
from decimal import Decimal
from datetime import timedelta
from typing import Tuple, Dict
import uuid
import logging

from app.schemas.schemas import (
    CreateTransactionsRequest, TransactionIn, TransactionCreate,
    CapitalGainCreate
)
from app.models.enums import CapitalGainKind, Currency
from app.crud.deposit_account_crud import get_deposit_account, get_deposit_account_for_user_for_update
from app.crud.deposit_account_balance import get_deposit_account_balance, get_or_create_balance_for_update
from app.crud.capital_gain_crud import create_capital_gain
from app.core.exceptions import (
    ImportMismatchError, UnknownAccountError, UnknownUserError, DuplicateTransactionError
)
from app.utils.money import account_type_allows_negative_balance
from app.crud.transaction_crud import (
    create_transaction_uow, account_has_transactions, find_duplicate_transaction,
    sum_income_expense_for_wallet_year, list_chain_from_dt_for_update, tx_datetime_exists,
    get_prev_tx_for_update
    )

logger = logging.getLogger(__name__)


def _money_key(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _order_same_datetime_group_by_balance_chain(
    rows: list[TransactionIn],
    opening_balance: Decimal | None = None,
    prefer_reversed_source_order: bool = False,
) -> list[TransactionIn]:
    if len(rows) <= 1 or any(row.amount_after is None for row in rows):
        return list(rows)

    nodes: list[tuple[int, Decimal, Decimal]] = []
    for idx, row in enumerate(rows):
        after = _money_key(Decimal(row.amount_after))
        before = _money_key(after - Decimal(row.amount))
        nodes.append((idx, before, after))

    before_by_idx = {idx: before for idx, before, _ in nodes}
    after_by_idx = {idx: after for idx, _, after in nodes}

    if opening_balance is not None:
        opening = _money_key(opening_balance)
        start_nodes = [node for node in nodes if node[1] == opening]
    else:
        after_values = {after for _, _, after in nodes}
        start_nodes = [node for node in nodes if node[1] not in after_values]

    preferred_indexes = (
        list(reversed(range(len(rows))))
        if prefer_reversed_source_order
        else list(range(len(rows)))
    )
    preferred_position = {idx: position for position, idx in enumerate(preferred_indexes)}
    start_nodes = sorted(start_nodes, key=lambda node: preferred_position[node[0]])
    solution: list[int] | None = None

    def walk(current_idx: int, used: set[int], ordered: list[int]) -> None:
        nonlocal solution
        if solution is not None:
            return
        if len(ordered) == len(rows):
            solution = list(ordered)
            return

        current_after = after_by_idx[current_idx]
        candidates = sorted(
            [
                idx
                for idx in range(len(rows))
                if idx not in used and before_by_idx[idx] == current_after
            ],
            key=lambda idx: preferred_position[idx],
        )

        for candidate_idx in candidates:
            used.add(candidate_idx)
            ordered.append(candidate_idx)
            walk(candidate_idx, used, ordered)
            ordered.pop()
            used.remove(candidate_idx)

    for start_idx, _, _ in start_nodes:
        walk(start_idx, {start_idx}, [start_idx])
        if solution is not None:
            return [rows[idx] for idx in solution]

    return list(rows)


def _group_consecutive_rows_by_datetime(rows: list[TransactionIn]) -> list[list[TransactionIn]]:
    groups: list[list[TransactionIn]] = []
    for row in rows:
        if not groups or groups[-1][0].date != row.date:
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups


def _flatten_ordered_datetime_groups(
    groups: list[list[TransactionIn]],
    prefer_reversed_source_order: bool = False,
) -> list[TransactionIn]:
    ordered_rows: list[TransactionIn] = []
    opening_balance: Decimal | None = None

    for group in groups:
        ordered_group = _order_same_datetime_group_by_balance_chain(
            group,
            opening_balance,
            prefer_reversed_source_order,
        )
        ordered_rows.extend(ordered_group)
        if ordered_group and ordered_group[-1].amount_after is not None:
            opening_balance = _money_key(Decimal(ordered_group[-1].amount_after))
        else:
            opening_balance = None

    return ordered_rows


def normalize_transaction_rows_order(rows: list[TransactionIn]) -> list[TransactionIn]:
    """
    Normalize imported transaction order without destroying same-day sequencing.

    Some bank exports arrive in reverse chronological order (newest -> oldest).
    Rows that share the same timestamp can also be reversed relative to their
    balance chain, so same-timestamp groups are ordered by amount_after linkage.
    When the balance chain contains a same-day loop and more than one valid path
    exists, the source order breaks the tie: ascending imports prefer top-to-bottom
    order, descending imports prefer bottom-to-top order inside the day.

    We therefore:
    - keep already-ascending rows as-is
    - reverse fully descending rows
    - fall back to stable sorting by date only for mixed/irregular input
    """
    if len(rows) <= 1:
        return list(rows)

    is_ascending = all(rows[i].date <= rows[i + 1].date for i in range(len(rows) - 1))
    if is_ascending:
        return _flatten_ordered_datetime_groups(_group_consecutive_rows_by_datetime(rows))

    is_descending = all(rows[i].date >= rows[i + 1].date for i in range(len(rows) - 1))
    if is_descending:
        groups = _group_consecutive_rows_by_datetime(rows)
        return _flatten_ordered_datetime_groups(
            list(reversed(groups)),
            prefer_reversed_source_order=True,
        )

    logger.warning("normalize_transaction_rows_order: mixed import order detected; applying stable date sort")
    sorted_rows = sorted(rows, key=lambda r: r.date)
    return _flatten_ordered_datetime_groups(_group_consecutive_rows_by_datetime(sorted_rows))


async def create_transactions_service(
    session: AsyncSession,
    payload: CreateTransactionsRequest,
    verify_amount_after: bool = False, 
    return_tr: bool = False   
) -> dict:
    """
    Imports multiple transactions into a deposit account and updates the available balance.

    Args:
        session (AsyncSession): SQLAlchemy database session.
        payload (CreateTransactionsRequest): Contains account ID and transaction rows.
        verify_amount_after (bool, optional): If True, verifies provided balance_after values.
                                              Raises `ImportMismatchError` on mismatch.

    Returns:
        dict: Summary of the operation including:
              - number of created transactions
              - final balance
              - account ID

    Raises:
        ValueError: If account is not found.
        ImportMismatchError: If balance_after mismatch is detected when `verify_amount_after` is True.
    """
    logger.info(f"Creating transactions for account: {payload.account_id}")
    
    account = await get_deposit_account(session, payload.account_id)
    if not account:
        logger.error("Unknown account_id provided")
        raise ValueError("Unknown account_id")
    
    rows: list[TransactionIn] = normalize_transaction_rows_order(list(payload.transactions))

    bal = await get_deposit_account_balance(session, account.id)
    
    has_tx = await account_has_transactions(session, payload.account_id)
    
    if not has_tx:
        first = rows[0]
        if first.amount_after is not None:
            last_balance = Decimal(first.amount_after) - Decimal(first.amount)
        else:

            last_balance = Decimal(bal.available or 0)

    else:
        last_balance = Decimal(bal.available or 0)
    
    created = 0
    transaction_ids: list[uuid.UUID] = []
    for i, r in enumerate(rows, start=0):
        amount = Decimal(r.amount)
        before = last_balance

        logger.debug(f"Processing transaction {i}: amount={amount} before={before}")

        computed_after = before + amount
        if r.amount_after is not None:
            provided_after = Decimal(r.amount_after)
            if verify_amount_after and provided_after != computed_after:
                raise ImportMismatchError(f"Saldo po operacji w dniu {r.date} nie zgadza się: {provided_after} != {computed_after}")
            after = provided_after
        else:
            after = computed_after

        if after < 0 and not account_type_allows_negative_balance(account.account_type):
            logger.info("create_transactions_service would go negative")
            raise ImportMismatchError("This insert would make the account balance negative.")

        tx_data = TransactionCreate(
            account_id=payload.account_id,
            amount=amount,
            description=r.description,
            balance_before=before,
            balance_after=after,
            date_transaction=r.date + timedelta(seconds=i)
        )
        
        dup = await find_duplicate_transaction(session, tx_data)
        if dup is not None:
            raise ValueError(
                f"Duplicate transaction detected for "
                f"account={payload.account_id}, "
                f"date={tx_data.date_transaction}, "
                f"amount={tx_data.amount}, "
                f"description={tx_data.description!r}"
            )

        tx = await create_transaction_uow(session, tx_data)
        
        transaction_ids.append(tx.id)
        created += 1
        last_balance = after

        bal.available = last_balance
        session.add(bal)
        await session.flush()
        
        if r.capital_gain_kind in (
            CapitalGainKind.DEPOSIT_INTEREST,
            CapitalGainKind.BROKER_DIVIDEND,
        ) and amount != 0:
            cg_data = CapitalGainCreate(
                deposit_account_id=payload.account_id,
                transaction_id=tx.id,
                kind=r.capital_gain_kind,
                amount=amount,                
                currency=account.currency,  
                occurred_at=tx.date_transaction,
                tax_year=tx.date_transaction.year,
            )
            await create_capital_gain(session, cg_data)

    logger.info(f"{created} transactions created for account {account.id}")
    
    if return_tr:
        return {
            "created": created,
            "final_balance": last_balance,
            "account_id": str(account.id),
            "transaction_ids": [str(tid) for tid in transaction_ids],
        }
        
    return {
        "created": created, 
        "final_balance": last_balance, 
        "account_id": str(account.id)
        }
   
    
async def ensure_unique_dt(
    session: AsyncSession,
    account_id: uuid.UUID,
    dt,
    max_bumps: int = 2000,
):
    """
    Ensure a unique transaction datetime for a given account by bumping microseconds.

    This helper checks whether a transaction already exists for (account_id, dt).
    If it does, it increments dt by 1 microsecond until it finds a free timestamp.

    Args:
        session: SQLAlchemy async database session.
        account_id: Deposit account UUID.
        dt: Base datetime to test for uniqueness.
        max_bumps: Maximum number of 1-microsecond bumps before failing.

    Returns:
        A datetime value that is unique for the given account.

    Raises:
        DuplicateTransactionError: If a unique datetime cannot be found within `max_bumps`.
    """
    cur = dt
    for _ in range(max_bumps):
        if not await tx_datetime_exists(session, account_id=account_id, dt=cur):
            return cur
        cur = cur + timedelta(microseconds=1)
    logger.warning(
        f"ensure_unique_dt failed account_id={account_id} base_dt={dt.isoformat()} max_bumps={max_bumps}"
    )
    raise DuplicateTransactionError("Too many transactions share the same timestamp.")
    
    
async def create_transactions_rebalance_service(
    session: AsyncSession,
    user_id: uuid.UUID,
    payload: CreateTransactionsRequest,
    verify_amount_after: bool = False,
) -> dict:
    """
    Create a list of transactions and rebalance the balance chain from the first inserted datetime.

    High-level steps:
      1) Validate account exists and belongs to the user (FOR UPDATE).
      2) Lock/create balance row (FOR UPDATE).
      3) Insert transactions (ensuring unique timestamps).
      4) Recompute the chain balances starting from dt_start.
      5) Update account balance row to the final running value.

    Args:
        session: SQLAlchemy async database session (should be inside a transaction).
        user_id: Internal user UUID.
        payload: Input with `account_id` and `transactions`.
        verify_amount_after: If True, validate provided `amount_after` against computed value.

    Returns:
        Dict with:
            - created: int
            - final_balance: Decimal
            - account_id: str
            - transaction_ids: list[str]
            - rebalanced_count: int

    Raises:
        UnknownUserError: If the user is unknown (depending on your user/account validation rules).
        UnknownAccountError: If the account is unknown or not owned by the user.
        DuplicateTransactionError: If a duplicate transaction is detected.
        ImportMismatchError: If balance checks fail (e.g., mismatch or negative balance).
    """
    account = await get_deposit_account(session, payload.account_id)
    if not account:
        logger.info(
            f"create_transactions_rebalance_service account not found account_id={payload.account_id} user_id={user_id}"
        )
        raise UnknownAccountError("Unknown account_id")

    acc_id = uuid.UUID(str(payload.account_id))

    account = await get_deposit_account_for_user_for_update(
        session, user_id=user_id, account_id=acc_id
    )
    if account is None:
        raise UnknownAccountError("Unknown account_id")

    bal = await get_or_create_balance_for_update(session, account_id=acc_id)

    if not payload.transactions:
        return {"created": 0, "final_balance": Decimal(str(bal.available or 0)), "account_id": str(acc_id)}

    rows = normalize_transaction_rows_order(list(payload.transactions))
    allows_negative_balance = account_type_allows_negative_balance(account.account_type)

    dt_start = rows[0].date

    prev = await get_prev_tx_for_update(session, account_id=acc_id, dt=dt_start)
    existing_chain = await list_chain_from_dt_for_update(session, account_id=acc_id, dt=dt_start)

    if prev is not None:
        baseline_running = Decimal(str(prev.balance_after))
    elif existing_chain:
        baseline_running = Decimal(str(existing_chain[0].balance_before))
    else:
        baseline_running = Decimal(str(bal.available or 0))

    created = 0
    inserted_ids: list[uuid.UUID] = []
    running = baseline_running

    for idx, r in enumerate(rows):
        amount = Decimal(str(r.amount))
        before = running
        computed_after = before + amount

        if getattr(r, "amount_after", None) is not None:
            provided_after = Decimal(str(r.amount_after))
            if verify_amount_after and provided_after != computed_after:
                raise ImportMismatchError(
                    f"Saldo po operacji w dniu {r.date} nie zgadza się: {provided_after} != {computed_after}"
                )
            after = provided_after
        else:
            after = computed_after

        if after < 0 and not allows_negative_balance:
            logger.info(f"create_transactions_rebalance_service would go negative")
            raise ImportMismatchError("This insert would make the account balance negative.")

        dt_base = r.date + timedelta(microseconds=idx)
        tx_data = TransactionCreate(
            account_id=acc_id,
            amount=amount,
            description=r.description or "",
            balance_before=before,
            balance_after=after,
            date_transaction=dt_base,
        )

        dup = await find_duplicate_transaction(session, tx_data)
        if dup is not None:
            logger.info(f"create_transactions_rebalance_service duplicate detected")
            raise DuplicateTransactionError(
                f"Duplicate transaction detected for account={acc_id}, date={dt_base}, amount={amount}, description={tx_data.description!r}"
            )

        dt_unique = await ensure_unique_dt(session, account_id=acc_id, dt=dt_base)
        tx_data = tx_data.model_copy(update={"date_transaction": dt_unique})

        tx = await create_transaction_uow(session, tx_data)
        inserted_ids.append(uuid.UUID(str(tx.id)))
        created += 1
        running = after

        if getattr(r, "capital_gain_kind", None) in (
            CapitalGainKind.DEPOSIT_INTEREST,
            CapitalGainKind.BROKER_DIVIDEND,
        ) and amount != 0:
            cg_data = CapitalGainCreate(
                deposit_account_id=acc_id,
                transaction_id=tx.id,
                kind=r.capital_gain_kind,
                amount=amount,
                currency=account.currency,
                occurred_at=tx.date_transaction,
                tax_year=tx.date_transaction.year,
            )
            await create_capital_gain(session, cg_data)

    await session.flush()

    chain = await list_chain_from_dt_for_update(session, account_id=acc_id, dt=dt_start)

    running = baseline_running
    for t in chain:
        amt = Decimal(str(t.amount))
        t.balance_before = running
        t.balance_after = running + amt
        running = Decimal(str(t.balance_after))
        if running < 0 and not allows_negative_balance:
            logger.info(f"create_transactions_rebalance_service would go negative")
            raise ImportMismatchError("This insert would make the account balance negative.")

    bal.available = running
    await session.flush()

    logger.info(
        f"create_transactions_rebalance_service: created={created} account_id={acc_id} final_balance={running}"
    )

    return {
        "created": created,
        "final_balance": running,
        "account_id": str(acc_id),
        "transaction_ids": [str(tid) for tid in inserted_ids],
        "rebalanced_count": len(chain),
    }
    

async def compute_wallet_ytd_income_expense_maps(
    session: AsyncSession,
    wallet_id: uuid.UUID,
    year: int,
) -> Tuple[Dict[Currency, Decimal], Dict[Currency, Decimal]]:
    """
    Compute year-to-date income and expense totals for a wallet grouped by currency.

    This function expects the underlying query `sum_income_expense_for_wallet_year`
    to return rows in the form:
        (status: str, currency: Currency, total: Decimal | None)

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.
        year: Year to aggregate (e.g., 2025).

    Returns:
        Tuple of:
            - income_by_currency: Dict[Currency, Decimal]
            - expense_by_currency: Dict[Currency, Decimal]
    """
    rows = await sum_income_expense_for_wallet_year(session, wallet_id=wallet_id, year=year)

    income: Dict[Currency, Decimal] = {}
    expense: Dict[Currency, Decimal] = {}

    for status_s, ccy, total in rows:
        total_dec = total or Decimal("0")
        if status_s == "INCOME":
            income[ccy] = income.get(ccy, Decimal("0")) + total_dec
        else:
            expense[ccy] = expense.get(ccy, Decimal("0")) + total_dec

    return income, expense
