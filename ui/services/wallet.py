from typing import List, Dict, Tuple
import uuid
import logging
from schemas.wallet import Transaction, WalletListItem, Currency, TransactionRow
from utils.utils import parse_date, truncate_string
from utils.money import change_currency_to

logger = logging.getLogger(__name__)


def build_account_index(wallets: List[WalletListItem]) -> Dict[uuid.UUID, Tuple[str, Currency]]:
    """
    Build an index of accounts from a list of wallets.

    The index maps:
        account_id -> (account_name, account_currency, account_type)

    Args:
        wallets: List of wallet objects, each containing accounts.

    Returns:
        Dictionary where keys are account UUIDs and values are tuples:
        (name, currency, account_type).
    """
    logger.info(f"build_account_index: building index for {len(wallets or [])} wallets")
    
    index: Dict[uuid.UUID, Tuple[str, Currency]] = {}
    for w in (wallets or []):
        for acc in (w.accounts or []):
            index[acc.id] = (acc.name, acc.currency, acc.account_type)
    return index


def last_n_wallets_transactions_sorted(wallets: List[WalletListItem], n: int = 5) -> List[Transaction]:
    """
    Collect the last transactions from all wallets and return the latest N globally.

    Transactions are sorted by `date_transaction` descending.

    Args:
        wallets: List of wallet objects with `accounts` and their `last_transactions`.
        n: Maximum number of transactions to return.

    Returns:
        List of at most N `Transaction` objects, sorted by date descending.
    """
    logger.info(
        f"last_n_wallets_transactions_sorted: collecting up to {n} transactions "
        f"from {len(wallets or [])} wallets"
    )

    txs = [tx
           for w in (wallets or [])
           for acc in (w.accounts or [])
           for tx in (acc.last_transactions or [])]
    return sorted(txs, key=lambda t: t.date_transaction, reverse=True)[:n]


def all_wallets_transactions(wallets: List[WalletListItem]) -> List[Transaction]:
    """
    Flatten all `last_transactions` from all accounts in all wallets.

    Args:
        wallets: List of wallet objects.

    Returns:
        List of all `Transaction` objects found in `last_transactions`.
    """
    logger.info(
        f"all_wallets_transactions: collecting transactions from {len(wallets or [])} wallets"
    )
    return [tx
            for w in (wallets or [])
            for acc in (w.accounts or [])
            for tx in (acc.last_transactions or [])]


def all_wallets_transactions_sorted(wallets: List[WalletListItem]) -> List[Transaction]:
    """
    Return all transactions from all wallets, sorted by date descending.

    Args:
        wallets: List of wallet objects.

    Returns:
        List of `Transaction` objects sorted by `date_transaction` descending.
    """
    logger.info(
        "all_wallets_transactions_sorted: sorting all transactions by date descending"
    )
    return sorted(all_wallets_transactions(wallets), key=lambda t: t.date_transaction, reverse=True)


def make_transaction_rows(
    wallets: List[WalletListItem],
    n: int = 5,
    account_type: str = "CURRENT",
    all_last: bool = False,
    description_lenght: int = 12,
    currency: str = "PLN",
    rates: dict = None  
) -> List[TransactionRow]:
    """
    Build normalized `TransactionRow` objects for UI tables/cards.

    Source:
        - Transactions from wallets' accounts:
            * if `all_last` is False:
                take global top-N `last_transactions` across all accounts.
            * if `all_last` is True:
                take all transactions, sorted descending by date.

    Filtering:
        - Only accounts with `account_type` matching the given `account_type` are included.

    Transformations:
        - `date_transaction` is parsed via `parse_date`.
        - Amount and `balance_after` are converted to target `currency` via `change_currency_to`.
        - `description` is truncated with `truncate_string(..., keep_words=True)`.

    Args:
        wallets: List of wallets with accounts and last transactions.
        n: Number of latest transactions to consider when `all_last` is False.
        account_type: Account type filter (e.g. "CURRENT", "SAVINGS").
        all_last: If True, use all transactions; if False, only the latest N globally.
        description_lenght: Max length of description (truncation length).
        currency: Target currency code for conversion.
        rates: Optional FX rates structure passed to `change_currency_to`.

    Returns:
        List of `TransactionRow` objects ready for display.
    """
    
    if all_last:
        top = all_wallets_transactions_sorted(wallets)
    else:
        top = last_n_wallets_transactions_sorted(wallets, n=n)  
    index = build_account_index(wallets)        

    rows: List[TransactionRow] = []
    for tx in top:
        acc_name, acc_currency, acc_account_type = index.get(tx.account_id, (None, None))
        logger.info(f"acc_account_type: {acc_account_type}")
        if acc_account_type == account_type:
            logger.info(parse_date(tx.date_transaction))
            rows.append(TransactionRow(
                date_transaction=parse_date(tx.date_transaction),
                amount=change_currency_to(tx.amount, currency, acc_currency, rates),
                description=truncate_string(tx.description, description_lenght, keep_words=True),
                balance_after=change_currency_to(tx.balance_after, currency, acc_currency, rates),
                account_name=acc_name,
                currency=currency,
            ))
            
    return rows
