from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from typing import Optional

TZ = ZoneInfo('Europe/Warsaw')
BUSINESS_START = time(9, 0)
BUSINESS_END = time(17, 0)  


def _is_business_day(dt: datetime) -> bool:
    """
    Check whether a given date is a business day (Monday–Friday).

    Args:
        dt: Datetime to check (date part is used).

    Returns:
        True if weekday is 0..4 (Mon–Fri), False otherwise.
    """
    return 0 <= dt.weekday() <= 4  


def _next_business_day_9(dt: datetime) -> datetime:
    """
    Compute the next business day's start time at BUSINESS_START hour.

    The function:
        - moves `dt` forward day by day until it hits a business day (Mon–Fri),
        - then returns that date with time set to BUSINESS_START hour and 00:00 seconds.

    Args:
        dt: Reference datetime.

    Returns:
        Datetime at BUSINESS_START on the next business day.
    """
    d = dt + timedelta(days=1)
    while not _is_business_day(d):
        d += timedelta(days=1)
    return d.replace(hour=BUSINESS_START.hour, minute=0, second=0, microsecond=0)


def next_quarter_business(now: datetime) -> datetime:
    """
    Compute the next 15-minute business slot in [09:00, 17:00) local TZ.

    Rules:
        - If `now` is outside business hours or not a business day:
            -> return next business day at 09:00 (BUSINESS_START).
        - If `now` is before business hours:
            -> return today at 09:00.
        - Otherwise:
            -> round `now` up to the next 15-minute boundary.
               If that boundary is >= business end (17:00),
               return next business day at 09:00.

    Args:
        now: Current datetime (with or without tzinfo). If naive, TZ is forced to `TZ`.

    Returns:
        Datetime of the next business 15-minute slot.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    else:
        now = now.astimezone(TZ)

    start = now.replace(hour=BUSINESS_START.hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=BUSINESS_END.hour, minute=0, second=0, microsecond=0)

    if not _is_business_day(now) or now >= end:
        return _next_business_day_9(now)
    if now < start:
        return start

    q = 15
    next_min = (now.minute // q + 1) * q
    if next_min == 60:
        candidate = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        candidate = now.replace(minute=next_min, second=0, microsecond=0)

    if candidate >= end:
        return _next_business_day_9(now)
    return candidate


def to_pl_local_parts(iso_or_dt: Optional[datetime]):
    """
    Convert a datetime (or ISO string) into multiple Polish-localized formats.

    Input:
        - `iso_or_dt` may be:
            * None            → returns (None, None, None, None)
            * datetime        → used directly
            * ISO8601 string  → parsed (with 'Z' treated as '+00:00')

    Output:
        All dates/times converted to Europe/Warsaw.

    Returns:
        Tuple:
            - iso: ISO string (original dt, seconds precision, in original tz)
            - pretty: 'dd.mm.yyyy HH:MM' in Europe/Warsaw
            - date_fmt: 'dd.mm.yyyy' in Europe/Warsaw
            - time_fmt: 'HH:MM' in Europe/Warsaw
    """
    if iso_or_dt is None:
        return None, None, None, None
    if isinstance(iso_or_dt, str):
        s = iso_or_dt.replace('Z', '+00:00')
        dt = datetime.fromisoformat(s)
    else:
        dt = iso_or_dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo('UTC'))
    dt_pl = dt.astimezone(ZoneInfo('Europe/Warsaw'))
    iso = dt.isoformat(timespec='seconds')
    pretty = dt_pl.strftime('%d.%m.%Y %H:%M')
    date_fmt = dt_pl.strftime('%d.%m.%Y')
    time_fmt = dt_pl.strftime('%H:%M')
    return iso, pretty, date_fmt, time_fmt


def month_floor(dt: datetime) -> datetime:
    """
    Return the first moment of the month containing `dt`.

    The result preserves the original timezone info (tzinfo) if present:
    - Input:  2025-12-31 18:20:00+01:00
    - Output: 2025-12-01 00:00:00+01:00

    Args:
        dt: Any datetime (naive or timezone-aware).

    Returns:
        A datetime set to day=1 and time=00:00:00.000000 for the same month/year as `dt`.
    """
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
