from typing import Optional
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
    