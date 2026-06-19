from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CALCULATION_VERSION = "1.5.1"
CONFIGURATION_VERSION = "1.4.1"


class VolumeZoneConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    volume_median_window: int = Field(default=30, ge=3, le=260)
    volume_percentile_window: int = Field(default=120, ge=10, le=520)
    atr_window: int = Field(default=14, ge=3, le=120)
    profile_half_life_sessions: int = Field(default=180, ge=1, le=2000)
    # Two-profile model (S3). ``structural_half_life_sessions=None`` means no decay
    # (the structural profile spans the full history); the active profile keeps decay.
    structural_half_life_sessions: int | None = Field(default=None, ge=1, le=100000)
    active_half_life_sessions: int = Field(default=504, ge=1, le=5000)
    active_profile_lookback_sessions: int = Field(default=756, ge=20, le=10000)
    price_bin_strategy: Literal[
        "percentage_bins",
        "atr_based_bins",
        "fixed_target_bin_count",
        "logarithmic_bins",
    ] = "logarithmic_bins"
    price_bin_percentage: float = Field(default=0.015, gt=0, le=0.25)
    target_bin_count: int = Field(default=80, ge=10, le=240)
    minimum_effective_sessions: float = Field(default=10.0, ge=1)
    minimum_active_weeks: int = Field(default=3, ge=1)
    minimum_activity_equivalent_sessions: float = Field(default=8.0, ge=1)
    maximum_dominant_session_share: float = Field(default=0.35, gt=0, le=1)
    minimum_consistency: float = Field(default=0.60, ge=0, le=1)
    candidate_balance_threshold: float = Field(default=0.20, ge=0, le=1)
    strong_balance_threshold: float = Field(default=0.40, ge=0, le=1)
    candidate_evidence_score_min: int = Field(default=40, ge=0, le=100)
    candidate_exit_threshold: float = Field(default=0.15, ge=0, le=1)
    confirmation_hold_sessions: int = Field(default=3, ge=1, le=20)
    invalidation_hold_sessions: int = Field(default=2, ge=1, le=20)
    # Lifecycle phases (S2). A candidate becomes ACTIVE only after the candidate
    # conditions hold for ``active_hold_sessions`` sessions; confirmation is counted
    # only from the entered-ACTIVE date forward.
    candidate_hold_sessions: int = Field(default=3, ge=1, le=60)
    active_hold_sessions: int = Field(default=5, ge=1, le=120)
    episode_inactivity_sessions: int = Field(default=20, ge=1, le=260)
    episode_departure_atr: float = Field(default=2.0, ge=0)
    maximum_episode_span_sessions: int = Field(default=120, ge=5, le=1000)
    active_zone_max_atr_distance: float = Field(default=1.5, ge=0, le=20)
    active_zone_recent_sessions: int = Field(default=30, ge=1, le=260)
    maximum_visible_zones: int = Field(default=5, ge=1, le=20)
    timeline_max_sessions: int = Field(default=260, ge=20, le=5000)
    recent_free_float_window_sessions: int = Field(default=120, ge=1, le=520)
    confirmation_atr_buffer: float = Field(default=0.30, ge=0, le=5)
    invalidation_atr_buffer: float = Field(default=0.20, ge=0, le=5)
    body_bin_bonus: float = Field(default=0.20, ge=0, le=2)
    close_bin_bonus: float = Field(default=0.25, ge=0, le=2)
    typical_price_bin_bonus: float = Field(default=0.15, ge=0, le=2)
    min_history_sessions: int = Field(default=25, ge=5, le=260)
    maximum_zones_to_score: int = Field(default=12, ge=1, le=50)
    # Detection quality (S4). Hard width caps and unambiguous local-minimum split.
    max_zone_width_atr: float = Field(default=6.0, ge=0.5, le=50)
    max_zone_width_pct: float = Field(default=0.18, gt=0, le=1)
    max_zone_price_range_share: float = Field(default=0.40, gt=0, le=1)
    min_local_minimum_drop: float = Field(default=0.35, ge=0, le=1)
    minimum_peak_separation_bins: int = Field(default=2, ge=1, le=50)
    minimum_child_bin_count: int = Field(default=2, ge=1, le=50)
    minimum_child_activity: float = Field(default=0.0, ge=0)
    # Two-profile detection: candidate bands from the structural and active
    # profiles are merged when their price ranges overlap by at least this
    # fraction of the narrower band.
    zone_merge_overlap_fraction: float = Field(default=0.40, gt=0, le=1)
    # Rolling window (sessions) for the causal per-day evidence-balance series
    # shown in the lower panel. Independent of zone selection.
    evidence_balance_window: int = Field(default=20, ge=3, le=260)
    # Directional phase (accumulation/distribution) detector over the daily
    # evidence-balance series, with hysteresis. Independent of profile zones.
    phase_enter_threshold: float = Field(default=0.25, gt=0, le=1)
    phase_exit_threshold: float = Field(default=0.10, ge=0, le=1)
    phase_candidate_min: int = Field(default=3, ge=1, le=60)
    phase_min_sessions: int = Field(default=8, ge=1, le=120)
    phase_active_avg: float = Field(default=0.30, gt=0, le=1)
    # Directional phases are anchored to a preceding/early base, not to the
    # whole later markup/markdown leg.
    phase_base_lookback_sessions: int = Field(default=120, ge=10, le=520)
    phase_base_min_sessions: int = Field(default=8, ge=3, le=120)
    phase_base_max_range_atr: float = Field(default=7.0, ge=1, le=50)
    phase_base_max_range_pct: float = Field(default=0.20, gt=0, le=1)
    phase_base_max_trend_atr: float = Field(default=3.5, ge=0, le=50)
    phase_base_min_boundary_touches: int = Field(default=3, ge=0, le=20)
    phase_base_min_compression_share: float = Field(default=0.45, ge=0, le=1)
    # Final safety cap: if a base still spans too much price, clamp around its
    # weighted-median center.
    phase_max_height_atr: float = Field(default=6.0, ge=0.5, le=50)
    phase_max_height_pct: float = Field(default=0.12, gt=0, le=1)
    # User-facing phase resolution. Raw candidates can be noisy; final chart
    # phases are merged, conflict-resolved, and significance-filtered.
    phase_merge_gap_sessions: int = Field(default=8, ge=0, le=60)
    phase_merge_price_overlap_fraction: float = Field(default=0.45, ge=0, le=1)
    phase_conflict_time_overlap_fraction: float = Field(default=0.35, ge=0, le=1)
    phase_conflict_price_overlap_fraction: float = Field(default=0.35, ge=0, le=1)
    phase_conflict_ambiguous_margin: float = Field(default=8.0, ge=0, le=100)
    phase_render_min_significance: float = Field(default=48.0, ge=0, le=100)
    phase_cooldown_sessions: int = Field(default=12, ge=0, le=120)
    # Historical phase ranking. This is deliberately separate from live setup
    # quality because returns/MFE/MAE use future candles and are annotations,
    # not causal signals.
    phase_outcome_short_sessions: int = Field(default=20, ge=1, le=260)
    phase_outcome_long_sessions: int = Field(default=60, ge=2, le=520)
    phase_major_min_outcome_score: float = Field(default=40.0, ge=0, le=100)
    phase_major_max_count: int = Field(default=28, ge=1, le=50)
    phase_major_min_direction_count: int = Field(default=4, ge=0, le=20)
    phase_major_period_years: int = Field(default=1, ge=1, le=10)
    phase_major_min_spacing_sessions: int = Field(default=35, ge=0, le=260)
    # Historical swing-low fallback for major annotations. Used only when a
    # major price base explains a large later move but the evidence-balance
    # state machine did not create a full accumulation setup.
    phase_swing_low_window_sessions: int = Field(default=70, ge=10, le=260)
    phase_swing_low_prior_sessions: int = Field(default=90, ge=20, le=520)
    phase_swing_low_forward_sessions: int = Field(default=90, ge=20, le=520)
    phase_swing_low_base_before_sessions: int = Field(default=18, ge=3, le=120)
    phase_swing_low_base_after_sessions: int = Field(default=8, ge=0, le=60)
    phase_swing_low_min_prior_drawdown_pct: float = Field(default=14.0, ge=0, le=100)
    phase_swing_low_min_followthrough_pct: float = Field(default=18.0, ge=0, le=300)
    # Price relation (S6).
    price_relation_approach_atr: float = Field(default=1.5, ge=0, le=20)
    price_relation_retest_atr: float = Field(default=0.5, ge=0, le=20)
    price_relation_break_hold_sessions: int = Field(default=2, ge=1, le=20)


DEFAULT_CONFIG = VolumeZoneConfig()
