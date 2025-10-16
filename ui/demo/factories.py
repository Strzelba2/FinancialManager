import uuid
from decimal import Decimal
from typing import Optional

from schemas.wallet import ClientWalletSyncResponse, WalletListItem, AccountListItem, Currency


def _d(amount: str) -> Decimal:
    """Safe Decimal from string to avoid float issues."""
    return Decimal(amount)


def create_demo_wallet_payload(
    first_name: str = "Artur",
    user_id: Optional[str] = None,
) -> "ClientWalletSyncResponse":
    """
    Build a ClientWalletSyncResponse with demo banks, wallets and accounts.
    """
    uid = user_id or str(uuid.uuid4())

    banks = [
        {"id": str(uuid.uuid4()), "name": "mBank",   "shortname": "MBK", "bic": "BREXPLPWXXX"},
        {"id": str(uuid.uuid4()), "name": "PKO BP",  "shortname": "PKO", "bic": "BPKOPLPW"},
        {"id": str(uuid.uuid4()), "name": "ING",     "shortname": "ING", "bic": "INGBPLPW"},
        {"id": str(uuid.uuid4()), "name": "Santander", "shortname": "SAN", "bic": "WBKPPLPP"},
    ]

    w1 = WalletListItem(
        id=uuid.uuid4(),
        name="Mój portfel",
        accounts=[
            AccountListItem(
                id=uuid.uuid4(), name="mBank ROR",
                account_type="CURRENT", currency=Currency.PLN,
                available=_d("12345.67"), blocked=_d("0.00")
            ),
            AccountListItem(
                id=uuid.uuid4(), name="ING Oszczędnościowe",
                account_type="SAVINGS", currency=Currency.PLN,
                available=_d("25000.00"), blocked=_d("0.00")
            ),
            AccountListItem(
                id=uuid.uuid4(), name="USD Rachunek",
                account_type="CURRENT", currency=Currency.USD,
                available=_d("840.25"), blocked=_d("0.00")
            ),
        ],
    )

    w2 = WalletListItem(
        id=uuid.uuid4(),
        name="Portfel A",
        accounts=[
            AccountListItem(
                id=uuid.uuid4(), name="Santander ROR",
                account_type="CURRENT", currency=Currency.PLN,
                available=_d("5321.10"), blocked=_d("0.00")
            ),
            AccountListItem(
                id=uuid.uuid4(), name="Brokerage",
                account_type="BROKERAGE", currency=Currency.PLN,
                available=_d("0.00"), blocked=_d("0.00")
            ),
        ],
    )

    w3 = WalletListItem(
        id=uuid.uuid4(),
        name="Portfel Demo",
        accounts=[],
    )

    return ClientWalletSyncResponse(
        first_name=first_name,
        user_id=uid,
        wallets=[w1, w2, w3],
        banks=banks,
    )
