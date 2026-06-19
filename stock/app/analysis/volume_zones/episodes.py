from __future__ import annotations

from datetime import date
from typing import Callable, NamedTuple

from app.schemas.volume_zones import DirectionalPhase, VolumeZone

from .config import VolumeZoneConfig
from .indicators import EPSILON
from .types import AnalysisContext, OhlcvCandle


class _BaseWindow(NamedTuple):
    start: int
    end: int
    score: float
    price_low: float
    price_high: float
    center: float


class _PhaseSpan(NamedTuple):
    start: int
    candidate: int
    end: int
    price_low: float
    price_high: float


def _weighted_percentile(pairs: list[tuple[float, float]], pct: float) -> float:
    """Value at ``pct`` of cumulative weight (pairs = list of (value, weight))."""
    if not pairs:
        return 0.0
    ordered = sorted(pairs, key=lambda item: item[0])
    total = sum(w for _, w in ordered)
    if total <= 0:
        values = [v for v, _ in ordered]
        return values[min(int(pct * len(values)), len(values) - 1)]
    target = pct * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return value
    return ordered[-1][0]


def _regime(
    balance_series: list[float | None], config: VolumeZoneConfig
) -> list[str]:
    """Per-day ACCUMULATION/DISTRIBUTION/NEUTRAL label with hysteresis.

    Enter a phase when |balance| exceeds ``phase_enter_threshold``; leave it only
    when balance falls back through ``phase_exit_threshold`` (so the state does
    not flip on every session). Warm-up (None) resets to NEUTRAL.
    """
    out: list[str] = []
    state = "NEUTRAL"
    enter = config.phase_enter_threshold
    exit_ = config.phase_exit_threshold
    for balance in balance_series:
        if balance is None:
            state = "NEUTRAL"
            out.append(state)
            continue
        if balance > enter:
            state = "ACCUMULATION"
        elif balance < -enter:
            state = "DISTRIBUTION"
        elif state == "ACCUMULATION" and balance < exit_:
            state = "NEUTRAL"
        elif state == "DISTRIBUTION" and balance > -exit_:
            state = "NEUTRAL"
        out.append(state)
    return out


def _transition_date(
    candles: list[OhlcvCandle],
    start_idx: int,
    confirmation: float,
    conf_side: str,
    invalidation: float,
    inval_side: str,
    config: VolumeZoneConfig,
) -> tuple[str | None, date | None]:
    """Return the first terminal lifecycle event from ``start_idx`` onward."""
    conf_streak = 0
    inval_streak = 0

    def crossed(close: float, price: float, side: str) -> bool:
        return close > price if side == "above" else close < price

    for idx in range(max(start_idx, 0), len(candles)):
        close = candles[idx].close
        if crossed(close, confirmation, conf_side):
            conf_streak += 1
        else:
            conf_streak = 0
        if crossed(close, invalidation, inval_side):
            inval_streak += 1
        else:
            inval_streak = 0

        if conf_streak >= config.confirmation_hold_sessions:
            return "CONFIRMED", candles[idx].date
        if inval_streak >= config.invalidation_hold_sessions:
            return "INVALIDATED", candles[idx].date
    return None, None


def _price_box_for_window(
    candles: list[OhlcvCandle],
    balance_series: list[float | None],
    start: int,
    end: int,
) -> tuple[float, float, float]:
    pairs = [
        (
            (candles[k].high + candles[k].low + candles[k].close) / 3.0,
            candles[k].volume * max(abs(balance_series[k] or 0.0), 0.10) + EPSILON,
        )
        for k in range(start, end + 1)
    ]
    price_low = _weighted_percentile(pairs, 0.15)
    price_high = _weighted_percentile(pairs, 0.85)
    center = _weighted_percentile(pairs, 0.50)
    if price_high < price_low:
        price_low, price_high = price_high, price_low
    if price_high - price_low < EPSILON:
        price_low = min(candles[k].low for k in range(start, end + 1))
        price_high = max(candles[k].high for k in range(start, end + 1))
    return price_low, price_high, center


def _score_base_window(
    candles: list[OhlcvCandle],
    balance_series: list[float | None],
    context: AnalysisContext,
    start: int,
    end: int,
    signal_start: int,
    is_acc: bool,
    config: VolumeZoneConfig,
) -> _BaseWindow | None:
    length = end - start + 1
    if length < config.phase_base_min_sessions:
        return None

    sample = candles[start: end + 1]
    atr_values = [max(context.atr[k], EPSILON) for k in range(start, end + 1)]
    atr = sum(atr_values) / len(atr_values)
    low = min(c.low for c in sample)
    high = max(c.high for c in sample)
    center = max((low + high) / 2.0, EPSILON)
    width = high - low
    width_atr = width / atr
    width_pct = width / center
    trend_atr = abs(sample[-1].close - sample[0].close) / atr
    if width_atr > config.phase_base_max_range_atr:
        return None
    if width_pct > config.phase_base_max_range_pct:
        return None
    if trend_atr > config.phase_base_max_trend_atr:
        return None

    compression = sum(
        1
        for candle, atr_value in zip(sample, atr_values, strict=True)
        if (candle.high - candle.low) <= atr_value * 1.50
    ) / length
    if compression < config.phase_base_min_compression_share:
        return None

    tolerance = max(atr * 0.35, width * 0.12, EPSILON)
    lower_touches = sum(1 for c in sample if min(c.low, c.close) <= low + tolerance)
    upper_touches = sum(1 for c in sample if max(c.high, c.close) >= high - tolerance)
    boundary_touches = lower_touches + upper_touches
    if boundary_touches < config.phase_base_min_boundary_touches:
        return None

    balances = [balance_series[k] for k in range(start, end + 1) if balance_series[k] is not None]
    signed_pressure = 0.0
    if balances:
        avg_balance = sum(balances) / len(balances)
        signed_pressure = avg_balance if is_acc else -avg_balance

    price_low, price_high, price_center = _price_box_for_window(
        candles, balance_series, start, end
    )
    cap = min(
        config.phase_max_height_atr * atr,
        config.phase_max_height_pct * max(price_center, EPSILON),
    )
    if price_high - price_low > cap:
        half = cap / 2.0
        price_low = price_center - half
        price_high = price_center + half

    range_score = 1.0 - min(1.0, width_atr / config.phase_base_max_range_atr)
    trend_score = 1.0 - min(1.0, trend_atr / max(config.phase_base_max_trend_atr, EPSILON))
    touch_score = min(1.0, boundary_touches / 8.0)
    recency_score = 1.0 - min(
        1.0,
        max(0, signal_start - end) / max(config.phase_base_lookback_sessions, 1),
    )
    pressure_score = max(0.0, min(1.0, signed_pressure))
    late_penalty = max(0, end - signal_start) / max(config.phase_base_lookback_sessions, 1)
    score = (
        range_score * 0.30
        + trend_score * 0.24
        + compression * 0.16
        + touch_score * 0.12
        + recency_score * 0.14
        + pressure_score * 0.10
        - late_penalty * 0.18
    )
    return _BaseWindow(start, end, score, price_low, price_high, price_center)


def _find_base_window(
    candles: list[OhlcvCandle],
    balance_series: list[float | None],
    context: AnalysisContext,
    signal_start: int,
    signal_end: int,
    is_acc: bool,
    config: VolumeZoneConfig,
) -> _BaseWindow | None:
    earliest = max(0, signal_start - config.phase_base_lookback_sessions)
    latest = min(signal_end, len(candles) - 1)

    def best_for_end_range(first_end: int, last_end: int) -> _BaseWindow | None:
        best: _BaseWindow | None = None
        for end in range(max(first_end, earliest), last_end + 1):
            min_start = max(earliest, end - config.phase_base_lookback_sessions + 1)
            for start in range(min_start, end - config.phase_base_min_sessions + 2):
                candidate = _score_base_window(
                    candles, balance_series, context, start, end,
                    signal_start, is_acc, config,
                )
                if candidate is not None and (
                    best is None or candidate.score > best.score
                ):
                    best = candidate
        return best

    # Prefer a base already visible when the pressure regime starts. If the
    # pressure appears on the breakout candle, this anchors the box to the prior
    # consolidation instead of to the move itself.
    pre_signal = best_for_end_range(
        earliest + config.phase_base_min_sessions - 1,
        max(earliest, signal_start - 1),
    )
    if pre_signal is not None:
        return pre_signal

    # Fallback: pressure can start inside the base, so search the early/whole
    # regime but penalize later boxes that follow the move.
    return best_for_end_range(earliest + config.phase_base_min_sessions - 1, latest)


def detect_directional_episodes(
    candles: list[OhlcvCandle],
    balance_series: list[float | None],
    context: AnalysisContext,
    config: VolumeZoneConfig,
) -> list[DirectionalPhase]:
    """Detect accumulation/distribution phases from the daily evidence balance.

    Independent of profile zones: a phase can exist where no liquidity zone
    formed. The pressure regime detects the candidate, then the phase is
    anchored to a compact base visible before or early in that regime. The
    lifecycle status reflects the first confirmation/invalidation transition
    known as of the requested history.
    """
    regime = _regime(balance_series, config)
    phases: list[DirectionalPhase] = []
    n = len(candles)
    i = 0
    phase_index = 0
    while i < n:
        state = regime[i]
        if state == "NEUTRAL":
            i += 1
            continue
        j = i
        while j + 1 < n and regime[j + 1] == state:
            j += 1
        seg = [k for k in range(i, j + 1) if balance_series[k] is not None]
        if len(seg) < config.phase_candidate_min:
            i = j + 1
            continue

        is_acc = state == "ACCUMULATION"
        bvals = [balance_series[k] for k in seg]
        avg = sum(bvals) / len(bvals)
        peak = max(bvals) if is_acc else min(bvals)
        cumulative = sum(bvals)

        base = _find_base_window(
            candles, balance_series, context, seg[0], seg[-1], is_acc, config
        )
        if base is None:
            # A pressure burst without a base is not a full accumulation /
            # distribution phase. The lower evidence panel still shows it.
            i = j + 1
            continue

        price_low = base.price_low
        price_high = base.price_high
        center = base.center
        atr = max(context.atr[base.end], EPSILON)
        if is_acc:
            confirmation = price_high + config.confirmation_atr_buffer * atr
            invalidation = price_low - config.invalidation_atr_buffer * atr
            conf_side, inval_side = "above", "below"
        else:
            confirmation = price_low - config.confirmation_atr_buffer * atr
            invalidation = price_high + config.invalidation_atr_buffer * atr
            conf_side, inval_side = "below", "above"

        count = len(seg)
        qualifies = (
            count >= config.phase_min_sessions
            and abs(avg) >= config.phase_active_avg
        )

        terminal, terminal_date = _transition_date(
            candles, seg[0], confirmation, conf_side, invalidation, inval_side, config
        )
        confirmed_at = terminal_date if terminal == "CONFIRMED" else None
        invalidated_at = terminal_date if terminal == "INVALIDATED" else None

        if terminal == "CONFIRMED":
            status = "CONFIRMED"
            ended_at = confirmed_at
        elif terminal == "INVALIDATED":
            status = "INVALIDATED"
            ended_at = invalidated_at
        elif j == n - 1:
            status = "ACTIVE" if qualifies else "CANDIDATE"
            ended_at = candles[seg[-1]].date
        else:
            status = "CLOSED"
            ended_at = candles[seg[-1]].date

        active_at = (
            candles[seg[config.phase_min_sessions - 1]].date
            if qualifies and count >= config.phase_min_sessions
            else None
        )
        score = round(max(0.0, min(100.0, abs(avg) * 100.0)))
        phase_index += 1
        phases.append(
            DirectionalPhase(
                phase_id=f"phase-{phase_index}",
                phase="ACCUMULATION" if is_acc else "DISTRIBUTION",
                estimated_start_at=candles[base.start].date,
                base_end_at=candles[base.end].date,
                candidate_at=candles[seg[0]].date,
                active_at=active_at,
                ended_at=ended_at or candles[seg[-1]].date,
                confirmed_at=confirmed_at,
                invalidated_at=invalidated_at,
                price_low=round(price_low, 4),
                price_high=round(price_high, 4),
                center_price=round(center, 4),
                average_balance=round(avg, 4),
                peak_balance=round(peak, 4),
                cumulative_evidence=round(cumulative, 4),
                session_count=count,
                evidence_score=int(score),
                status=status,
                confirmation_price=round(confirmation, 4),
                invalidation_price=round(invalidation, 4),
                linked_zone_ids=[],
            )
        )
        i = j + 1
    return phases


def _date_index(candles: list[OhlcvCandle]) -> dict[date, int]:
    return {candle.date: idx for idx, candle in enumerate(candles)}


def _phase_span(phase: DirectionalPhase, indexes: dict[date, int]) -> _PhaseSpan:
    start_date = phase.estimated_start_at or phase.candidate_at
    return _PhaseSpan(
        indexes.get(start_date, 0),
        indexes.get(phase.candidate_at, indexes.get(start_date, 0)),
        indexes.get(phase.ended_at, indexes.get(phase.candidate_at, 0)),
        min(phase.price_low, phase.price_high),
        max(phase.price_low, phase.price_high),
    )


def _range_overlap(a_low: float, a_high: float, b_low: float, b_high: float) -> float:
    return max(0.0, min(a_high, b_high) - max(a_low, b_low))


def _overlap_fraction(
    a_low: float, a_high: float, b_low: float, b_high: float
) -> float:
    overlap = _range_overlap(a_low, a_high, b_low, b_high)
    narrower = min(max(a_high - a_low, EPSILON), max(b_high - b_low, EPSILON))
    return overlap / narrower


def _phase_time_overlap(a: _PhaseSpan, b: _PhaseSpan) -> float:
    overlap = max(0, min(a.end, b.end) - max(a.start, b.start) + 1)
    shorter = max(1, min(a.end - a.start + 1, b.end - b.start + 1))
    return overlap / shorter


def _phase_price_overlap(a: _PhaseSpan, b: _PhaseSpan) -> float:
    return _overlap_fraction(a.price_low, a.price_high, b.price_low, b.price_high)


def _significance_score(phase: DirectionalPhase) -> float:
    """Causal setup quality, retained as the legacy significance score."""
    balance = abs(phase.average_balance)
    cumulative = abs(phase.cumulative_evidence)
    duration_score = min(18.0, phase.session_count * 1.15)
    balance_score = min(34.0, balance * 85.0)
    cumulative_score = min(20.0, cumulative * 2.4)
    evidence_score = phase.evidence_score * 0.18
    status_score = {
        "CONFIRMED": 14.0,
        "ACTIVE": 8.0,
        "INVALIDATED": 5.0,
        "CLOSED": 2.0,
        "CANDIDATE": 0.0,
    }.get(phase.status, 0.0)
    link_score = min(6.0, len(phase.linked_zone_ids) * 3.0)
    return min(
        100.0,
        balance_score + cumulative_score + duration_score + evidence_score
        + status_score + link_score,
    )


def _pct_return(start: float, end: float) -> float | None:
    if abs(start) <= EPSILON:
        return None
    return ((end / start) - 1.0) * 100.0


def _phase_event_date(phase: DirectionalPhase) -> date:
    return phase.confirmed_at or phase.candidate_at


def _outcome_metrics(
    phase: DirectionalPhase,
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
) -> dict[str, float | int | None]:
    indexes = _date_index(candles)
    event_date = _phase_event_date(phase)
    event_idx = indexes.get(event_date)
    if event_idx is None:
        return {
            "historical_outcome_score": None,
            "subsequent_return_20": None,
            "subsequent_return_60": None,
            "maximum_favorable_excursion": None,
            "maximum_adverse_excursion": None,
            "expected_direction_return": None,
            "opposite_move_penalty": None,
            "outcome_lookahead_sessions": None,
        }

    max_horizon = config.phase_outcome_long_sessions
    last_idx = min(event_idx + max_horizon, len(candles) - 1)
    lookahead = last_idx - event_idx
    if lookahead < config.phase_outcome_short_sessions:
        return {
            "historical_outcome_score": None,
            "subsequent_return_20": None,
            "subsequent_return_60": None,
            "maximum_favorable_excursion": None,
            "maximum_adverse_excursion": None,
            "expected_direction_return": None,
            "opposite_move_penalty": None,
            "outcome_lookahead_sessions": lookahead,
        }

    start = candles[event_idx].close
    idx20 = min(event_idx + config.phase_outcome_short_sessions, len(candles) - 1)
    idx60 = min(event_idx + config.phase_outcome_long_sessions, len(candles) - 1)
    ret20 = _pct_return(start, candles[idx20].close)
    ret60 = _pct_return(start, candles[idx60].close)
    future_closes = [candle.close for candle in candles[event_idx:last_idx + 1]]
    if phase.phase == "ACCUMULATION":
        mfe = _pct_return(start, max(future_closes))
        mae = _pct_return(start, min(future_closes))
        expected_return = ret60
    else:
        downside = _pct_return(start, min(future_closes))
        upside = _pct_return(start, max(future_closes))
        mfe = -downside if downside is not None else None
        mae = -upside if upside is not None else None
        expected_return = -ret60 if ret60 is not None else None

    direction_ret20 = ret20 if phase.phase == "ACCUMULATION" else (
        -ret20 if ret20 is not None else None
    )
    direction_ret60 = expected_return
    favorable = max(0.0, mfe or 0.0)
    adverse = max(0.0, -(mae or 0.0))
    setup_score = phase.setup_score if phase.setup_score is not None else _significance_score(phase)
    ret20_score = min(18.0, max(0.0, direction_ret20 or 0.0) * 1.20)
    ret60_score = min(26.0, max(0.0, direction_ret60 or 0.0) * 0.85)
    mfe_score = min(26.0, favorable * 1.10)
    adverse_penalty = min(35.0, adverse * 1.20)
    breakout_score = 12.0 if phase.status == "CONFIRMED" else 0.0
    follow_through_score = (
        10.0
        if (direction_ret20 or 0.0) > 0.0 and (direction_ret60 or 0.0) > 0.0
        else 0.0
    )
    incomplete_factor = min(1.0, lookahead / max(config.phase_outcome_long_sessions, 1))
    status_penalty = 20.0 if phase.status == "INVALIDATED" else 0.0
    outcome_score = (
        setup_score * 0.12
        + breakout_score
        + ret20_score
        + ret60_score
        + mfe_score
        + follow_through_score
        - adverse_penalty
        - status_penalty
    ) * incomplete_factor

    return {
        "historical_outcome_score": round(max(0.0, min(100.0, outcome_score)), 3),
        "subsequent_return_20": round(ret20, 4) if ret20 is not None else None,
        "subsequent_return_60": round(ret60, 4) if ret60 is not None else None,
        "maximum_favorable_excursion": round(favorable, 4),
        "maximum_adverse_excursion": round(-(adverse), 4),
        "expected_direction_return": round(direction_ret60, 4)
        if direction_ret60 is not None else None,
        "opposite_move_penalty": round(adverse, 4),
        "outcome_lookahead_sessions": lookahead,
    }


def enrich_directional_phases(
    phases: list[DirectionalPhase],
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
) -> list[DirectionalPhase]:
    enriched: list[DirectionalPhase] = []
    for phase in phases:
        setup_score = round(_significance_score(phase), 3)
        update = {
            "setup_score": setup_score,
            "significance_score": setup_score,
            **_outcome_metrics(
                phase.model_copy(update={"setup_score": setup_score}),
                candles,
                config,
            ),
        }
        enriched.append(phase.model_copy(update=update))
    return enriched


def _first_date(*values: date | None) -> date | None:
    dates = [value for value in values if value is not None]
    return min(dates) if dates else None


def _last_date(*values: date | None) -> date | None:
    dates = [value for value in values if value is not None]
    return max(dates) if dates else None


def _phase_status(phases: list[DirectionalPhase]) -> str:
    if any(phase.status == "ACTIVE" for phase in phases):
        return "ACTIVE"
    if any(phase.status == "CONFIRMED" for phase in phases):
        return "CONFIRMED"
    if any(phase.status == "INVALIDATED" for phase in phases):
        return "INVALIDATED"
    if any(phase.status == "CANDIDATE" for phase in phases):
        return "CANDIDATE"
    return "CLOSED"


def _merge_phase_group(phases: list[DirectionalPhase], phase_id: str) -> DirectionalPhase:
    if len(phases) == 1:
        return phases[0].model_copy(update={"phase_id": phase_id})

    total_sessions = max(1, sum(phase.session_count for phase in phases))
    avg = sum(phase.average_balance * phase.session_count for phase in phases) / total_sessions
    cumulative = sum(phase.cumulative_evidence for phase in phases)
    peak = (
        max(phase.peak_balance for phase in phases)
        if phases[0].phase == "ACCUMULATION"
        else min(phase.peak_balance for phase in phases)
    )
    low = min(phase.price_low for phase in phases)
    high = max(phase.price_high for phase in phases)
    center = sum(phase.center_price * phase.session_count for phase in phases) / total_sessions
    status = _phase_status(phases)
    confirmed_at = _first_date(*(phase.confirmed_at for phase in phases))
    invalidated_at = None if confirmed_at is not None else _first_date(
        *(phase.invalidated_at for phase in phases)
    )
    ended_at = _last_date(*(phase.ended_at for phase in phases)) or phases[-1].ended_at
    active_at = _first_date(*(phase.active_at for phase in phases))
    linked = sorted({zone_id for phase in phases for zone_id in phase.linked_zone_ids})
    score = round(max(0.0, min(100.0, abs(avg) * 100.0)))

    return phases[0].model_copy(
        update={
            "phase_id": phase_id,
            "estimated_start_at": _first_date(*(phase.estimated_start_at for phase in phases)),
            "base_end_at": _last_date(*(phase.base_end_at for phase in phases)),
            "candidate_at": _first_date(*(phase.candidate_at for phase in phases)) or phases[0].candidate_at,
            "active_at": active_at,
            "ended_at": ended_at,
            "confirmed_at": confirmed_at,
            "invalidated_at": invalidated_at,
            "price_low": round(low, 4),
            "price_high": round(high, 4),
            "center_price": round(center, 4),
            "average_balance": round(avg, 4),
            "peak_balance": round(peak, 4),
            "cumulative_evidence": round(cumulative, 4),
            "session_count": total_sessions,
            "evidence_score": int(score),
            "status": status,
            "linked_zone_ids": linked,
        }
    )


def _merge_same_direction(
    phases: list[DirectionalPhase],
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
) -> list[DirectionalPhase]:
    if not phases:
        return []

    indexes = _date_index(candles)
    ordered = sorted(phases, key=lambda phase: _phase_span(phase, indexes).start)
    groups: list[list[DirectionalPhase]] = []

    for phase in ordered:
        if not groups:
            groups.append([phase])
            continue
        prev = groups[-1][-1]
        prev_span = _phase_span(prev, indexes)
        span = _phase_span(phase, indexes)
        gap = span.start - prev_span.end - 1
        price_overlap = _phase_price_overlap(prev_span, span)
        same_direction = phase.phase == prev.phase
        can_merge = (
            same_direction
            and gap <= config.phase_merge_gap_sessions
            and price_overlap >= config.phase_merge_price_overlap_fraction
        )
        if can_merge:
            groups[-1].append(phase)
        else:
            groups.append([phase])

    return [
        _merge_phase_group(group, f"resolved-phase-{idx}")
        for idx, group in enumerate(groups, start=1)
    ]


def _conflicts(
    left: DirectionalPhase,
    right: DirectionalPhase,
    indexes: dict[date, int],
    config: VolumeZoneConfig,
) -> bool:
    if left.phase == right.phase:
        return False
    left_span = _phase_span(left, indexes)
    right_span = _phase_span(right, indexes)
    time_overlap = _phase_time_overlap(left_span, right_span)
    price_overlap = _phase_price_overlap(left_span, right_span)
    return (
        time_overlap >= config.phase_conflict_time_overlap_fraction
        and price_overlap >= config.phase_conflict_price_overlap_fraction
    )


def _resolve_opposites(
    phases: list[DirectionalPhase],
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
    score_fn: Callable[[DirectionalPhase], float] = _significance_score,
) -> list[DirectionalPhase]:
    indexes = _date_index(candles)
    remaining = list(phases)
    removed: set[str] = set()

    for i, left in enumerate(remaining):
        if left.phase_id in removed:
            continue
        for right in remaining[i + 1:]:
            if right.phase_id in removed or not _conflicts(left, right, indexes, config):
                continue
            left_score = score_fn(left)
            right_score = score_fn(right)
            if abs(left_score - right_score) <= config.phase_conflict_ambiguous_margin:
                removed.add(left.phase_id)
                removed.add(right.phase_id)
                break
            loser = right if left_score > right_score else left
            removed.add(loser.phase_id)
            if loser.phase_id == left.phase_id:
                break

    return [phase for phase in remaining if phase.phase_id not in removed]


def _apply_cooldown(
    phases: list[DirectionalPhase],
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
    score_fn: Callable[[DirectionalPhase], float] = _significance_score,
) -> list[DirectionalPhase]:
    indexes = _date_index(candles)
    accepted: list[DirectionalPhase] = []
    for phase in sorted(phases, key=lambda item: _phase_span(item, indexes).start):
        span = _phase_span(phase, indexes)
        rejected = False
        for prev in reversed(accepted):
            prev_span = _phase_span(prev, indexes)
            if phase.phase == prev.phase:
                continue
            gap = span.start - prev_span.end - 1
            if gap < 0 or gap > config.phase_cooldown_sessions:
                continue
            if _phase_price_overlap(prev_span, span) < config.phase_conflict_price_overlap_fraction:
                continue
            if score_fn(phase) <= score_fn(prev):
                rejected = True
                break
        if not rejected:
            accepted.append(phase)
    return accepted


def resolve_directional_phases(
    phases: list[DirectionalPhase],
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
) -> list[DirectionalPhase]:
    """Return sparse, conflict-resolved phases for the user-facing chart.

    ``detect_directional_episodes`` intentionally emits candidates from the
    evidence regime. This resolver is the boundary between noisy internal
    candidates and the final A/D layer: same-direction nearby candidates are
    merged, weak phases are filtered, overlapping opposite phases are resolved,
    and rapid opposite flips in the same area are suppressed.
    """
    merged = _merge_same_direction(phases, candles, config)
    significant = [
        phase for phase in merged
        if _significance_score(phase) >= config.phase_render_min_significance
    ]
    conflict_free = _resolve_opposites(significant, candles, config)
    cooled = _apply_cooldown(conflict_free, candles, config)
    ordered = sorted(cooled, key=lambda item: item.candidate_at)
    resolved = [
        phase.model_copy(
            update={
                "phase_id": f"resolved-phase-{idx}",
            }
        )
        for idx, phase in enumerate(ordered, start=1)
    ]
    return enrich_directional_phases(resolved, candles, config)


def _historical_outcome_score(phase: DirectionalPhase) -> float:
    return phase.historical_outcome_score or 0.0


def _is_major_duplicate(
    left: DirectionalPhase,
    right: DirectionalPhase,
    indexes: dict[date, int],
    config: VolumeZoneConfig,
) -> bool:
    left_span = _phase_span(left, indexes)
    right_span = _phase_span(right, indexes)
    start_gap = abs(right_span.start - left_span.start)
    time_overlap = _phase_time_overlap(left_span, right_span)
    price_overlap = _phase_price_overlap(left_span, right_span)
    return (
        price_overlap >= config.phase_conflict_price_overlap_fraction
        and (
            time_overlap >= config.phase_conflict_time_overlap_fraction
            or start_gap <= config.phase_major_min_spacing_sessions
        )
    )


def _major_sort_key(phase: DirectionalPhase) -> tuple[float, float, date]:
    return (
        -(phase.historical_outcome_score or 0.0),
        -(phase.setup_score or 0.0),
        phase.candidate_at,
    )


def _append_major_phase(
    selected: list[DirectionalPhase],
    phase: DirectionalPhase,
    indexes: dict[date, int],
    config: VolumeZoneConfig,
) -> bool:
    if len(selected) >= config.phase_major_max_count:
        return False
    if any(_is_major_duplicate(phase, accepted, indexes, config) for accepted in selected):
        return False
    selected.append(phase)
    return True


def _coverage_phase(
    phases: list[DirectionalPhase],
    config: VolumeZoneConfig,
) -> DirectionalPhase:
    best = sorted(phases, key=_major_sort_key)[0]
    floor = max(
        config.phase_major_min_outcome_score,
        (best.historical_outcome_score or 0.0) * 0.75,
    )
    early = [
        phase for phase in sorted(phases, key=lambda item: item.candidate_at)
        if (phase.historical_outcome_score or 0.0) >= floor
    ]
    return early[0] if early else best


def _first_break_above(
    candles: list[OhlcvCandle],
    start_idx: int,
    end_idx: int,
    price: float,
) -> int | None:
    for idx in range(max(0, start_idx), min(end_idx, len(candles) - 1) + 1):
        if candles[idx].close > price:
            return idx
    return None


def _swing_low_major_fallbacks(
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
) -> list[DirectionalPhase]:
    phases: list[DirectionalPhase] = []
    if len(candles) < (
        config.phase_swing_low_prior_sessions
        + config.phase_swing_low_forward_sessions
        + 1
    ):
        return phases

    half = config.phase_swing_low_window_sessions
    prior = config.phase_swing_low_prior_sessions
    forward = config.phase_swing_low_forward_sessions
    last_idx = len(candles) - forward - 1

    for idx in range(prior, max(prior, last_idx) + 1):
        window_start = max(0, idx - half)
        window_end = min(len(candles) - 1, idx + half)
        low = candles[idx].low
        if low > min(candle.low for candle in candles[window_start:window_end + 1]) + EPSILON:
            continue

        prior_high = max(candle.close for candle in candles[idx - prior:idx])
        drawdown = _pct_return(prior_high, candles[idx].close)
        if drawdown is None or drawdown > -config.phase_swing_low_min_prior_drawdown_pct:
            continue

        future_end = min(len(candles) - 1, idx + forward)
        future_high = max(candle.close for candle in candles[idx + 1:future_end + 1])
        followthrough = _pct_return(candles[idx].close, future_high)
        if followthrough is None or followthrough < config.phase_swing_low_min_followthrough_pct:
            continue

        base_start = max(0, idx - config.phase_swing_low_base_before_sessions)
        base_end = min(len(candles) - 1, idx + config.phase_swing_low_base_after_sessions)
        sample = candles[base_start:base_end + 1]
        price_low = min(candle.low for candle in sample)
        price_high = max(candle.high for candle in sample)
        center = (price_low + price_high) / 2.0
        confirmation_idx = _first_break_above(
            candles, base_end + 1, future_end, price_high
        )
        if confirmation_idx is None:
            continue

        setup = min(70.0, 38.0 + max(0.0, -drawdown) * 0.45 + followthrough * 0.35)
        phases.append(
            DirectionalPhase(
                phase_id=f"swing-low-{idx}",
                phase="ACCUMULATION",
                estimated_start_at=candles[base_start].date,
                base_end_at=candles[base_end].date,
                candidate_at=candles[idx].date,
                active_at=None,
                ended_at=candles[base_end].date,
                confirmed_at=candles[confirmation_idx].date,
                invalidated_at=None,
                price_low=round(price_low, 4),
                price_high=round(price_high, 4),
                center_price=round(center, 4),
                average_balance=0.0,
                peak_balance=0.0,
                cumulative_evidence=0.0,
                session_count=base_end - base_start + 1,
                evidence_score=round(setup),
                status="CONFIRMED",
                confirmation_price=round(price_high, 4),
                invalidation_price=round(price_low, 4),
                linked_zone_ids=[],
                setup_score=round(setup, 3),
                significance_score=round(setup, 3),
            )
        )

    return enrich_directional_phases(phases, candles, config)


def rank_major_directional_phases(
    phases: list[DirectionalPhase],
    candles: list[OhlcvCandle],
    config: VolumeZoneConfig,
) -> list[DirectionalPhase]:
    """Return after-the-fact phases that explain meaningful follow-through.

    This layer intentionally uses future returns/MFE/MAE and is therefore a
    historical annotation layer. Live/current views must use setup_score and
    lifecycle status instead.
    """
    enriched = enrich_directional_phases(phases, candles, config)
    candidates = [
        phase for phase in enriched
        if phase.status == "CONFIRMED"
        and (phase.historical_outcome_score or 0.0) >= config.phase_major_min_outcome_score
    ]
    conflict_free = _resolve_opposites(
        candidates, candles, config, score_fn=_historical_outcome_score,
    )
    cooled = _apply_cooldown(
        conflict_free, candles, config, score_fn=_historical_outcome_score,
    )
    swing_fallbacks = [
        phase for phase in _swing_low_major_fallbacks(candles, config)
        if (phase.historical_outcome_score or 0.0) >= config.phase_major_min_outcome_score
    ]
    cooled = [*cooled, *swing_fallbacks]
    indexes = _date_index(candles)
    selected: list[DirectionalPhase] = []

    per_direction = min(
        config.phase_major_min_direction_count,
        max(1, config.phase_major_max_count // 3),
    )
    for direction in ("DISTRIBUTION", "ACCUMULATION"):
        for phase in sorted(
            [item for item in cooled if item.phase == direction],
            key=_major_sort_key,
        )[:per_direction]:
            _append_major_phase(selected, phase, indexes, config)

    period_groups: dict[tuple[int, str], list[DirectionalPhase]] = {}
    for phase in cooled:
        bucket = phase.candidate_at.year // config.phase_major_period_years
        period_groups.setdefault((bucket, phase.phase), []).append(phase)

    coverage_candidates = [
        _coverage_phase(group, config)
        for group in period_groups.values()
    ]
    for phase in sorted(coverage_candidates, key=_major_sort_key):
        _append_major_phase(selected, phase, indexes, config)

    for phase in sorted(cooled, key=_major_sort_key):
        _append_major_phase(selected, phase, indexes, config)

    ordered = sorted(selected, key=lambda item: item.candidate_at)
    return [
        phase.model_copy(update={"phase_id": f"major-phase-{idx}"})
        for idx, phase in enumerate(ordered, start=1)
    ]


def link_episodes_to_zones(
    episodes: list[DirectionalPhase], zones: list[VolumeZone]
) -> list[DirectionalPhase]:
    """Attach overlapping zone ids; a phase is still returned when it links none."""
    linked: list[DirectionalPhase] = []
    for phase in episodes:
        ids = [
            zone.zone_id
            for zone in zones
            if zone.price_low <= phase.price_high
            and zone.price_high >= phase.price_low
        ]
        linked.append(phase.model_copy(update={"linked_zone_ids": ids}))
    return linked
