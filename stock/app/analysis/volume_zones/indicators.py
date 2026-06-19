from __future__ import annotations

from collections import defaultdict
from statistics import median

from app.schemas.volume_zones import DirectionLabel

from .config import VolumeZoneConfig
from .types import AnalysisContext, BinContribution, OhlcvCandle


EPSILON = 1e-9


def rolling_median(values: list[int], window: int) -> list[float]:
    out: list[float] = []
    for idx, value in enumerate(values):
        start = max(0, idx - window + 1)
        sample = [float(v) for v in values[start: idx + 1] if v is not None and v >= 0]
        out.append(float(median(sample)) if sample else float(value or 0))
    return out


def causal_percentile(values: list[int], window: int) -> list[float]:
    out: list[float] = []
    for idx, value in enumerate(values):
        start = max(0, idx - window + 1)
        sample = [float(v) for v in values[start: idx + 1] if v is not None]
        if not sample:
            out.append(0.0)
            continue
        less_or_equal = sum(1 for item in sample if item <= value)
        out.append(less_or_equal / len(sample))
    return out


def atr_series(candles: list[OhlcvCandle], window: int) -> list[float]:
    true_ranges: list[float] = []
    for idx, candle in enumerate(candles):
        if idx == 0:
            true_ranges.append(max(candle.high - candle.low, EPSILON))
            continue
        prev_close = candles[idx - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - prev_close),
                abs(candle.low - prev_close),
                EPSILON,
            )
        )

    out: list[float] = []
    for idx in range(len(true_ranges)):
        start = max(0, idx - window + 1)
        out.append(sum(true_ranges[start: idx + 1]) / (idx - start + 1))
    return out


def rejection_score(candle: OhlcvCandle) -> float:
    price_range = candle.high - candle.low
    if price_range <= 0:
        return 0.0
    close_location = ((candle.close - candle.low) - (candle.high - candle.close)) / price_range
    open_to_close = (candle.close - candle.open) / price_range
    lower_wick = max(min(candle.open, candle.close) - candle.low, 0.0) / price_range
    upper_wick = max(candle.high - max(candle.open, candle.close), 0.0) / price_range
    value = (0.55 * close_location) + (0.25 * open_to_close) + (0.20 * (lower_wick - upper_wick))
    return max(-1.0, min(1.0, value))


def evidence_balance(demand_absorption_evidence: float, supply_absorption_evidence: float) -> float:
    return (
        (demand_absorption_evidence - supply_absorption_evidence)
        / (demand_absorption_evidence + supply_absorption_evidence + EPSILON)
    )


def evidence_score(balance: float, consistency: float) -> int:
    score = round(abs(balance) * max(0.0, min(1.0, consistency)) * 100)
    return max(0, min(100, int(score)))


def rolling_directional_balance(
    candles: list[OhlcvCandle],
    context: AnalysisContext,
    window: int,
) -> list[float | None]:
    """Causal per-day evidence balance in [-1, 1], independent of any zone.

    Each day's demand/supply pressure is derived from the same effort-vs-result
    and rejection primitives used for zones, then summed over a trailing window.
    Sign is preserved: > 0 favours accumulation, < 0 distribution, 0 neutral.
    Returns ``None`` for the warm-up sessions before a full window exists.
    """
    n = len(candles)
    demand = [0.0] * n
    supply = [0.0] * n
    for i, candle in enumerate(candles):
        median_v = context.rolling_median_volume[i] or 0.0
        rel = candle.volume / median_v if median_v > 0 else 0.0
        pct = context.volume_percentile[i]
        atr = max(context.atr[i], EPSILON)
        close_change_atr = (
            (candle.close - candles[i - 1].close) / atr if i > 0 else 0.0
        )
        rej = rejection_score(candle)
        volume_factor = max(0.0, min(2.0, rel - 1.0))
        percentile_factor = max(0.0, pct - 0.5) * 2.0
        activity = max(volume_factor, percentile_factor)
        directional_reaction = rej * max(activity, 0.25)
        if directional_reaction > 0:
            demand[i] += directional_reaction
        elif directional_reaction < 0:
            supply[i] += abs(directional_reaction)
        move = abs(close_change_atr)
        if activity > 0.25 and close_change_atr < 0 and move < 1.0:
            demand[i] += activity * (1.0 - move)
        if activity > 0.25 and close_change_atr > 0 and move < 1.0:
            supply[i] += activity * (1.0 - move)

    out: list[float | None] = []
    for i in range(n):
        if i < window - 1:
            out.append(None)
            continue
        ds = sum(demand[i - window + 1: i + 1])
        ss = sum(supply[i - window + 1: i + 1])
        out.append((ds - ss) / (ds + ss) if (ds + ss) > 0 else 0.0)
    return out


def consistency_for_contributions(contributions: list[BinContribution]) -> float:
    weekly_balance: dict[tuple[int, int], float] = defaultdict(float)
    for item in contributions:
        week = item.date.isocalendar()[:2]
        weekly_balance[week] += item.rejection_score * max(item.relative_volume, 0.0)
    balances = [value for value in weekly_balance.values() if abs(value) > 0.01]
    if not balances:
        return 0.0
    total = len(balances)
    dominant_positive = sum(1 for value in balances if value > 0)
    dominant_negative = sum(1 for value in balances if value < 0)
    return max(dominant_positive, dominant_negative) / total


def count_consecutive_closes(
    candles: list[OhlcvCandle],
    threshold: float,
    direction: str,
) -> int:
    count = 0
    for candle in reversed(candles):
        if direction == "above" and candle.close > threshold:
            count += 1
            continue
        if direction == "below" and candle.close < threshold:
            count += 1
            continue
        break
    return count


def recent_local_high(candles: list[OhlcvCandle], lookback: int = 20) -> float:
    window = candles[-lookback:] if candles else []
    return max((item.high for item in window), default=0.0)


def recent_local_low(candles: list[OhlcvCandle], lookback: int = 20) -> float:
    window = candles[-lookback:] if candles else []
    return min((item.low for item in window), default=0.0)


def trend_context(candles: list[OhlcvCandle]) -> str:
    if len(candles) < 20:
        return "neutral"
    latest = candles[-1].close
    reference = candles[-20].close
    if reference <= 0:
        return "neutral"
    change = (latest - reference) / reference
    if change <= -0.06:
        return "after_decline"
    if change >= 0.06:
        return "after_rise"
    return "neutral"


def classify_direction_label(balance: float, trend: str, config: VolumeZoneConfig) -> DirectionLabel:
    if balance >= config.strong_balance_threshold:
        return "ACCUMULATION_CANDIDATE" if trend != "after_rise" else "REACCUMULATION_CANDIDATE"
    if balance > config.candidate_balance_threshold:
        return "DEMAND_ABSORPTION_CANDIDATE"
    if balance <= -config.strong_balance_threshold:
        return "DISTRIBUTION_CANDIDATE" if trend != "after_decline" else "REDISTRIBUTION_CANDIDATE"
    if balance < -config.candidate_balance_threshold:
        return "SUPPLY_ABSORPTION_CANDIDATE"
    return "NEUTRAL_LIQUIDITY"
