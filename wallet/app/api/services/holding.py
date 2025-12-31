from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
from decimal import Decimal
import logging

from app.schamas.response import QuoteBySymbolItem, PositionPerformance
from app.models.models import Holding, Instrument
from app.models.enums import Currency

logger = logging.getLogger(__name__)


async def compute_brokerage_account_value_by_currency_from_quotes(
    session: AsyncSession,
    holdings: List[Holding],
    quotes_map: Dict[str, QuoteBySymbolItem],
    auto_fix_currency: bool = True,
    commit_changes: bool = True,
) -> Dict[Currency, Decimal]:
    """
    Compute brokerage account market value grouped by currency using a quotes map.

    For each holding:
    - Resolve holding.instrument and its symbol.
    - Look up the quote by symbol in `quotes_map`.
    - Multiply quantity * quote.price to get position value (in quote.currency).
    - Sum values per quote.currency into a totals dict.

    Optionally, if an instrument's stored currency differs from the quote currency:
    - When `auto_fix_currency=True`, update Instrument.currency to match quote.currency.
    - When `commit_changes=True`, commit those changes at the end.

    Args:
        session: SQLAlchemy async session (used only when committing currency fixes).
        holdings: List of Holding ORM objects with `.quantity` and `.instrument`.
        quotes_map: Mapping from instrument symbol -> QuoteBySymbolItem.
        auto_fix_currency: If True, update Instrument.currency when mismatch is detected.
        commit_changes: If True and fixes exist, commit changes via session.commit().

    Returns:
        Dict mapping Currency -> total market value in that currency.
    """
 
    if not holdings:
        logger.info("compute_brokerage_account_value_by_currency_from_quotes: no holdings")
        return {}

    totals_by_currency: Dict[Currency, Decimal] = {}
    instruments_to_fix: Dict[Instrument, Currency] = {}

    for h in holdings:
        if h.quantity is None:
            continue

        inst = h.instrument
        if inst is None:
            logger.warning(f"Holding id={h.id} has no instrument relation")
            continue

        symbol = inst.symbol
        quote = quotes_map.get(symbol)
        if quote is None:
            logger.warning(
                f"No quote found in quotes_map for symbol={symbol} (holding id={h.id})"
            )
            continue

        qty = Decimal(h.quantity)

        wallet_ccy = inst.currency
        stock_ccy = quote.currency

        if wallet_ccy != stock_ccy and auto_fix_currency:
            logger.warning(
                f"Currency mismatch for symbol={symbol}: wallet={wallet_ccy}, "
                f"stock={stock_ccy}. Will update Instrument.id={inst.id}."
            )
            instruments_to_fix[inst] = stock_ccy

        try:
            value = qty * quote.price
        except Exception:
            logger.exception(
                f"Failed to compute value for symbol={symbol}, "
                f"qty={qty}, price={quote.price}"
            )
            continue

        totals_by_currency[stock_ccy] = totals_by_currency.get(stock_ccy, Decimal("0")) + value

    if auto_fix_currency and instruments_to_fix:
        for inst, new_ccy in instruments_to_fix.items():
            inst.currency = new_ccy 
        if commit_changes:
            await session.commit()
            logger.info(
                f"Updated {len(instruments_to_fix)} instruments' currency to match stock"
            )

    logger.info(
        f"compute_brokerage_account_value_by_currency_from_quotes: totals={totals_by_currency}"
    )
    return totals_by_currency


def compute_top_n_performance_from_quotes(
    holdings: List[Holding],
    quotes_map: Dict[str, QuoteBySymbolItem],
    n: int = 5,
) -> tuple[List[PositionPerformance], List[PositionPerformance]]:
    """
    Compute top-N most profitable and top-N most losing positions in the portfolio.

    Uses:
        - holdings: quantity + avg_price (or cost per unit) + instrument.symbol
        - quotes_map: symbol -> QuoteBySymbolItem (with latest price & currency)

    PnL logic:
        - value      = quantity * price
        - cost       = quantity * avg_price
        - pnl_amount = value - cost
        - pnl_pct    = pnl_amount / cost if cost > 0 else 0

    Args:
        holdings: list of Holding WITH .instrument loaded (instrument.symbol + avg_price).
        quotes_map: mapping symbol -> latest quote from stock.
        n: number of top losers/gainers to return.

    Returns:
        (top_losers, top_gainers):
            - both are lists of PositionPerformance
            - top_losers: sorted by pnl_amount ASC (największe straty pierwsze)
            - top_gainers: sorted by pnl_amount DESC (największe zyski pierwsze)
    """
    perf_list: List[PositionPerformance] = []

    for h in holdings:
        if h.quantity is None:
            continue

        inst = h.instrument
        if inst is None:
            logger.warning(f"Holding id={h.id} has no instrument relation")
            continue

        symbol = inst.symbol
        quote = quotes_map.get(symbol)
        if quote is None:
            logger.warning(
                f"No quote for symbol={symbol} in quotes_map while computing performance"
            )
            continue

        qty = Decimal(h.quantity)
        avg_price = Decimal(h.avg_cost)  

        price = quote.price
        ccy = quote.currency

        try:
            value = qty * price
            cost = qty * avg_price
        except Exception:
            logger.exception(
                f"Failed to compute value/cost for symbol={symbol}, "
                f"qty={qty}, price={price}, avg_price={avg_price}"
            )
            continue

        pnl_amount = value - cost
        pnl_pct = Decimal("0")
        if cost > 0:
            try:
                pnl_pct = pnl_amount / cost
            except Exception:
                logger.exception(
                    f"Failed to compute pnl_pct for symbol={symbol}, "
                    f"pnl_amount={pnl_amount}, cost={cost}"
                )

        perf_list.append(
            PositionPerformance(
                symbol=symbol,
                quantity=qty,
                avg_cost=h.avg_cost,
                price=price,
                currency=ccy,
                value=value,
                cost=cost,
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
            )
        )

    if not perf_list:
        return [], []

    losers_sorted = sorted(perf_list, key=lambda p: p.pnl_pct)
    gainers_sorted = sorted(perf_list, key=lambda p: p.pnl_pct, reverse=True)

    top_losers = losers_sorted[:n]
    top_gainers = gainers_sorted[:n]

    return top_losers, top_gainers
