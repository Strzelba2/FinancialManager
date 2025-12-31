import base64
from datetime import datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal

TROY_OUNCE_G = Decimal("31.1034768")


def normalize_name(name: str) -> str:
    """Trim and collapse internal whitespace for consistent uniqueness checks."""
    return " ".join((name or "").split())


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s)


def ccy_str(x) -> str:
    return x.value if hasattr(x, "value") else str(x)


def month_floor(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def last_n_month_starts(n: int, now: datetime) -> list[datetime]:
    end_month = month_floor(now)
    start_month = end_month - relativedelta(months=n-1)
    return [start_month + relativedelta(months=i) for i in range(n)]
