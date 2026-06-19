from __future__ import annotations

import math

from .config import VolumeZoneConfig
from .indicators import EPSILON, atr_series, causal_percentile, rejection_score, rolling_median
from .types import AnalysisContext, BinContribution, OhlcvCandle, PriceBin


def time_decay_weight(
    age_in_sessions: int, half_life_sessions: int | None
) -> float:
    # ``None`` means no decay - the structural profile spans the full history.
    if half_life_sessions is None:
        return 1.0
    return 0.5 ** (max(age_in_sessions, 0) / max(half_life_sessions, 1))


def build_analysis_context(candles: list[OhlcvCandle], config: VolumeZoneConfig) -> AnalysisContext:
    volumes = [item.volume for item in candles]
    medians = rolling_median(volumes, config.volume_median_window)
    percentiles = causal_percentile(volumes, config.volume_percentile_window)
    atr = atr_series(candles, config.atr_window)
    return AnalysisContext(
        rolling_median_volume=medians,
        volume_percentile=percentiles,
        atr=atr,
    )


def build_price_bins(candles: list[OhlcvCandle], config: VolumeZoneConfig) -> list[PriceBin]:
    min_price = min(candle.low for candle in candles)
    max_price = max(candle.high for candle in candles)
    if max_price <= min_price:
        width = max(max_price * 0.01, 0.01)
        return [PriceBin(index=0, low=max(min_price - width, 0.0), high=max_price + width)]

    if config.price_bin_strategy == "percentage_bins" and min_price > 0:
        edges = [min_price]
        while edges[-1] < max_price and len(edges) <= config.target_bin_count * 4:
            edges.append(edges[-1] * (1.0 + config.price_bin_percentage))
        if edges[-1] < max_price:
            edges.append(max_price)
    elif config.price_bin_strategy == "atr_based_bins":
        atr = atr_series(candles, config.atr_window)[-1]
        width = max(atr, (max_price - min_price) / config.target_bin_count, EPSILON)
        count = max(1, min(240, math.ceil((max_price - min_price) / width)))
        step = (max_price - min_price) / count
        edges = [min_price + step * idx for idx in range(count + 1)]
    elif config.price_bin_strategy == "fixed_target_bin_count":
        count = config.target_bin_count
        step = (max_price - min_price) / count
        edges = [min_price + step * idx for idx in range(count + 1)]
    elif min_price > 0:
        log_min = math.log(min_price)
        log_max = math.log(max_price)
        step = (log_max - log_min) / config.target_bin_count
        edges = [math.exp(log_min + step * idx) for idx in range(config.target_bin_count + 1)]
    else:
        count = config.target_bin_count
        step = (max_price - min_price) / count
        edges = [min_price + step * idx for idx in range(count + 1)]

    edges[0] = min_price
    edges[-1] = max_price
    bins: list[PriceBin] = []
    for idx in range(len(edges) - 1):
        low = edges[idx]
        high = edges[idx + 1]
        if high <= low:
            continue
        bins.append(PriceBin(index=len(bins), low=low, high=high))
    return bins


def _price_in_bin(price: float, price_bin: PriceBin, is_last: bool) -> bool:
    if is_last:
        return price_bin.low <= price <= price_bin.high
    return price_bin.low <= price < price_bin.high


def allocate_candle_to_bins(
    candle: OhlcvCandle,
    bins: list[PriceBin],
    config: VolumeZoneConfig,
) -> list[tuple[int, float, float]]:
    """Return `(bin_index, allocated_volume, overlap_ratio)` for one candle."""
    if not bins or candle.volume <= 0:
        return []

    price_range = candle.high - candle.low
    body_low = min(candle.open, candle.close)
    body_high = max(candle.open, candle.close)
    typical_price = (candle.high + candle.low + candle.close) / 3.0
    raw_weights: list[tuple[int, float, float]] = []

    for idx, price_bin in enumerate(bins):
        is_last = idx == len(bins) - 1
        if price_range <= 0:
            overlap = 1.0 if _price_in_bin(candle.close, price_bin, is_last) else 0.0
        else:
            intersection = max(0.0, min(candle.high, price_bin.high) - max(candle.low, price_bin.low))
            overlap = intersection / price_range
        if overlap <= 0:
            continue

        multiplier = 1.0
        if max(0.0, min(body_high, price_bin.high) - max(body_low, price_bin.low)) > 0:
            multiplier += config.body_bin_bonus
        if _price_in_bin(candle.close, price_bin, is_last):
            multiplier += config.close_bin_bonus
        if _price_in_bin(typical_price, price_bin, is_last):
            multiplier += config.typical_price_bin_bonus
        raw_weights.append((idx, overlap * multiplier, overlap))

    if not raw_weights:
        for idx, price_bin in enumerate(bins):
            if _price_in_bin(candle.close, price_bin, idx == len(bins) - 1):
                return [(idx, float(candle.volume), 1.0)]
        return []

    total_weight = sum(item[1] for item in raw_weights)
    if total_weight <= 0:
        return []
    return [
        (idx, float(candle.volume) * raw_weight / total_weight, overlap)
        for idx, raw_weight, overlap in raw_weights
    ]


def build_volume_profile(
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
    *,
    half_life_sessions: int | None = None,
    weighting: str = "time_decay",
    lookback_sessions: int | None = None,
    context: AnalysisContext | None = None,
) -> tuple[list[PriceBin], AnalysisContext]:
    """Build a price-volume profile.

    ``weighting="time_decay"`` accumulates ``allocated_volume * decay`` (the
    active profile). ``weighting="activity_normalized"`` accumulates
    ``overlap_ratio * relative_volume`` so liquidity-heavy recent years do not
    dominate the long-term structural profile. ``lookback_sessions`` limits the
    candles that contribute (bin edges still span the full price range so the
    active profile stays aligned with the chart axis). ``context`` may be
    supplied to avoid recomputing rolling stats for a second profile.
    """
    bins = build_price_bins(candles, config)
    if context is None:
        context = build_analysis_context(candles, config)
    last_index = candles[-1].index if candles else 0
    min_included_index = (
        0 if lookback_sessions is None
        else max(0, last_index - lookback_sessions + 1)
    )

    for candle in candles:
        if candle.index < min_included_index:
            continue
        allocations = allocate_candle_to_bins(candle, bins, config)
        median_volume = context.rolling_median_volume[candle.index] or 0.0
        relative_volume = candle.volume / median_volume if median_volume > 0 else 0.0
        atr = max(context.atr[candle.index], EPSILON)
        if candle.index > 0:
            close_change_atr = (candle.close - candles[candle.index - 1].close) / atr
        else:
            close_change_atr = 0.0
        decay = time_decay_weight(last_index - candle.index, half_life_sessions)
        candle_rejection = rejection_score(candle)

        for bin_index, allocated, overlap in allocations:
            if weighting == "activity_normalized":
                weighted = overlap * relative_volume
            else:
                weighted = allocated * decay
            contribution = BinContribution(
                date=candle.date,
                session_index=candle.index,
                allocated_volume=allocated,
                weighted_volume=weighted,
                overlap_ratio=overlap,
                close=candle.close,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                relative_volume=relative_volume,
                volume_percentile=context.volume_percentile[candle.index],
                atr=atr,
                rejection_score=candle_rejection,
                close_change_atr=close_change_atr,
            )
            price_bin = bins[bin_index]
            price_bin.raw_volume += allocated
            price_bin.weighted_volume += weighted
            price_bin.effective_sessions += overlap
            price_bin.contributions.append(contribution)

    return bins, context
