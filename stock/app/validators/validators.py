from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Any, Annotated, Callable
from pydantic import BeforeValidator, AfterValidator, AnyUrl, TypeAdapter
import re
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


def q2(v: Optional[Decimal]) -> Optional[Decimal]:
    """
    Quantize a Decimal value to 2 decimal places with HALF_UP rounding.

    Args:
        v: Input Decimal value or None.

    Returns:
        Decimal rounded to 2 decimal places, or None if input is None.
    """
    logger.debug(f"q2: input={v!r}")
    
    if v is None:
        return None
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def strip(v: Any) -> Any:
    """
    Strip whitespace from a string, pass through non-strings unchanged.

    Args:
        v: Any value; if str, `.strip()` is applied.

    Returns:
        Stripped string or the original value for non-strings.
    """
    logger.debug(f"strip: input={v!r}")
    return v.strip() if isinstance(v, str) else v


def strip_upper(v: Any) -> Any:
    """
    Strip whitespace and uppercase a string, pass through non-strings unchanged.

    Args:
        v: Any value; if str, `.strip().upper()` is applied.

    Returns:
        Normalized string or the original value for non-strings.
    """
    logger.debug(f"strip_upper: input={v!r}")
    return v.strip().upper() if isinstance(v, str) else v


def require_nonempty(v: str) -> str:
    """
    Ensure a string is not empty or only whitespace.

    Args:
        v: Input string.

    Returns:
        The original string if non-empty after strip.

    Raises:
        ValueError: If the string is empty or only whitespace.
    """
    logger.debug(f"require_nonempty: input={v!r}")
    if not v or not v.strip():
        raise ValueError("cannot be empty")
    return v


def require_len_between_1_12(v: str) -> str:
    """
    Ensure a string length is between 1 and 12 characters.

    Args:
        v: Input string.

    Returns:
        The original string if its length is in [1, 12].

    Raises:
        ValueError: If the length is outside the allowed range.
    """
    logger.debug(f"require_len_between_1_12: input={v!r}, len={len(v)}")
    if not (1 <= len(v) <= 12):
        raise ValueError("must be 1..12 characters")
    return v


def require_len_between_1_50(v: str) -> str:
    """
    Ensure a string length is between 1 and 50 characters.

    Args:
        v: Input string.

    Returns:
        The original string if its length is in [1, 50].

    Raises:
        ValueError: If the length is outside the allowed range.
    """
    logger.debug(f"require_len_between_1_50: input={v!r}, len={len(v)}")
    if not (1 <= len(v) <= 50):
        raise ValueError("must be 1..50 characters")
    return v


def require_regex(pattern: str, msg: str) -> Callable[[str], str]:
    """
    Build a validator that enforces a full regex match.

    Args:
        pattern: Regular expression pattern (full match).
        msg: Error message to raise on mismatch.

    Returns:
        A function taking a string and returning it if it matches the regex.

    Raises (from inner function):
        ValueError: If the string does not fully match the pattern.
    """
    rx = re.compile(pattern)
    
    def _check(s: str) -> str:
        if not rx.fullmatch(s):
            raise ValueError(msg)
        return s
    return _check


def validate_isin(s: str) -> str:
    """
    Validate an ISIN according to ISO 6166 basic format rules.

    Checks:
    - If None, returns None (for optional ISIN fields).
    - Must be exactly 12 characters.
    - Must match `[A-Z]{2}[A-Z0-9]{9}[0-9]`.

    Note: This implementation checks length and pattern, but does not
    yet validate the Luhn checksum digit.

    Args:
        s: ISIN string or None.

    Returns:
        The original ISIN string if valid, or None if input is None.

    Raises:
        ValueError: If format or length constraints are violated.
    """
    logger.debug(f"validate_isin: input={s!r}")
    
    if s is None:
        return None
    
    if len(s) != 12:
        raise ValueError("ISIN must be exactly 12 characters")
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", s):
        raise ValueError("Invalid ISIN format")
    return s


def to_upper_trim_optional(v: object) -> Optional[str]:
    """
    Normalize optional text: trim whitespace and uppercase, None on empty.

    Args:
        v: Value to normalize; converted to str if not None.

    Returns:
        Uppercased and stripped string, or None if input is None/empty.
    """
    logger.debug(f"to_upper_trim_optional: input={v!r}")
    
    if v is None:
        return None
    s = str(v).strip().upper()
    return s or None


def to_int(v: object) -> int:
    """
    Convert a value to int with a controlled error message.

    Args:
        v: Value to cast to int.

    Returns:
        Integer representation of the value.

    Raises:
        ValueError: If conversion fails.
    """
    logger.debug(f"to_int: input={v!r}")
    
    try:
        return int(v)
    except Exception as e:
        raise ValueError("must be an integer") from e


def ge(min_value: int) -> Callable[[int], int]:
    """
    Build a validator that ensures a value is greater than or equal to `min_value`.

    Args:
        min_value: Minimum allowed value (inclusive).

    Returns:
        A function that checks the constraint and returns the value.

    Raises (from inner function):
        ValueError: If `x < min_value`.
    """
    logger.debug(f"ge: creating validator with min_value={min_value}")
    
    def _check(x: int) -> int:
        logger.debug(f"ge._check: value={x}")
        if x < min_value:
            raise ValueError(f"must be >= {min_value}")
        return x
    return _check


def to_dt_optional(v: object) -> Optional[datetime]:
    """
    Convert a value to an optional datetime using ISO 8601 parsing.

    Args:
        v: Value to convert (None, empty string, datetime, or ISO 8601 string).

    Returns:
        - None if value is None or empty string.
        - The original datetime if already a datetime instance.
        - Parsed datetime if convertible from ISO 8601 string.

    Raises:
        ValueError: If the value is not a valid ISO 8601 datetime.
    """
    logger.debug(f"to_dt_optional: input={v!r}")
    
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except Exception as e:
        raise ValueError("invalid datetime format (expected ISO 8601)") from e
    

def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure a datetime is converted to UTC (or return None).

    Args:
        dt: Datetime to normalize; may be naive, aware, or None.

    Returns:
        A UTC-aware datetime, or None if input is None.
    """
    logger.debug(f"to_utc: input={dt!r}")
    
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def strip_upper_opt(v: Optional[str]) -> Optional[str]:
    """
    Trim and uppercase an optional string; pass through None.

    Args:
        v: Input string or None.

    Returns:
        Uppercased, stripped string, or None if input is None.
    """
    logger.debug(f"strip_upper_opt: input={v!r}")
    
    if v is None:
        return None
    return v.strip().upper()


def nonempty_if_present(v: Optional[str]) -> Optional[str]:
    """
    Require a non-empty string if the value is present.

    Args:
        v: Optional string.

    Returns:
        The original value if non-empty, or None if input is None.

    Raises:
        ValueError: If value is an empty string.
    """
    logger.debug(f"nonempty_if_present: input={v!r}")
    
    if v is None:
        return None
    if v == "":
        raise ValueError("must not be empty")
    return v


URL_TYPE = TypeAdapter(AnyUrl)


def url_to_str(v: object) -> Optional[str]:
    """
    Validate a URL (str or AnyUrl) and return it as a plain string.

    Args:
        v: URL-like value (None, empty string, str, AnyUrl).

    Returns:
        Normalized URL as string, or None if input is None/empty.

    Raises:
        pydantic.ValidationError: If the value is not a valid URL.
    """
    logger.debug(f"url_to_str: input={v!r}")
    
    if v is None or v == "":
        return None
    return str(URL_TYPE.validate_python(v))


Q2 = Annotated[Decimal, AfterValidator(q2)]
NonEmptyStr = Annotated[str, AfterValidator(strip), AfterValidator(require_nonempty)]
NonEmptyStrUpper = Annotated[str, AfterValidator(strip_upper), AfterValidator(require_nonempty)]
NonEmptyStrUpperOpt = Annotated[
    Optional[str],
    AfterValidator(strip_upper_opt),
    AfterValidator(nonempty_if_present),
]
Shortname = Annotated[str, BeforeValidator(strip_upper), AfterValidator(require_len_between_1_12)]
Name = Annotated[str, BeforeValidator(strip), AfterValidator(require_len_between_1_50)]
MICCode = Annotated[
    str,
    BeforeValidator(strip_upper),
    AfterValidator(require_regex(r"^[A-Z0-9]{4}$", "MIC must be 4 uppercase letters/digits")),
]

ISINOpt = Annotated[
    Optional[str],
    BeforeValidator(to_upper_trim_optional),
    AfterValidator(validate_isin),
]

g0int = Annotated[
    int,
    BeforeValidator(to_int),
    AfterValidator(ge(0)),
]

datetimeUTC = Annotated[
    Optional[datetime],
    BeforeValidator(to_dt_optional),
    AfterValidator(to_utc),
]