from decimal import Decimal
from typing import Optional, Any
from app.models.enums import BrokerageEventKind
from app.validators.validators import Q2


def compute_cash_effect(
    kind: BrokerageEventKind,
    quantity: Q2,
    price: Q2,
) -> Decimal:
    """
    Compute the cash impact of a brokerage event.

    Logic:
        - TRADE_BUY  → negative cash flow  (cash leaves account)
        - TRADE_SELL → positive cash flow  (cash enters account)
        - DIV        → positive cash flow  (dividend income)
        - Other kinds → 0

    Args:
        kind: Type of brokerage event (BUY, SELL, DIV, etc.).
        quantity: Trade quantity (Q2-decimal).
        price: Price per unit (Q2-decimal).

    Returns:
        Decimal representing cash effect; sign depends on event kind.
    """
    
    q = Decimal(quantity)
    p = Decimal(price)

    gross = q * p

    if kind == BrokerageEventKind.TRADE_BUY:
        return -gross
    if kind == BrokerageEventKind.TRADE_SELL:
        return gross
    if kind == BrokerageEventKind.DIV:
        return gross

    return Decimal("0")


def dec(x) -> Decimal:
    """
    Safely convert any value to `Decimal`.

    Args:
        x: The value to convert.

    Returns:
        A Decimal representation of the value (defaults to 0 if `x` is None).
    """
    
    return x if isinstance(x, Decimal) else Decimal(str(x or "0"))


def fx_convert(amount: Decimal, src: str, dst: str, fx: dict[str, Any]) -> Optional[Decimal]:
    """
    fx is expected to include keys like "USD/PLN", "EUR/PLN", "PLN/USD", etc.
    (the same style your UI sends from nbp_client.get_usd_eur_pln()).
    """
    if src == dst:
        return amount
    rate = fx.get(f"{src}/{dst}")
    if rate is None:
        return None
    return amount * dec(rate)


def safe_ccy(x: Any, fallback: str) -> str:
    """Return enum.value if present, else string fallback."""
    if x is None:
        return fallback
    return getattr(x, "value", None) or str(x)
