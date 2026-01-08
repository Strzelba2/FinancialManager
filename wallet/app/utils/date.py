from datetime import datetime, timezone
from collections import defaultdict
from decimal import Decimal
from typing import Optional


def month_key(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def last_n_month_keys(n: int) -> list[str]:
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month
    out: list[str] = []
    for _ in range(max(1, n)):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def monthly_index_from_daily_candles(items) -> dict[str, float]:
    by_month = defaultdict(list)

    for c in (items or []):
        mk = c.date_quote.strftime("%Y-%m")
        by_month[mk].append(c)

    out: dict[str, float] = {}
    for mk, candles in by_month.items():
        candles.sort(key=lambda x: x.date_quote)
        last = candles[-1]
        out[mk] = float(Decimal(str(last.close)))
    return out
