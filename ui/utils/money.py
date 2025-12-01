from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Iterable, Dict, Optional, Union
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


def dec2(x, q=2):
    """
    Convert a numeric-like value to Decimal and quantize it to a given precision.

    This is a convenience wrapper around:
        - `dec(x)`       → converts input to `Decimal`
        - `quantize(..)` → rounds to `q` decimal places

    Args:
        x: Value to convert to Decimal (e.g. str, int, float, Decimal).
        q: Number of decimal places to keep (default: 2).

    Returns:
        Quantized `Decimal` value.

    Raises:
        Whatever `dec` or `quantize` may raise if input is invalid.
    """
    amount = dec(x)
    return quantize(amount, q)


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


def fx_rate(src: str, dst: str, rates: Dict) -> Decimal:
    """
    Compute an FX rate from `src` currency to `dst` using a rates dict.

    The `rates` dict is expected to contain entries like:
        "USD/PLN" -> 4.1234
        "PLN/EUR" -> 0.225
        ...

    Resolution order:
        1. Direct pair:  src/dst
        2. Inverse pair: dst/src  (inverted via `invert_rate`)
        3. Cross via PLN: src/PLN and PLN/dst
        4. Cross via PLN inverse: dst/PLN and PLN/src (both inverted)
        5. Cross via USD: src/USD and USD/dst
        6. Cross via USD inverse: dst/USD and USD/src (both inverted)

    If no combination is found, returns Decimal("0").

    Args:
        src: Source currency code (e.g. "PLN", "USD").
        dst: Destination currency code.
        rates: Mapping of "CUR1/CUR2" -> numeric rate.

    Returns:
        Decimal FX rate from src to dst; Decimal("0") if not resolvable.
    """
    if src == dst:
        return Decimal('1')
    direct = f'{src}/{dst}'
    if direct in rates:
        return dec(rates[direct])
    
    inv = f"{dst}/{src}"
    if inv in rates:
        return invert_rate(rates[inv])

    if f"{src}/PLN" in rates and f"PLN/{dst}" in rates:
        return dec(rates[f"{src}/PLN"]) * dec(rates[f"PLN/{dst}"])
    if f"{dst}/PLN" in rates and f"PLN/{src}" in rates:
        return invert_rate(rates[f"{dst}/PLN"]) * invert_rate(rates[f"PLN/{src}"])

    if f"{src}/USD" in rates and f"USD/{dst}" in rates:
        return dec(rates[f"{src}/USD"]) * dec(rates[f"USD/{dst}"])
    if f"{dst}/USD" in rates and f"USD/{src}" in rates:
        return invert_rate(rates[f"{dst}/USD"]) * invert_rate(rates[f"USD/{src}"])

    return Decimal("0")
   
    
def convert_amount(
    amount: Decimal,
    src: str,
    dst: str,
    rates: Dict,
    quant: int = 2,
) -> Decimal:
    """
    Convert a Decimal amount from `src` currency to `dst` using FX rates.

    Steps:
        1. Compute fx = fx_rate(src, dst, rates)
        2. Multiply: out = amount * fx
        3. Quantize with `quantize(out, quant)`

    Args:
        amount: Monetary amount in `src` currency as Decimal.
        src: Source currency code.
        dst: Destination currency code.
        rates: FX rates mapping (passed to `fx_rate`).
        quant: Number of decimal places to keep in result.

    Returns:
        Converted and quantized Decimal value.
    """
    out = amount * fx_rate(src, dst, rates)
    return quantize(out, quant)


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


def change_currency_to(amount: Union[str, float, Decimal], view_currency: str, transaction_currency: str, rates: str) -> Decimal:
    """
    High-level helper to convert an amount to a "view" currency.

    Shortcut for typical UI usage: given an amount in `transaction_currency`,
    convert it to `view_currency` using the FX table.

    If currencies match, the function returns the original amount (as Decimal)
    without conversion.

    Args:
        amount: Input amount (str, float, or Decimal).
        view_currency: Target/display currency code (e.g. "PLN").
        transaction_currency: Original transaction currency code.
        rates: FX rate mapping passed to `convert_amount`.

    Returns:
        Amount expressed in `view_currency` as Decimal.
    """
    if view_currency == transaction_currency:
        return amount
    
    converted_amount = convert_amount(amount, transaction_currency, view_currency, rates)
    return converted_amount


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
