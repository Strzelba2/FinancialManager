from __future__ import annotations

from datetime import date

from .config import CALCULATION_VERSION, CONFIGURATION_VERSION


CACHE_TTL_SECONDS = 15 * 60


def volume_zones_cache_key(
    mic: str,
    symbol: str,
    mode: str,
    date_from: date | None,
    date_to: date | None,
    include_timeline: bool,
    max_zones: int,
    last_candle_date: date | None,
    free_float_version: str | None = None,
) -> str:
    return ":".join(
        [
            "analysis",
            "volume-zones",
            mic.strip().upper(),
            symbol.strip().upper(),
            mode,
            date_from.isoformat() if date_from else "none",
            date_to.isoformat() if date_to else "none",
            "timeline" if include_timeline else "no-timeline",
            str(max_zones),
            last_candle_date.isoformat() if last_candle_date else "none",
            free_float_version or "no-free-float-snapshot",
            CALCULATION_VERSION,
            CONFIGURATION_VERSION,
        ]
    )
