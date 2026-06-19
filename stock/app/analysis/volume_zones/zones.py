from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median

from app.schemas.volume_zones import (
    DataConfidence,
    DirectionLabel,
    VolumeZone,
    VolumeZoneEpisode,
    ZoneBehavior,
    ZoneEvidence,
    ZoneStatus,
)

from .config import VolumeZoneConfig
from .indicators import (
    EPSILON,
    classify_direction_label,
    consistency_for_contributions,
    evidence_balance,
    evidence_score,
    recent_local_high,
    recent_local_low,
    trend_context,
)
from .types import AnalysisContext, BinContribution, OhlcvCandle, PriceBin


DEMAND_LABELS = {
    "ACCUMULATION_CANDIDATE",
    "REACCUMULATION_CANDIDATE",
    "DEMAND_ABSORPTION_CANDIDATE",
}
SUPPLY_LABELS = {
    "DISTRIBUTION_CANDIDATE",
    "REDISTRIBUTION_CANDIDATE",
    "SUPPLY_ABSORPTION_CANDIDATE",
}


def _behavior_for_label(direction_label: DirectionLabel) -> ZoneBehavior:
    if direction_label in DEMAND_LABELS:
        return "DEMAND_ABSORPTION_PROXY"
    if direction_label in SUPPLY_LABELS:
        return "SUPPLY_ABSORPTION_PROXY"
    if direction_label == "INSUFFICIENT_DIRECTIONAL_EVIDENCE":
        return "INSUFFICIENT_DIRECTIONAL_EVIDENCE"
    return "NEUTRAL_LIQUIDITY"


def _active_weeks(contributions: list[BinContribution]) -> int:
    return len({item.date.isocalendar()[:2] for item in contributions})


def _dominant_session_share(contributions: list[BinContribution]) -> float:
    by_session: dict[date, float] = defaultdict(float)
    for item in contributions:
        by_session[item.date] += item.allocated_volume
    total = sum(by_session.values())
    if total <= 0:
        return 0.0
    return max(by_session.values(), default=0.0) / total


def _activity_equivalent_sessions(
    allocated_volume: float,
    last_session_index: int,
    context: AnalysisContext,
) -> float:
    if not context.rolling_median_volume:
        return 0.0
    median_volume = context.rolling_median_volume[min(last_session_index, len(context.rolling_median_volume) - 1)]
    if median_volume <= 0:
        return 0.0
    return allocated_volume / median_volume


def _split_episodes(
    contributions: list[BinContribution],
    zone_low: float,
    zone_high: float,
    candles: list[OhlcvCandle],
    context: AnalysisContext,
    config: VolumeZoneConfig,
) -> list[list[BinContribution]]:
    if not contributions:
        return []
    groups: list[list[BinContribution]] = []
    current: list[BinContribution] = []
    last_index: int | None = None
    for item in sorted(contributions, key=lambda row: (row.session_index, row.date)):
        departed = False
        if last_index is not None:
            for idx in range(last_index + 1, item.session_index):
                candle = candles[idx]
                atr = max(context.atr[idx], EPSILON)
                if (
                    candle.close < zone_low - config.episode_departure_atr * atr
                    or candle.close > zone_high + config.episode_departure_atr * atr
                ):
                    departed = True
                    break

        span_exceeded = bool(current and item.session_index - current[0].session_index > config.maximum_episode_span_sessions)
        inactive = last_index is not None and item.session_index - last_index > config.episode_inactivity_sessions
        if inactive or departed or span_exceeded:
            groups.append(current)
            current = []
        current.append(item)
        last_index = item.session_index
    if current:
        groups.append(current)
    return groups


def _directional_evidence(
    contributions: list[BinContribution],
    zone_low: float,
    zone_high: float,
) -> tuple[float, float, list[ZoneEvidence]]:
    demand = 0.0
    supply = 0.0
    high_relative_volume = 0
    failed_breakdowns = 0
    failed_breakouts = 0
    compression_points = 0

    for item in contributions:
        volume_factor = max(0.0, min(2.0, item.relative_volume - 1.0))
        percentile_factor = max(0.0, item.volume_percentile - 0.5) * 2.0
        activity = max(volume_factor, percentile_factor)
        if activity > 0.25:
            high_relative_volume += 1

        directional_reaction = item.rejection_score * max(activity, 0.25)
        if directional_reaction > 0:
            demand += directional_reaction
        elif directional_reaction < 0:
            supply += abs(directional_reaction)

        move = abs(item.close_change_atr)
        if activity > 0.25 and item.close_change_atr < 0 and move < 1.0:
            demand += activity * (1.0 - move)
        if activity > 0.25 and item.close_change_atr > 0 and move < 1.0:
            supply += activity * (1.0 - move)

        if item.low < zone_low and item.close >= zone_low:
            failed_breakdowns += 1
            demand += 0.75
        if item.high > zone_high and item.close <= zone_high:
            failed_breakouts += 1
            supply += 0.75
        if item.atr > 0 and (item.high - item.low) / item.atr < 0.75:
            compression_points += 1

    evidence: list[ZoneEvidence] = []
    if high_relative_volume:
        evidence.append(
            ZoneEvidence(
                code="HIGH_RELATIVE_VOLUME",
                value=high_relative_volume,
                direction="NEUTRAL",
            )
        )
    if demand > supply and demand > 0:
        evidence.append(
            ZoneEvidence(
                code="DECLINING_DOWNSIDE_EFFECTIVENESS",
                value=round(demand, 3),
                direction="ACCUMULATION",
            )
        )
    if supply > demand and supply > 0:
        evidence.append(
            ZoneEvidence(
                code="DECLINING_UPSIDE_EFFECTIVENESS",
                value=round(supply, 3),
                direction="DISTRIBUTION",
            )
        )
    if failed_breakdowns:
        evidence.append(
            ZoneEvidence(
                code="FAILED_BREAKDOWNS",
                value=failed_breakdowns,
                direction="ACCUMULATION",
            )
        )
    if failed_breakouts:
        evidence.append(
            ZoneEvidence(
                code="FAILED_BREAKOUTS",
                value=failed_breakouts,
                direction="DISTRIBUTION",
            )
        )
    if compression_points:
        evidence.append(
            ZoneEvidence(
                code="VOLATILITY_COMPRESSION",
                value=compression_points,
                direction="NEUTRAL",
            )
        )
    return demand, supply, evidence


def _quality_fail_reasons(
    effective_sessions: float,
    active_weeks: int,
    activity_equivalent_sessions: float,
    dominant_session_share: float,
    consistency: float,
    config: VolumeZoneConfig,
) -> list[str]:
    """Return the quality-gate failures (empty list == gate passed).

    The raw directional score is kept as-is; these reasons explain why a strong
    raw score may still not earn a directional label (correction 5).
    """
    reasons: list[str] = []
    if effective_sessions < config.minimum_effective_sessions:
        reasons.append("MINIMUM_EFFECTIVE_SESSIONS_NOT_MET")
    if active_weeks < config.minimum_active_weeks:
        reasons.append("MINIMUM_ACTIVE_WEEKS_NOT_MET")
    if activity_equivalent_sessions < config.minimum_activity_equivalent_sessions:
        reasons.append("MINIMUM_ACTIVITY_EQUIVALENT_SESSIONS_NOT_MET")
    if dominant_session_share > config.maximum_dominant_session_share:
        reasons.append("DOMINANT_SESSION_SHARE_EXCEEDED")
    if consistency < config.minimum_consistency:
        reasons.append("MINIMUM_CONSISTENCY_NOT_MET")
    return reasons


def _confirmation_levels(
    direction_label: DirectionLabel,
    zone_low: float,
    zone_high: float,
    candles: list[OhlcvCandle],
    atr_value: float,
    config: VolumeZoneConfig,
) -> tuple[float | None, float | None]:
    if direction_label in {"ACCUMULATION_CANDIDATE", "REACCUMULATION_CANDIDATE", "DEMAND_ABSORPTION_CANDIDATE"}:
        confirmation = max(
            zone_high + config.confirmation_atr_buffer * atr_value,
            recent_local_high(candles) + config.confirmation_atr_buffer * atr_value * 0.25,
        )
        invalidation = zone_low - config.invalidation_atr_buffer * atr_value
        return confirmation, invalidation
    if direction_label in {"DISTRIBUTION_CANDIDATE", "REDISTRIBUTION_CANDIDATE", "SUPPLY_ABSORPTION_CANDIDATE"}:
        confirmation = min(
            zone_low - config.confirmation_atr_buffer * atr_value,
            recent_local_low(candles) - config.confirmation_atr_buffer * atr_value * 0.25,
        )
        invalidation = zone_high + config.invalidation_atr_buffer * atr_value
        return confirmation, invalidation
    return None, None


def _episode_lifecycle(
    direction_label: DirectionLabel,
    candles: list[OhlcvCandle],
    confirmation_price: float | None,
    invalidation_price: float | None,
    first_detected_index: int,
    entered_active_index: int | None,
    config: VolumeZoneConfig,
) -> tuple[ZoneStatus, str | None, date | None, date | None]:
    """Monotonic per-episode lifecycle (no resurrection).

    Transitions:
        CANDIDATE -> ACTIVE -> CONFIRMED
        CANDIDATE -> INVALIDATED -> CLOSED
        ACTIVE -> INVALIDATED -> CLOSED

    Invalidation is counted from ``first_detected_index`` forward; confirmation
    only from ``entered_active_index`` forward. Candles before detection never
    drive a transition, and once a terminal state (CONFIRMED or CLOSED) is
    reached the walk stops - the earlier full-series scan that could flip
    INVALIDATED back to CONFIRMED is gone.

    Returns ``(legacy_status, lifecycle_status, confirmed_at, invalidated_at)``.
    """
    if confirmation_price is None or invalidation_price is None:
        return "NEUTRAL", "CANDIDATE", None, None

    is_demand = direction_label in DEMAND_LABELS
    conf_side = "above" if is_demand else "below"
    inval_side = "below" if is_demand else "above"

    def crossed(close: float, price: float, side: str) -> bool:
        return close > price if side == "above" else close < price

    inval_streak = 0
    conf_streak = 0
    for idx in range(max(first_detected_index, 0), len(candles)):
        candle = candles[idx]
        if crossed(candle.close, invalidation_price, inval_side):
            inval_streak += 1
        else:
            inval_streak = 0
        if inval_streak >= config.invalidation_hold_sessions:
            return "INVALIDATED", "CLOSED", None, candle.date

        in_active = (
            entered_active_index is not None and idx >= entered_active_index
        )
        if in_active:
            if crossed(candle.close, confirmation_price, conf_side):
                conf_streak += 1
            else:
                conf_streak = 0
            if conf_streak >= config.confirmation_hold_sessions:
                return "CONFIRMED", "CONFIRMED", candle.date, None

    if entered_active_index is not None and entered_active_index < len(candles):
        return "ACTIVE", "ACTIVE", None, None
    return "ACTIVE", "CANDIDATE", None, None


def _build_episode(
    zone_id: str,
    episode_index: int,
    contributions: list[BinContribution],
    zone_low: float,
    zone_high: float,
    candles: list[OhlcvCandle],
    context: AnalysisContext,
    config: VolumeZoneConfig,
    directional_allowed: bool = True,
) -> VolumeZoneEpisode:
    contributions = sorted(contributions, key=lambda item: item.session_index)
    allocated = sum(item.allocated_volume for item in contributions)
    weighted = sum(item.weighted_volume for item in contributions)
    effective_sessions = sum(item.overlap_ratio for item in contributions)
    active_weeks = _active_weeks(contributions)
    dominant = _dominant_session_share(contributions)
    activity_equivalent = _activity_equivalent_sessions(allocated, contributions[-1].session_index, context)
    demand, supply, evidence = _directional_evidence(contributions, zone_low, zone_high)
    balance = evidence_balance(demand, supply)
    consistency = consistency_for_contributions(contributions)
    score = evidence_score(balance, consistency if consistency > 0 else 1.0)
    trend = trend_context(candles[: contributions[-1].session_index + 1])
    quality_fail_reasons = _quality_fail_reasons(
        effective_sessions,
        active_weeks,
        activity_equivalent,
        dominant,
        consistency,
        config,
    )
    quality_passes = not quality_fail_reasons

    if quality_passes and score >= config.candidate_evidence_score_min:
        direction_label = classify_direction_label(balance, trend, config)
    elif abs(balance) > config.candidate_balance_threshold:
        direction_label = "INSUFFICIENT_DIRECTIONAL_EVIDENCE"
    else:
        direction_label = "NEUTRAL_LIQUIDITY"

    if not directional_allowed:
        # Broad cluster that could not be split into a clean zone: keep it as
        # liquidity-only, never directional (correction 3).
        direction_label = "NEUTRAL_LIQUIDITY"

    behavior = _behavior_for_label(direction_label)
    if not directional_allowed:
        behavior = "BROAD_NEUTRAL_LIQUIDITY"
    is_directional = (
        direction_label in DEMAND_LABELS or direction_label in SUPPLY_LABELS
    )

    first_detected_at = contributions[0].date
    first_detected_index = contributions[0].session_index
    cumulative_effective = 0.0
    for item in contributions:
        cumulative_effective += item.overlap_ratio
        if cumulative_effective >= min(3.0, config.minimum_effective_sessions):
            first_detected_at = item.date
            first_detected_index = item.session_index
            break

    direction_assigned_at = first_detected_at if is_directional else None
    candidate_at = direction_assigned_at

    # Entered ACTIVE: candidate conditions held for ``active_hold_sessions``
    # distinct contact sessions after first detection. Confirmation only counts
    # from here, so an early candidate and a held active phase are distinct.
    entered_active_index: int | None = None
    entered_active_at: date | None = None
    if is_directional:
        seen_sessions: list[int] = []
        for item in contributions:
            if item.session_index < first_detected_index:
                continue
            if not seen_sessions or seen_sessions[-1] != item.session_index:
                seen_sessions.append(item.session_index)
            if len(seen_sessions) >= config.active_hold_sessions:
                entered_active_index = item.session_index
                entered_active_at = item.date
                break

    atr_value = max(contributions[-1].atr, EPSILON)
    confirmation, invalidation = _confirmation_levels(
        direction_label,
        zone_low,
        zone_high,
        candles[: contributions[-1].session_index + 1],
        atr_value,
        config,
    )
    if is_directional:
        status_name, lifecycle_status, confirmed_at, invalidated_at = (
            _episode_lifecycle(
                direction_label,
                candles,
                confirmation,
                invalidation,
                first_detected_index,
                entered_active_index,
                config,
            )
        )
    else:
        status_name = "NEUTRAL"
        lifecycle_status = None
        confirmed_at = None
        invalidated_at = None
    confidence: DataConfidence = (
        "high" if quality_passes and abs(balance) >= config.strong_balance_threshold
        else "medium" if quality_passes
        else "low"
    )

    if is_directional:
        display_classification = "DIRECTIONAL"
    elif direction_label == "INSUFFICIENT_DIRECTIONAL_EVIDENCE":
        display_classification = "INSUFFICIENT_DIRECTIONAL_EVIDENCE"
    else:
        display_classification = "NEUTRAL_LIQUIDITY"

    return VolumeZoneEpisode(
        episode_id=f"{zone_id}-episode-{episode_index}",
        zone_id=zone_id,
        estimated_start_date=contributions[0].date,
        first_detected_at=first_detected_at,
        last_active_at=contributions[-1].date,
        direction_assigned_at=direction_assigned_at,
        confirmed_at=confirmed_at,
        invalidated_at=invalidated_at,
        effective_sessions=round(effective_sessions, 3),
        session_count=len({item.session_index for item in contributions}),
        active_weeks=active_weeks,
        allocated_volume=round(allocated, 3),
        weighted_volume=round(weighted, 3),
        activity_equivalent_sessions=round(activity_equivalent, 3),
        demand_absorption_evidence=round(demand, 3),
        supply_absorption_evidence=round(supply, 3),
        evidence_balance=round(balance, 4),
        consistency=round(consistency, 4),
        direction_label=direction_label,
        evidence_score=score,
        confidence=confidence,
        status=status_name,
        confirmation_price=round(confirmation, 4) if confirmation is not None else None,
        invalidation_price=round(invalidation, 4) if invalidation is not None else None,
        evidence=evidence,
        lifecycle_status=lifecycle_status,
        candidate_at=candidate_at,
        entered_active_at=entered_active_at,
        directional_classification_allowed=directional_allowed,
        detected_signature=behavior,
        episode_signature=behavior,
        raw_directional_score=score,
        quality_gate="PASSED" if quality_passes else "FAILED",
        quality_fail_reasons=quality_fail_reasons,
        display_classification=display_classification,
    )


def _split_run_at_minima(
    run: list[PriceBin], config: VolumeZoneConfig
) -> list[list[PriceBin]]:
    """Split a contiguous run at a clear low-volume node (LVN).

    A valley splits the run only when it is at least ``min_local_minimum_drop``
    below the weaker of the two surrounding peaks and both sides keep at least
    ``minimum_child_bin_count`` bins (conservative; small bumps are not cut).
    """
    n = len(run)
    child = config.minimum_child_bin_count
    if n < 2 * child + 1:
        return [run]
    interior = range(child, n - child)
    best_idx = min(interior, key=lambda i: run[i].weighted_volume, default=None)
    if best_idx is None:
        return [run]
    left = run[:best_idx]
    right = run[best_idx:]
    left_peak = max(b.weighted_volume for b in left)
    right_peak = max(b.weighted_volume for b in right)
    valley = run[best_idx].weighted_volume
    weaker_peak = min(left_peak, right_peak)
    qualifies = (
        valley <= (1.0 - config.min_local_minimum_drop) * weaker_peak
        and weaker_peak > config.minimum_child_activity
        and len(left) >= child
        and len(right) >= child
    )
    if not qualifies:
        return [run]
    return (
        _split_run_at_minima(left, config)
        + _split_run_at_minima(right, config)
    )


def _allowed_zone_width(
    piece: list[PriceBin], atr_value: float, config: VolumeZoneConfig
) -> float:
    low = min(b.low for b in piece)
    high = max(b.high for b in piece)
    center = (low + high) / 2.0
    # Hard cap = the more restrictive of the ATR-based and percentage-of-price
    # limits (percentage relative to the zone center price, not the full range).
    return min(
        config.max_zone_width_atr * max(atr_value, EPSILON),
        center * config.max_zone_width_pct,
    )


def _split_to_width_cap(
    piece: list[PriceBin], atr_value: float, config: VolumeZoneConfig
) -> list[list[PriceBin]]:
    low = min(b.low for b in piece)
    high = max(b.high for b in piece)
    if high - low <= _allowed_zone_width(piece, atr_value, config) or len(piece) < 3:
        return [piece]
    split_local = min(
        range(1, len(piece) - 1), key=lambda i: piece[i].weighted_volume
    )
    left = piece[:split_local]
    right = piece[split_local:]
    if not left or not right:
        return [piece]
    return (
        _split_to_width_cap(left, atr_value, config)
        + _split_to_width_cap(right, atr_value, config)
    )


def _cluster_active_bins(
    bins: list[PriceBin],
    full_price_range: float,
    atr_value: float,
    config: VolumeZoneConfig,
) -> list[tuple[list[PriceBin], bool]]:
    """Return ``(cluster_bins, directional_classification_allowed)`` tuples.

    Threshold runs are split at LVNs and then to the hard width cap. A piece
    that still cannot be made narrow enough (or that spans more than
    ``max_zone_price_range_share`` of the price range) is kept but flagged as
    broad neutral liquidity rather than deleted; only pieces spanning almost the
    entire range are dropped as useless.
    """
    volumes = [item.weighted_volume for item in bins if item.weighted_volume > 0]
    if not volumes:
        return []
    volume_median = median(volumes)
    mean = sum(volumes) / len(volumes)
    variance = sum((item - mean) ** 2 for item in volumes) / len(volumes)
    threshold = max(volume_median, mean + (variance ** 0.5) * 0.25)
    if max(volumes) < threshold:
        threshold = max(volumes)

    runs: list[list[PriceBin]] = []
    current: list[PriceBin] = []
    for price_bin in bins:
        if price_bin.weighted_volume >= threshold and price_bin.raw_volume > 0:
            current.append(price_bin)
            continue
        if current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    results: list[tuple[list[PriceBin], bool]] = []
    for run in runs:
        for piece in _split_run_at_minima(run, config):
            for sub in _split_to_width_cap(piece, atr_value, config):
                low = min(b.low for b in sub)
                high = max(b.high for b in sub)
                width = high - low
                range_share = (
                    width / full_price_range if full_price_range > 0 else 0.0
                )
                if range_share >= 0.9:
                    # Spans almost the whole range - not a usable zone.
                    continue
                allowed = _allowed_zone_width(sub, atr_value, config)
                directional_allowed = (
                    width <= allowed
                    and range_share <= config.max_zone_price_range_share
                )
                results.append((sub, directional_allowed))
    return results


def _band_strength_pct(
    bins: list[PriceBin], low: float, high: float, total: float
) -> float:
    weighted = sum(
        b.weighted_volume for b in bins if b.low < high and b.high > low
    )
    return weighted / total * 100.0 if total > 0 else 0.0


def _bands_from_bins(
    bins: list[PriceBin],
    full_price_range: float,
    atr_value: float,
    config: VolumeZoneConfig,
    source: str,
) -> list[dict]:
    bands: list[dict] = []
    for cbins, dir_allowed in _cluster_active_bins(
        bins, full_price_range, atr_value, config
    ):
        bands.append({
            "low": min(b.low for b in cbins),
            "high": max(b.high for b in cbins),
            "dir": dir_allowed,
            "sources": {source},
        })
    return bands


def _merge_bands(bands: list[dict], config: VolumeZoneConfig) -> list[dict]:
    """Merge bands from either profile when their ranges substantially overlap."""
    merged: list[dict] = []
    for band in sorted(bands, key=lambda b: b["low"]):
        target = None
        for existing in merged:
            lo = max(existing["low"], band["low"])
            hi = min(existing["high"], band["high"])
            overlap = max(0.0, hi - lo)
            smaller = min(
                existing["high"] - existing["low"], band["high"] - band["low"]
            ) or EPSILON
            if overlap / smaller >= config.zone_merge_overlap_fraction:
                target = existing
                break
        if target is not None:
            target["low"] = min(target["low"], band["low"])
            target["high"] = max(target["high"], band["high"])
            target["dir"] = target["dir"] or band["dir"]
            target["sources"] |= band["sources"]
        else:
            merged.append(dict(band))
    return merged


def detect_volume_zones(
    candles: list[OhlcvCandle],
    structural_bins: list[PriceBin],
    active_bins: list[PriceBin],
    context: AnalysisContext,
    config: VolumeZoneConfig,
    free_float_shares: float | None = None,
) -> list[VolumeZone]:
    full_price_range = (
        max((item.high for item in structural_bins), default=0.0)
        - min((item.low for item in structural_bins), default=0.0)
    )
    atr_value = context.atr[-1] if context.atr else 0.0
    # Discover candidate bands from BOTH profiles and merge overlaps. The
    # structural profile anchors long-term dwell zones; the active (decayed
    # volume) profile restores historical/high-price zones that activity
    # normalization alone cannot see.
    bands = _merge_bands(
        _bands_from_bins(structural_bins, full_price_range, atr_value, config, "STRUCTURAL")
        + _bands_from_bins(active_bins, full_price_range, atr_value, config, "ACTIVE"),
        config,
    )
    zones: list[VolumeZone] = []
    struct_total = sum(item.weighted_volume for item in structural_bins) or 1.0
    active_total = sum(item.weighted_volume for item in active_bins) or 1.0
    latest_index = candles[-1].index

    for zone_index, band in enumerate(bands, start=1):
        zone_id = f"zone-{zone_index}"
        zone_low = band["low"]
        zone_high = band["high"]
        directional_allowed = band["dir"]
        # Episodes / evidence are always built from full-history (structural)
        # contributions, even for active-discovered bands, so they stay causal.
        cluster = [
            b for b in structural_bins if b.low < zone_high and b.high > zone_low
        ]
        contributions = sorted(
            [item for price_bin in cluster for item in price_bin.contributions],
            key=lambda item: (item.session_index, item.date),
        )
        if not contributions:
            continue

        struct_strength = _band_strength_pct(
            structural_bins, zone_low, zone_high, struct_total
        )
        active_strength = _band_strength_pct(
            active_bins, zone_low, zone_high, active_total
        )
        sources = band["sources"]
        source_profile = "BOTH" if len(sources) > 1 else next(iter(sources))
        by_date: dict[date, float] = defaultdict(float)
        for item in contributions:
            by_date[item.date] += item.allocated_volume
        top_session_dates = [
            d for d, _ in sorted(
                by_date.items(), key=lambda kv: kv[1], reverse=True
            )[:5]
        ]
        weighted_volume = sum(item.weighted_volume for item in cluster)
        dominant_share = _dominant_session_share(contributions)
        freshness = 0.5 ** ((latest_index - contributions[-1].session_index) / max(config.profile_half_life_sessions, 1))
        activity_score = min(100.0, max(struct_strength, active_strength) * 4.0)

        episode_groups = _split_episodes(contributions, zone_low, zone_high, candles, context, config)
        episodes = [
            _build_episode(
                zone_id,
                idx,
                group,
                zone_low,
                zone_high,
                candles,
                context,
                config,
                directional_allowed,
            )
            for idx, group in enumerate(episode_groups, start=1)
        ]
        if not episodes:
            continue
        active_episode = episodes[-1]
        if not directional_allowed:
            behavior: ZoneBehavior = "BROAD_NEUTRAL_LIQUIDITY"
        else:
            behavior = _behavior_for_label(active_episode.direction_label)

        center_numerator = sum(item.center * item.weighted_volume for item in cluster)
        center = center_numerator / weighted_volume if weighted_volume > 0 else (zone_low + zone_high) / 2.0

        zones.append(
            VolumeZone(
                zone_id=zone_id,
                price_low=round(zone_low, 4),
                price_high=round(zone_high, 4),
                center_price=round(center, 4),
                estimated_start_date=active_episode.estimated_start_date,
                first_detected_at=active_episode.first_detected_at,
                last_active_at=active_episode.last_active_at,
                raw_volume=active_episode.allocated_volume,
                weighted_volume=active_episode.weighted_volume,
                activity_score=round(activity_score, 3),
                activity_equivalent_sessions=active_episode.activity_equivalent_sessions,
                effective_sessions=active_episode.effective_sessions,
                active_weeks=active_episode.active_weeks,
                dominant_session_share=round(dominant_share, 4),
                freshness_score=round(freshness * 100.0, 3),
                status=active_episode.status,
                behavior=behavior,
                direction_label=active_episode.direction_label,
                evidence_score=active_episode.evidence_score,
                evidence_balance=active_episode.evidence_balance,
                consistency=active_episode.consistency,
                confirmation_price=active_episode.confirmation_price,
                invalidation_price=active_episode.invalidation_price,
                current_free_float_turnover=(
                    round(active_episode.allocated_volume / free_float_shares * 100.0, 4)
                    if free_float_shares and free_float_shares > 0
                    else None
                ),
                current_free_float_turnover_is_estimate=free_float_shares is not None,
                evidence=active_episode.evidence,
                episodes=episodes,
                lifecycle_status=active_episode.lifecycle_status,
                directional_classification_allowed=directional_allowed,
                detected_signature=active_episode.detected_signature,
                episode_signature=active_episode.episode_signature,
                raw_directional_score=active_episode.raw_directional_score,
                quality_gate=active_episode.quality_gate,
                quality_fail_reasons=active_episode.quality_fail_reasons,
                display_classification=active_episode.display_classification,
                source_profile=source_profile,
                structural_strength=round(struct_strength, 3),
                active_strength=round(active_strength, 3),
                current_relevance=round(active_strength, 3),
                top_session_dates=top_session_dates,
            )
        )

    zones.sort(
        key=lambda item: (
            item.status == "ACTIVE",
            item.evidence_score,
            item.activity_score,
            item.freshness_score,
        ),
        reverse=True,
    )
    return zones[: config.maximum_zones_to_score]
