from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class FreeFloatSnapshot:
    free_float_pct: float
    shares_outstanding: float
    as_of: date | None
    source: str

    @property
    def float_shares(self) -> float:
        return self.shares_outstanding * self.free_float_pct / 100.0


def _metric_value(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, dict) and "value" in current:
        return current.get("value")
    return current


def _metric_as_of(payload: dict[str, Any], *path: str) -> date | None:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    raw = current.get("as_of") if isinstance(current, dict) else None
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result <= 0:
        return None
    return result


def extract_free_float_snapshot(payload: dict[str, Any] | None, source: str) -> FreeFloatSnapshot | None:
    if not isinstance(payload, dict):
        return None

    pct = _to_float(_metric_value(payload, "shareholders", "free_float_pct"))
    shares = _to_float(_metric_value(payload, "company", "shares_outstanding"))
    if pct is None or shares is None or pct > 100:
        return None

    return FreeFloatSnapshot(
        free_float_pct=round(pct, 4),
        shares_outstanding=shares,
        as_of=_metric_as_of(payload, "shareholders", "free_float_pct"),
        source=source,
    )
