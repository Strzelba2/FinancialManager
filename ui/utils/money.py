from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Iterable, Dict, Optional
import re
import logging

logger = logging.getLogger(__name__)


def dec(x) -> Decimal:
    """
    Safely convert any value to `Decimal`.

    Args:
        x: The value to convert.

    Returns:
        A Decimal representation of the value (defaults to 0 if `x` is None).
    """
    
    return x if isinstance(x, Decimal) else Decimal(str(x or "0"))


def quantize(dec: Decimal, decimals: int) -> Decimal:
    """
    Round a Decimal to the specified number of decimal places using ROUND_HALF_UP.

    Args:
        dec: The Decimal to round.
        decimals: Number of decimal places.

    Returns:
        Rounded Decimal value.
    """
    q = Decimal("1").scaleb(-decimals) if decimals else Decimal("1")
    return dec.quantize(q, rounding=ROUND_HALF_UP)


def format_pl_amount(amount: Decimal, *, decimals: int = 0) -> str:
    """
    Format a Decimal value for display using Polish locale (space as thousand separator, comma as decimal).

    Args:
        amount: Decimal value to format.
        decimals: Number of decimal places.

    Returns:
        Formatted string, e.g. "12 345,67".
    """
    s = f"{quantize(amount, decimals):,.{decimals}f}"
    s = s.replace(",", " ").replace(".", ",")
    if s.startswith("-"):
        s = "−" + s[1:]
    return s


def cash_sum_for_wallet(wallet, *, currency: str) -> Decimal:
    """
    Sum available cash across all accounts in a wallet for a specific currency.

    Args:
        wallet: Wallet object with `.accounts` (each having `.currency`, `.available`, `.blocked`).
        currency: Currency to sum (e.g. 'PLN').

    Returns:
        Total available cash in the specified currency.
    """
    total = Decimal("0")
    for acc in (wallet.accounts or []):
        if getattr(acc, "currency", None) == currency:
            total += dec(getattr(acc, "available", 0)) - dec(getattr(acc, "blocked", 0))
    return total


def cash_sum_all_wallets(wallets: Iterable, *, currency: str) -> Decimal:
    """
    Sum available cash across all wallets for a specific currency.

    Args:
        wallets: List of wallet-like objects.
        currency: Currency to sum.

    Returns:
        Aggregated total cash.
    """
    total = Decimal("0")
    for w in (wallets or []):
        total += cash_sum_for_wallet(w, currency=currency)
    return total


def cash_kpi_label(amount: Decimal, currency: str, *, decimals: int = 0) -> str:
    """
    Generate KPI label for cash amount with currency and formatting.

    Args:
        amount: Amount as Decimal.
        currency: Currency code (e.g., "PLN").
        decimals: Number of decimal digits.

    Returns:
        KPI label string, e.g. "1 234,56 PLN".
    """
    return f"{format_pl_amount(amount, decimals=decimals)} {currency}"


def invert_rate(x: Optional[float | str | Decimal], places: int = 6) -> Decimal:
    """
    Invert an exchange rate (e.g. USD/PLN → PLN/USD).

    Args:
        x: Rate to invert.
        places: Decimal places to round result.

    Returns:
        Inverted rate as Decimal.
    """
    d = dec(x)
    return (Decimal("1") / d).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def cash_total_in_pln(data, rates: Dict) -> Decimal:
    """
    Calculate total cash in PLN by converting from USD and EUR.

    Args:
        wallets: Wallet list.
        rates: Dictionary with rates (e.g., {"USD/PLN": 4.0}).

    Returns:
        Total cash in PLN.
    """
    total_pln = cash_sum_all_wallets(data, currency="PLN")
    total_usd = cash_sum_all_wallets(data, currency="USD")
    total_eur = cash_sum_all_wallets(data, currency="EUR")
    if total_usd or total_eur:
        total_pln += total_usd * dec(rates.get("USD/PLN", 4)) + total_eur * dec(rates.get("EUR/PLN", 4))
    return total_pln


def cash_total_in_usd(data, rates: Dict) -> Decimal:
    """
    Calculate total cash in USD by converting from PLN and EUR.

    Args:
        wallets: Wallet list.
        rates: Dictionary with rates (e.g., {"PLN/USD": 0.25}).

    Returns:
        Total cash in USD.
    """
    total_usd = cash_sum_all_wallets(data, currency="USD")
    total_pln = cash_sum_all_wallets(data, currency="PLN")
    total_eur = cash_sum_all_wallets(data, currency="EUR")
    if total_pln or total_eur:
        total_usd += total_pln * dec(rates.get("PLN/USD", 4)) + total_eur * dec(rates.get("EUR/USD", 4))
    return total_usd


def cash_total_in_eur(data, rates: Dict) -> Decimal:
    """
    Calculate total cash in EUR by converting from USD and PLN.

    Args:
        wallets: Wallet list.
        rates: Dictionary with rates (e.g., {"USD/EUR": 0.9}).

    Returns:
        Total cash in EUR.
    """
    total_eur = cash_sum_all_wallets(data, currency="EUR")
    total_pln = cash_sum_all_wallets(data, currency="PLN")
    total_usd = cash_sum_all_wallets(data, currency="USD")
    
    if total_usd or total_pln:
        total_eur += total_usd * dec(rates.get("USD/EUR", 4)) + total_pln * dec(rates.get("PLN/EUR", 4))
    return total_eur


def parse_amount(value) -> Decimal | None:
    """
    Parse a potentially localized amount string to Decimal.

    Supports:
    - Thousands separators: space or comma
    - Decimal separators: comma or period

    Args:
        value: String, float, or Decimal representation of a number.

    Returns:
        Decimal if valid, otherwise None.
    """

    s = str(value or "").strip().replace("\u00A0", " ") 
    m = re.search(r'[-+]?\d[\d\s.,]*', s)
    if not m:
        return None
    num = m.group(0)

    num = num.replace(" ", "")

    if num.count(",") == 1 and num.count(".") == 0:
        num = num.replace(",", ".")
    else:
        num = num.replace(",", "")

    try:
        return Decimal(num)
    except InvalidOperation:
        return None
