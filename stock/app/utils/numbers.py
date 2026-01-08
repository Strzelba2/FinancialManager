from typing import Optional
from decimal import Decimal, ROUND_HALF_UP
import re
import logging

from app.utils.text import txt

logger = logging.getLogger(__name__)


def parse_float_pl(s: Optional[str]) -> Optional[float]:
    """
    Parse a Polish-formatted numeric string into a float.

    This helper:
    - Normalizes the string with `txt()`.
    - Removes spaces and percent signs.
    - Converts comma to dot as decimal separator.
    - Strips all characters except digits, dot and minus.
    - Returns None if the result is empty or not a valid float.

    Examples:
        "1 234,56"   -> 1234.56
        "5,2%"       -> 5.2
        None / ""    -> None

    Args:
        s: Input string (possibly None) containing a number in PL formatting.

    Returns:
        Parsed float value, or None if parsing fails.
    """
    logger.info(f"parse_float_pl: raw input={s!r}")
    
    if not s:
        return None
    s = txt(s).replace(" ", "").replace("%", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in {".", "-.", ".-", "-"}:
        return None
    try:
        return float(s)
    except ValueError as e:
        logger.warning(
            f"parse_float_pl: failed to parse as float: {e}"
        )
        return None
    
    
def parse_int_pl(s: Optional[str]) -> Optional[int]:
    """
    Parse a Polish-formatted numeric string into an int.

    This helper:
    - Normalizes the string with `txt()`.
    - Removes all non-digit characters.
    - Returns None if no digits remain or parsing fails.

    Examples:
        "1 234"   -> 1234
        "5 000zł" -> 5000
        None / "" -> None

    Args:
        s: Input string (possibly None) containing an integer in PL formatting.

    Returns:
        Parsed int value, or None if parsing fails.
    """
    logger.info(f"parse_int_pl: raw input={s!r}")
    
    if not s:
        return None
    s = re.sub(r"[^\d]", "", txt(s))
    if not s:
        return None
    try:
        return int(s)
    except ValueError as e:
        logger.warning(
            f"parse_int_pl: failed to parse as int: {e}"
        )
        return None
    
    
def dec(x) -> Decimal:
    """
    Safely convert any value to `Decimal`.

    Args:
        x: The value to convert.

    Returns:
        A Decimal representation of the value (defaults to 0 if `x` is None).
    """
    if x is None:
        return Decimal("0")

    if isinstance(x, Decimal):
        return x

    if isinstance(x, str):
        s = x.strip().replace("\u00a0", "").replace(" ", "")  
        if not s:
            raise ValueError("Empty string is not a valid number")

        if "," in s and "." in s:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")

        return Decimal(s)

    if isinstance(x, float):
        return Decimal(str(x))

    return Decimal(str(x or "0"))


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


def to_int_opt(s: str) -> Optional[int]:
    """
    Convert a numeric-like string to an integer, returning `None` if empty/invalid.

    This is useful for optional fields like volume. The function strips whitespace and:
    - returns `None` for empty strings
    - otherwise parses via `Decimal` first, then converts to `int`

    Args:
        s: Input string representing an integer or decimal number.

    Returns:
        Parsed integer value, or `None` if the input is empty or cannot be parsed.
    """
    s = (s or "").strip()
    if s == "":
        return None
    try:
        return int(Decimal(s))
    except Exception:
        return None
    