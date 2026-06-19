from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from .types import OhlcvCandle, ValidationResult


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result


def _get(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def normalize_ohlcv(candles: Iterable[Any]) -> ValidationResult:
    """Validate and normalize OHLCV rows without silently repairing invalid candles."""
    raw_rows = list(candles)
    warnings: list[str] = []
    duplicate_dates: list[date] = []
    excluded_rows = 0
    seen_dates: set[date] = set()
    normalized: list[OhlcvCandle] = []

    for item in sorted(raw_rows, key=lambda row: _get(row, "date_quote") or _get(row, "date") or date.min):
        raw_date = _get(item, "date_quote") or _get(item, "date")
        if raw_date is None:
            excluded_rows += 1
            warnings.append("MISSING_DATE_EXCLUDED")
            continue
        if not isinstance(raw_date, date):
            excluded_rows += 1
            warnings.append("INVALID_DATE_EXCLUDED")
            continue
        if raw_date in seen_dates:
            duplicate_dates.append(raw_date)
            excluded_rows += 1
            warnings.append("DUPLICATE_DATE_EXCLUDED")
            continue
        seen_dates.add(raw_date)

        open_price = _to_float(_get(item, "open"))
        high = _to_float(_get(item, "high"))
        low = _to_float(_get(item, "low"))
        close = _to_float(_get(item, "close"))
        volume = _to_int(_get(item, "volume"))

        if open_price is None or high is None or low is None or close is None:
            excluded_rows += 1
            warnings.append("MISSING_OHLC_EXCLUDED")
            continue
        if high < low:
            excluded_rows += 1
            warnings.append("INVALID_OHLC_RANGE_EXCLUDED")
            continue
        if not (low <= open_price <= high) or not (low <= close <= high):
            excluded_rows += 1
            warnings.append("OPEN_OR_CLOSE_OUTSIDE_RANGE_EXCLUDED")
            continue
        if volume is None:
            volume = 0
            warnings.append("MISSING_VOLUME_TREATED_AS_ZERO")
        if volume < 0:
            excluded_rows += 1
            warnings.append("NEGATIVE_VOLUME_EXCLUDED")
            continue
        if volume == 0:
            warnings.append("ZERO_VOLUME_SESSION")
        if high == low:
            warnings.append("FLAT_PRICE_SESSION")

        normalized.append(
            OhlcvCandle(
                date=raw_date,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                index=len(normalized),
            )
        )

    return ValidationResult(
        candles=normalized,
        warnings=sorted(set(warnings)),
        duplicate_dates=duplicate_dates,
        input_rows=len(raw_rows),
        excluded_rows=excluded_rows,
    )
