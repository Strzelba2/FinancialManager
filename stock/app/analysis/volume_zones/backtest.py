from __future__ import annotations

from app.schemas.volume_zones import BacktestSummary, TimelinePoint, VolumeZone


def summarize_walk_forward(
    zones: list[VolumeZone],
    timeline: list[TimelinePoint],
) -> BacktestSummary:
    directional_zones = [
        zone for zone in zones
        if zone.behavior in {"DEMAND_ABSORPTION_PROXY", "SUPPLY_ABSORPTION_PROXY"}
    ]
    confirmed_states = sum(1 for point in timeline if point.state in {"MARKUP", "MARKDOWN"})
    invalidated_states = sum(1 for point in timeline if point.state in {"FAILED_ACCUMULATION", "FAILED_DISTRIBUTION"})
    candidate_states = sum(1 for point in timeline if point.state.endswith("_CANDIDATE"))
    state_changes = 0
    previous_state: str | None = None
    for point in timeline:
        if previous_state is not None and point.state != previous_state:
            state_changes += 1
        previous_state = point.state

    return BacktestSummary(
        evaluated_sessions=len(timeline),
        detected_zones=len(zones),
        directional_zones=len(directional_zones),
        neutral_zones=len(zones) - len(directional_zones),
        candidate_states=candidate_states,
        confirmed_states=confirmed_states,
        invalidated_states=invalidated_states,
        state_changes=state_changes,
        average_signal_delay_sessions=None,
        benchmark_notes=[
            "MVP reports deterministic walk-forward counts only.",
            "Benchmarks for breakout, relative-volume breakout, moving-average crosses, and randomized same-frequency signals are reserved for the validation extension.",
        ],
    )
