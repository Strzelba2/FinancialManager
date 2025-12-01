from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


PL_MONTHS = {
    "sty": 1, "stycz": 1,
    "lut": 2, "luty": 2,
    "mar": 3, "marz": 3,
    "kwi": 4, "kwie": 4,
    "maj": 5,
    "cze": 6, "czerw": 6,
    "lip": 7, "lipi": 7,
    "sie": 8, "sier": 8,
    "wrz": 9, "wrzes": 9,
    "paź": 10, "paz": 10, "pazdz": 10, "paźdz": 10,
    "lis": 11, "list": 11,
    "gru": 12, "grud": 12,
}


def to_local(dt_utc: datetime, tz: ZoneInfo = settings.TIME_ZONE) -> datetime:
    """
    Convert a UTC datetime to a given local timezone.

    If the input `dt_utc` is naive (no tzinfo), it is first assumed to be in UTC.

    Args:
        dt_utc: Datetime assumed to be in UTC (or naive, treated as UTC).
        tz: Target timezone to convert to (defaults to `settings.TIME_ZONE`).

    Returns:
        A timezone-aware `datetime` converted to `tz`.
    """
    logger.info(f"to_local: converting dt_utc={dt_utc!r} to tz={tz}")
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(tz)


def parse_last_trade_at(time_str: str) -> datetime:
    """
    Parse a last-trade time string into a `datetime`.

    Supported formats:
    - "HH:MM:SS"
    - "HH:MM"

    The parsed time is combined with `date.today()` and returned as a naive
    `datetime` (no timezone). If parsing fails or the string is empty,
    the current UTC datetime is returned.

    Args:
        time_str: Raw time string from the source (e.g. "10:45", "10:45:30").

    Returns:
        A `datetime` representing the parsed time on today's date, or
        `datetime.now(timezone.utc)` as a fallback.
    """
    s = str(time_str).strip()
    logger.info(
        f"parse_last_trade_at: raw_input={time_str!r}, normalized_input={s!r}"
    )
    
    if not s:
        return datetime.now(timezone.utc)
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt).time()
            return datetime.combine(date.today(), t)
        except ValueError:
            continue
    return datetime.now(timezone.utc)
