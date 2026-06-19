from __future__ import annotations

from datetime import date
from typing import Iterable, NamedTuple

from app.schemas.volume_zones import (
    AnalysisMode,
    CurrentStateName,
    CurrentZoneState,
    DataConfidence,
    DataQuality,
    ProfileMetadata,
    TimelinePoint,
    VolumeZone,
    VolumeProfileBin,
    VolumeZonesResponse,
)

from .backtest import summarize_walk_forward
from .config import CALCULATION_VERSION, CONFIGURATION_VERSION, DEFAULT_CONFIG, VolumeZoneConfig
from .data import normalize_ohlcv
from .episodes import (
    detect_directional_episodes,
    enrich_directional_phases,
    link_episodes_to_zones,
    rank_major_directional_phases,
    resolve_directional_phases,
)
from .free_float import FreeFloatSnapshot
from .indicators import rolling_directional_balance
from .profile import build_analysis_context, build_volume_profile
from .types import OhlcvCandle, PriceBin, ValidationResult
from .zones import detect_volume_zones


def _data_quality(validation: ValidationResult, free_float: FreeFloatSnapshot | None) -> DataQuality:
    rows = validation.candles
    confidence: DataConfidence = "high"
    if validation.excluded_rows or validation.duplicate_dates:
        confidence = "medium"
    if len(rows) < DEFAULT_CONFIG.min_history_sessions * 2:
        confidence = "low"
    warnings = [*validation.warnings, "DAILY_OHLCV_PROXY_NOT_ORDER_FLOW"]
    if free_float is None:
        warnings.append("FREE_FLOAT_SNAPSHOT_NOT_AVAILABLE")
    else:
        warnings.append("FREE_FLOAT_SNAPSHOT_USED")
        warnings.append("HISTORICAL_FREE_FLOAT_TIME_SERIES_NOT_AVAILABLE")
    return DataQuality(
        historical_free_float_available=False,
        current_free_float_used=free_float is not None,
        current_free_float_pct=free_float.free_float_pct if free_float is not None else None,
        current_free_float_as_of=free_float.as_of if free_float is not None else None,
        current_float_shares=round(free_float.float_shares) if free_float is not None else None,
        current_free_float_source=free_float.source if free_float is not None else None,
        confidence=confidence,
        input_rows=validation.input_rows,
        valid_rows=len(rows),
        excluded_rows=validation.excluded_rows,
        duplicate_dates=validation.duplicate_dates,
        first_date=rows[0].date if rows else None,
        last_date=rows[-1].date if rows else None,
        warnings=warnings,
    )


def _distance_to_zone(zone: VolumeZone, price: float) -> float:
    if zone.price_low <= price <= zone.price_high:
        return 0.0
    if price < zone.price_low:
        return zone.price_low - price
    return price - zone.price_high


def _zone_distance(zone: VolumeZone, price: float) -> float:
    if zone.price_low <= price <= zone.price_high:
        return 0.0
    return _distance_to_zone(zone, price)


def _zone_is_recent_or_close(
    zone: VolumeZone,
    current_candle: OhlcvCandle,
    current_atr: float,
    date_to_index: dict[date, int],
    config: VolumeZoneConfig,
) -> bool:
    last_index = date_to_index.get(zone.last_active_at)
    recent = last_index is not None and current_candle.index - last_index <= config.active_zone_recent_sessions
    close = _zone_distance(zone, current_candle.close) <= max(current_atr, 0.01) * config.active_zone_max_atr_distance
    return close or recent


def _select_active_zone(
    zones: list[VolumeZone],
    current_candle: OhlcvCandle,
    current_atr: float,
    date_to_index: dict[date, int],
    config: VolumeZoneConfig,
) -> VolumeZone | None:
    candidates = [
        zone for zone in zones
        if _zone_is_recent_or_close(zone, current_candle, current_atr, date_to_index, config)
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda zone: (
            zone.status in {"ACTIVE", "CONFIRMED", "INVALIDATED"},
            -_zone_distance(zone, current_candle.close),
            zone.status != "INVALIDATED",
            zone.evidence_score,
            zone.activity_score,
            zone.freshness_score,
        ),
        reverse=True,
    )
    return candidates[0]


def _visible_zones(
    zones: list[VolumeZone],
    active_zone: VolumeZone | None,
    current_price: float,
    max_zones: int,
) -> list[VolumeZone]:
    if not zones:
        return []
    selected: list[VolumeZone] = []
    if active_zone is not None:
        selected.append(active_zone)
    demand = sorted(
        [
            zone for zone in zones
            if zone.behavior == "DEMAND_ABSORPTION_PROXY" and zone not in selected
        ],
        key=lambda zone: _distance_to_zone(zone, current_price),
    )
    supply = sorted(
        [
            zone for zone in zones
            if zone.behavior == "SUPPLY_ABSORPTION_PROXY" and zone not in selected
        ],
        key=lambda zone: _distance_to_zone(zone, current_price),
    )
    neutral = sorted(
        [zone for zone in zones if zone not in selected and zone not in demand and zone not in supply],
        key=lambda zone: (-zone.activity_score, _distance_to_zone(zone, current_price)),
    )
    for group in (demand[:1], supply[:1], neutral, demand[1:], supply[1:]):
        for zone in group:
            if zone not in selected:
                selected.append(zone)
            if len(selected) >= max_zones:
                return selected
    return selected[:max_zones]


_ABOVE_RELATIONS = {
    "ABOVE_ZONE", "APPROACHING_FROM_ABOVE", "RETESTING_FROM_ABOVE", "BROKEN_UP",
}
_BELOW_RELATIONS = {
    "BELOW_ZONE", "APPROACHING_FROM_BELOW", "RETESTING_FROM_BELOW", "BROKEN_DOWN",
}


def _price_relation(
    zone: VolumeZone,
    candle: OhlcvCandle,
    atr: float,
    recent: list[OhlcvCandle],
    config: VolumeZoneConfig,
) -> str:
    low, high = zone.price_low, zone.price_high
    close = candle.close
    a = max(atr, 0.01)
    if low <= close <= high:
        return "INSIDE_ZONE"
    above = close > high
    dist = (close - high) if above else (low - close)
    was_inside = any(low <= c.close <= high for c in recent)
    hold = config.price_relation_break_hold_sessions
    window = recent[-hold:] if len(recent) >= hold else []
    held = bool(window) and all(
        (c.close > high if above else c.close < low) for c in window
    )
    if held and was_inside:
        return "BROKEN_UP" if above else "BROKEN_DOWN"
    if dist <= config.price_relation_retest_atr * a and was_inside:
        return "RETESTING_FROM_ABOVE" if above else "RETESTING_FROM_BELOW"
    if dist <= config.price_relation_approach_atr * a:
        return "APPROACHING_FROM_ABOVE" if above else "APPROACHING_FROM_BELOW"
    return "ABOVE_ZONE" if above else "BELOW_ZONE"


def _current_market_role(zone: VolumeZone, relation: str) -> str:
    sig = zone.episode_signature
    invalidated = zone.lifecycle_status in {"INVALIDATED", "CLOSED"}
    if sig == "DEMAND_ABSORPTION_PROXY":
        if not invalidated:
            return "ACTIVE_DEMAND"
        below = relation in _BELOW_RELATIONS
        return "FORMER_DEMAND_NOW_SUPPLY" if below else "HISTORICAL_SUPPORT"
    if sig == "SUPPLY_ABSORPTION_PROXY":
        if not invalidated:
            return "ACTIVE_SUPPLY"
        above = relation in _ABOVE_RELATIONS
        return "FORMER_SUPPLY_NOW_DEMAND" if above else "HISTORICAL_RESISTANCE"
    return "NEUTRAL_LIQUIDITY"


def _selection_metadata(
    zone: VolumeZone,
    candle: OhlcvCandle,
    atr: float,
    date_to_index: dict[date, int],
    config: VolumeZoneConfig,
) -> tuple[str, float | None, float | None, int | None]:
    dist = _zone_distance(zone, candle.close)
    last_index = date_to_index.get(zone.last_active_at)
    recent = (
        last_index is not None
        and candle.index - last_index <= config.active_zone_recent_sessions
    )
    close = dist <= max(atr, 0.01) * config.active_zone_max_atr_distance
    if dist == 0.0:
        reason = "INSIDE_ZONE"
    elif close and recent:
        reason = "INSIDE_AND_RECENT"
    elif close:
        reason = "WITHIN_ATR_DISTANCE"
    else:
        reason = "RECENT_CONTACT"
    sessions_since = (
        candle.index - last_index if last_index is not None else None
    )
    pct = dist / candle.close * 100.0 if candle.close else None
    atr_dist = dist / max(atr, 0.01)
    return reason, pct, atr_dist, sessions_since


def _display_role(
    zone: VolumeZone, active_zone: VolumeZone | None, current_price: float
) -> str:
    if active_zone is not None and zone.zone_id == active_zone.zone_id:
        return "ACTIVE"
    if zone.behavior == "DEMAND_ABSORPTION_PROXY":
        return "NEAREST_DEMAND"
    if zone.behavior == "SUPPLY_ABSORPTION_PROXY":
        return "NEAREST_SUPPLY"
    if zone.price_high < current_price:
        return "NEAREST_SUPPORT"
    if zone.price_low > current_price:
        return "NEAREST_RESISTANCE"
    return "STRONGEST_STRUCTURAL"


def _finalize_zones(
    all_zones: list[VolumeZone],
    highlighted_ids: list[str],
    active_zone: VolumeZone | None,
    current_candle: OhlcvCandle,
    current_atr: float,
    recent_candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
) -> list[VolumeZone]:
    """Set the response-time current_market_role on every zone (needed for
    coloring all historical zones) and display_priority/role on the highlighted
    subset only."""
    current_price = current_candle.close
    priority = {zid: i + 1 for i, zid in enumerate(highlighted_ids)}
    finalized: list[VolumeZone] = []
    for zone in all_zones:
        relation = _price_relation(
            zone, current_candle, current_atr, recent_candles, config
        )
        update: dict = {"current_market_role": _current_market_role(zone, relation)}
        if zone.zone_id in priority:
            update["display_priority"] = priority[zone.zone_id]
            update["display_role"] = _display_role(zone, active_zone, current_price)
        finalized.append(zone.model_copy(update=update))
    return finalized


def _nearest_zones(
    zones: list[VolumeZone], current_price: float
) -> tuple[VolumeZone | None, VolumeZone | None]:
    above = [z for z in zones if z.price_low > current_price]
    below = [z for z in zones if z.price_high < current_price]
    nearest_above = min(
        above, key=lambda z: z.price_low - current_price, default=None
    )
    nearest_below = min(
        below, key=lambda z: current_price - z.price_high, default=None
    )
    return nearest_above, nearest_below


def _current_state_for_zone(
    zone: VolumeZone | None,
    current_candle: OhlcvCandle | None = None,
    current_atr: float = 0.0,
    recent_candles: list[OhlcvCandle] | None = None,
    date_to_index: dict[date, int] | None = None,
    config: VolumeZoneConfig | None = None,
    with_context: bool = False,
) -> CurrentZoneState:
    if zone is None:
        return CurrentZoneState(
            state="NEUTRAL",
            evidence_score=0,
            transition_reasons=[],
        )

    label = zone.direction_label
    status = zone.status
    if label in {"ACCUMULATION_CANDIDATE", "DEMAND_ABSORPTION_CANDIDATE", "REACCUMULATION_CANDIDATE"}:
        if status == "CONFIRMED":
            state: CurrentStateName = "MARKUP"
        elif status == "INVALIDATED":
            state = "FAILED_ACCUMULATION"
        elif label == "REACCUMULATION_CANDIDATE" and zone.evidence_score >= 40:
            state = "REACCUMULATION_ACTIVE"
        elif label == "REACCUMULATION_CANDIDATE":
            state = "REACCUMULATION_CANDIDATE"
        elif zone.evidence_score >= 40 and zone.behavior == "DEMAND_ABSORPTION_PROXY":
            state = "ACCUMULATION_ACTIVE"
        else:
            state = "ACCUMULATION_CANDIDATE"
    elif label in {"DISTRIBUTION_CANDIDATE", "SUPPLY_ABSORPTION_CANDIDATE", "REDISTRIBUTION_CANDIDATE"}:
        if status == "CONFIRMED":
            state = "MARKDOWN"
        elif status == "INVALIDATED":
            state = "FAILED_DISTRIBUTION"
        elif label == "REDISTRIBUTION_CANDIDATE" and zone.evidence_score >= 40:
            state = "REDISTRIBUTION_ACTIVE"
        elif label == "REDISTRIBUTION_CANDIDATE":
            state = "REDISTRIBUTION_CANDIDATE"
        elif zone.evidence_score >= 40 and zone.behavior == "SUPPLY_ABSORPTION_PROXY":
            state = "DISTRIBUTION_ACTIVE"
        else:
            state = "DISTRIBUTION_CANDIDATE"
    else:
        state = "NEUTRAL"

    active_episode = zone.episodes[-1] if zone.episodes else None

    price_relation = None
    current_market_role = None
    selection_reason = None
    distance_pct = None
    distance_atr = None
    sessions_since = None
    if with_context and current_candle is not None and config is not None:
        recent = recent_candles or []
        price_relation = _price_relation(
            zone, current_candle, current_atr, recent, config
        )
        current_market_role = _current_market_role(zone, price_relation)
        selection_reason, distance_pct, distance_atr, sessions_since = (
            _selection_metadata(
                zone, current_candle, current_atr, date_to_index or {}, config
            )
        )

    return CurrentZoneState(
        state=state,
        evidence_score=zone.evidence_score,
        detected_at=zone.first_detected_at,
        confirmation_price=zone.confirmation_price,
        invalidation_price=zone.invalidation_price,
        transition_reasons=[item.code for item in zone.evidence],
        active_zone_id=zone.zone_id,
        active_episode_id=active_episode.episode_id if active_episode else None,
        current_market_role=current_market_role,
        price_relation=price_relation,
        selection_reason=selection_reason,
        distance_to_zone_percent=(
            round(distance_pct, 4) if distance_pct is not None else None
        ),
        distance_to_zone_atr=(
            round(distance_atr, 4) if distance_atr is not None else None
        ),
        sessions_since_last_contact=sessions_since,
        confirmation_hold_sessions=(
            config.confirmation_hold_sessions if with_context and config else None
        ),
        invalidation_hold_sessions=(
            config.invalidation_hold_sessions if with_context and config else None
        ),
    )


class _AnalysisBundle(NamedTuple):
    all_zones: list[VolumeZone]
    highlighted_ids: list[str]
    current_state: CurrentZoneState
    active_zone: VolumeZone | None
    profile: list[VolumeProfileBin]
    structural_profile: list[VolumeProfileBin]
    structural_metadata: ProfileMetadata | None
    active_metadata: ProfileMetadata | None
    nearest_above: VolumeZone | None = None
    nearest_below: VolumeZone | None = None


def _profile_metadata(
    mode: str,
    weighting: str,
    half_life: int | None,
    lookback: int | None,
    bins: list[PriceBin],
    config: VolumeZoneConfig,
    candles: list[OhlcvCandle],
) -> ProfileMetadata:
    if lookback is None:
        history_start = candles[0].date if candles else None
    else:
        start_idx = max(0, len(candles) - lookback)
        history_start = candles[start_idx].date if candles else None
    return ProfileMetadata(
        mode=mode,
        weighting=weighting,
        half_life_sessions=half_life,
        lookback_sessions=lookback,
        bin_count=len(bins),
        bin_strategy=config.price_bin_strategy,
        relative_volume_window=config.volume_median_window,
        history_start=history_start,
        history_end=candles[-1].date if candles else None,
    )


def _analyze_valid_candles(
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
    max_zones: int,
    free_float: FreeFloatSnapshot | None,
    with_display_profiles: bool = True,
) -> _AnalysisBundle:
    # Detection draws candidates from BOTH profiles: the structural profile
    # (full history, no decay, activity normalized) anchors long-term dwell
    # zones, the active profile (decayed volume) restores historical/high-price
    # zones that activity normalization alone cannot see.
    structural_bins, context = build_volume_profile(
        candles,
        config,
        half_life_sessions=config.structural_half_life_sessions,
        weighting="activity_normalized",
    )
    active_bins, _ = build_volume_profile(
        candles,
        config,
        half_life_sessions=config.active_half_life_sessions,
        weighting="time_decay",
        lookback_sessions=config.active_profile_lookback_sessions,
        context=context,
    )
    zones = detect_volume_zones(
        candles,
        structural_bins,
        active_bins,
        context,
        config,
        free_float_shares=free_float.float_shares if free_float is not None else None,
    )
    current_candle = candles[-1]
    current_price = current_candle.close
    current_atr = context.atr[-1] if context.atr else 0.0
    date_to_index = {candle.date: candle.index for candle in candles}
    recent_candles = candles[-config.active_zone_recent_sessions:]
    active_zone = _select_active_zone(zones, current_candle, current_atr, date_to_index, config)
    # A zone that price has decisively broken through is no longer the active
    # interaction - it becomes an overhead/underfoot level (nearest_*), not the
    # active zone. It still appears in `zones`/nearest, just not as active.
    if active_zone is not None:
        relation = _price_relation(
            active_zone, current_candle, current_atr, recent_candles, config
        )
        if relation in {"BROKEN_UP", "BROKEN_DOWN"}:
            active_zone = None
    current_state = _current_state_for_zone(
        active_zone,
        current_candle=current_candle,
        current_atr=current_atr,
        recent_candles=recent_candles,
        date_to_index=date_to_index,
        config=config,
        with_context=with_display_profiles,
    )
    highlighted = _visible_zones(zones, active_zone, current_price, max_zones)
    highlighted_ids = [zone.zone_id for zone in highlighted]

    if not with_display_profiles:
        return _AnalysisBundle(
            zones, highlighted_ids, current_state, active_zone,
            [], [], None, None, None, None,
        )

    all_zones = _finalize_zones(
        zones, highlighted_ids, active_zone, current_candle,
        current_atr, recent_candles, config,
    )
    if active_zone is not None:
        active_zone = next(
            (z for z in all_zones if z.zone_id == active_zone.zone_id), active_zone,
        )
    nearest_above, nearest_below = _nearest_zones(all_zones, current_price)

    profile = _profile_bins(active_bins)
    structural_profile = _profile_bins(structural_bins)
    structural_metadata = _profile_metadata(
        "STRUCTURAL", "ACTIVITY_NORMALIZED",
        config.structural_half_life_sessions, None,
        structural_bins, config, candles,
    )
    active_metadata = _profile_metadata(
        "ACTIVE", "TIME_DECAY",
        config.active_half_life_sessions, config.active_profile_lookback_sessions,
        active_bins, config, candles,
    )
    return _AnalysisBundle(
        all_zones, highlighted_ids, current_state, active_zone, profile,
        structural_profile, structural_metadata, active_metadata,
        nearest_above, nearest_below,
    )


def _profile_bins(bins: list[PriceBin]) -> list[VolumeProfileBin]:
    max_weighted = max((item.weighted_volume for item in bins), default=0.0)
    if max_weighted <= 0:
        return []
    return [
        VolumeProfileBin(
            price_low=round(item.low, 4),
            price_high=round(item.high, 4),
            center_price=round(item.center, 4),
            raw_volume=round(item.raw_volume, 3),
            weighted_volume=round(item.weighted_volume, 3),
            activity_score=round(item.weighted_volume / max_weighted * 100.0, 3),
            contributing_sessions=len({c.session_index for c in item.contributions}),
        )
        for item in bins
        if item.raw_volume > 0
    ]


def _timeline(
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
    free_float: FreeFloatSnapshot | None,
    balance_series: list[float | None],
    compute_state: bool,
) -> list[TimelinePoint]:
    """Emit one point per session over the full requested range.

    ``evidence_balance`` always comes from the cheap, full-range causal series
    (the only field the chart histogram renders). The per-prefix walk-forward
    lifecycle ``state`` is O(n^2) on long histories, so it is computed only in
    ``backtest`` mode; chart modes ship balance-only points (state neutral).
    """
    points: list[TimelinePoint] = []
    point_start = config.min_history_sessions - 1
    for idx in range(point_start, len(candles)):
        if compute_state:
            prefix = [
                OhlcvCandle(
                    date=item.date, open=item.open, high=item.high,
                    low=item.low, close=item.close, volume=item.volume, index=pos,
                )
                for pos, item in enumerate(candles[: idx + 1])
            ]
            state = _analyze_valid_candles(
                prefix, config, max_zones=1, free_float=free_float,
                with_display_profiles=False,
            ).current_state
            points.append(
                TimelinePoint(
                    date=candles[idx].date,
                    state=state.state,
                    evidence_score=state.evidence_score,
                    evidence_balance=balance_series[idx],
                    active_zone_id=state.active_zone_id,
                    active_episode_id=state.active_episode_id,
                    confirmation_price=state.confirmation_price,
                    invalidation_price=state.invalidation_price,
                    transition_reasons=state.transition_reasons,
                )
            )
        else:
            points.append(
                TimelinePoint(
                    date=candles[idx].date,
                    state="NEUTRAL",
                    evidence_score=0,
                    evidence_balance=balance_series[idx],
                )
            )
    return points


def analyze_volume_zones(
    candles: Iterable[object],
    symbol: str,
    mic: str,
    mode: AnalysisMode = "summary",
    include_timeline: bool = False,
    max_zones: int | None = None,
    config: VolumeZoneConfig = DEFAULT_CONFIG,
    free_float: FreeFloatSnapshot | None = None,
) -> VolumeZonesResponse:
    validation = normalize_ohlcv(candles)
    if len(validation.candles) < config.min_history_sessions:
        raise ValueError(
            f"At least {config.min_history_sessions} valid daily candles are required for volume-zone analysis."
        )

    # Highlighted-zone cap; the full set is always returned in `full`/`backtest`.
    limit = max_zones if max_zones is not None else config.maximum_visible_zones
    limit = max(1, min(20, limit))
    bundle = _analyze_valid_candles(validation.candles, config, limit, free_float)

    # Causal daily evidence balance drives both the lower panel and the
    # zone-independent accumulation/distribution phase detector (Etap 2).
    context = build_analysis_context(validation.candles, config)
    balance_series = rolling_directional_balance(
        validation.candles, context, config.evidence_balance_window
    )
    episodes = enrich_directional_phases(
        link_episodes_to_zones(
            detect_directional_episodes(
                validation.candles, balance_series, context, config
            ),
            bundle.all_zones,
        ),
        validation.candles,
        config,
    )
    resolved_episodes = resolve_directional_phases(
        episodes, validation.candles, config
    )
    major_episodes = rank_major_directional_phases(
        resolved_episodes, validation.candles, config
    )

    want_timeline = include_timeline or mode == "backtest"
    if want_timeline:
        timeline = _timeline(
            validation.candles, config, free_float, balance_series,
            compute_state=mode == "backtest",
        )
    else:
        timeline = []

    backtest = (
        summarize_walk_forward(bundle.all_zones, timeline)
        if mode == "backtest" else None
    )

    # `full`/`backtest` return every detected zone; `summary` limits to the cap.
    if mode == "summary":
        highlighted_set = set(bundle.highlighted_ids)
        zones = [z for z in bundle.all_zones if z.zone_id in highlighted_set]
    else:
        zones = bundle.all_zones

    return VolumeZonesResponse(
        symbol=symbol.strip().upper(),
        mic=mic.strip().upper(),
        as_of=validation.candles[-1].date,
        calculation_version=CALCULATION_VERSION,
        configuration_version=CONFIGURATION_VERSION,
        data_quality=_data_quality(validation, free_float),
        current_state=bundle.current_state,
        active_zone=bundle.active_zone,
        zones=zones,
        highlighted_zone_ids=bundle.highlighted_ids,
        profile=bundle.profile,
        structural_profile=bundle.structural_profile,
        structural_profile_metadata=bundle.structural_metadata,
        active_profile_metadata=bundle.active_metadata,
        nearest_zone_above=bundle.nearest_above,
        nearest_zone_below=bundle.nearest_below,
        directional_episodes=episodes,
        resolved_directional_episodes=resolved_episodes,
        major_directional_phases=major_episodes,
        timeline=timeline,
        backtest=backtest,
    )
