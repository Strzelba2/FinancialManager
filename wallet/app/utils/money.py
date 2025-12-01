from decimal import Decimal
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