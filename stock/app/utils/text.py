from typing import Optional
import unicodedata
import logging

logger = logging.getLogger(__name__)


def strip_accents(s: str) -> str:
    """
    Remove diacritical marks (accents) from a Unicode string.

    This function:
    - Uses NFKD normalization to decompose characters into base + combining marks.
    - Filters out all combining characters (e.g., accents).
    - Returns a plain ASCII-like string (where possible).

    Examples:
        "październik" -> "pazdziernik"
        "świeża"      -> "swieza"

    Args:
        s: Input string with or without accents.

    Returns:
        A string with diacritics removed.
    """
    logger.debug(f"strip_accents: input={s!r}")
    
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(ch)
    )
   
    
def txt(s: Optional[str]) -> str:
    """
    Normalize a possibly-None text value into a clean string.

    This helper:
    - Treats None as an empty string.
    - Replaces non-breaking spaces (\\xa0) with regular spaces.
    - Strips leading and trailing whitespace.

    It is handy for cleaning raw HTML/extracted text before parsing.

    Args:
        s: Input string or None.

    Returns:
        A stripped, normalized string (never None).
    """
    logger.debug(f"txt: raw input={s!r}")
    return (s or "").replace("\xa0", " ").strip()
