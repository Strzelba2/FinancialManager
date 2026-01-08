import uuid
from decimal import Decimal
from collections import defaultdict
from typing import Any

from app.utils.money import fx_convert


def sum_snapshots_into_monthly_totals(
    fx_by_month: dict[str, dict[str, Any]],
    target_ccy: str,
    dep_rows,
    bro_rows,
    metal_rows,
    re_rows,
) -> dict[uuid.UUID, dict[str, Decimal]]:
    """
    Sum snapshot rows into monthly totals per wallet in a target currency.

    Each input row is expected to provide:
        - wallet_id: uuid.UUID
        - month_key: str (e.g. "2026-01")
        - currency.value: str currency code (e.g. "PLN", "EUR")
        - amount fields:
            - deposit: available
            - brokerage: cash + stocks
            - metals: value
            - real_estate: value

    Args:
        fx_by_month: Mapping of month_key -> FX table (used by `fx_convert`).
        target_ccy: Currency code to convert all values into.
        dep_rows: Deposit snapshot rows.
        bro_rows: Brokerage snapshot rows.
        metal_rows: Metals snapshot rows.
        re_rows: Real estate snapshot rows.

    Returns:
        Mapping: wallet_id -> { month_key -> total_in_target_ccy }.
    """
    totals: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))

    def add(wallet_id: uuid.UUID, month_key: str, ccy: str, amount: Decimal) -> None:
        if amount is None:
            return
        fx = fx_by_month.get(month_key) or {}
        try:
            converted = fx_convert(amount, ccy, target_ccy, fx)
        except Exception:
            return
        totals[wallet_id][month_key] += converted

    for r in dep_rows:
        add(r.wallet_id, r.month_key, r.currency.value, Decimal(str(r.available or 0)))

    for r in bro_rows:
        add(r.wallet_id, r.month_key, r.currency.value, Decimal(str((r.cash or 0) + (r.stocks or 0))))

    for r in metal_rows:
        add(r.wallet_id, r.month_key, r.currency.value, Decimal(str(r.value or 0)))

    for r in re_rows:
        add(r.wallet_id, r.month_key, r.currency.value, Decimal(str(r.value or 0)))

    return totals
