from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AnalysisMode = Literal["summary", "full", "backtest"]
EvidenceDirection = Literal["ACCUMULATION", "DISTRIBUTION", "NEUTRAL"]
DataConfidence = Literal["high", "medium", "low"]
ZoneBehavior = Literal[
    "DEMAND_ABSORPTION_PROXY",
    "SUPPLY_ABSORPTION_PROXY",
    "NEUTRAL_LIQUIDITY",
    "INSUFFICIENT_DIRECTIONAL_EVIDENCE",
    "BROAD_NEUTRAL_LIQUIDITY",
]
DirectionLabel = Literal[
    "ACCUMULATION_CANDIDATE",
    "REACCUMULATION_CANDIDATE",
    "DISTRIBUTION_CANDIDATE",
    "REDISTRIBUTION_CANDIDATE",
    "DEMAND_ABSORPTION_CANDIDATE",
    "SUPPLY_ABSORPTION_CANDIDATE",
    "NEUTRAL_LIQUIDITY",
    "INSUFFICIENT_DIRECTIONAL_EVIDENCE",
]
ZoneStatus = Literal["ACTIVE", "CONFIRMED", "INVALIDATED", "DORMANT", "NEUTRAL"]
CurrentStateName = Literal[
    "NEUTRAL",
    "ACCUMULATION_CANDIDATE",
    "ACCUMULATION_ACTIVE",
    "MARKUP",
    "FAILED_ACCUMULATION",
    "REACCUMULATION_CANDIDATE",
    "REACCUMULATION_ACTIVE",
    "DISTRIBUTION_CANDIDATE",
    "DISTRIBUTION_ACTIVE",
    "MARKDOWN",
    "FAILED_DISTRIBUTION",
    "REDISTRIBUTION_CANDIDATE",
    "REDISTRIBUTION_ACTIVE",
]
LifecycleStatus = Literal[
    "CANDIDATE",
    "ACTIVE",
    "CONFIRMED",
    "INVALIDATED",
    "CLOSED",
]
CurrentMarketRole = Literal[
    "ACTIVE_DEMAND",
    "ACTIVE_SUPPLY",
    "FORMER_DEMAND_NOW_SUPPLY",
    "FORMER_SUPPLY_NOW_DEMAND",
    "HISTORICAL_SUPPORT",
    "HISTORICAL_RESISTANCE",
    "NEUTRAL_LIQUIDITY",
]
PriceRelation = Literal[
    "INSIDE_ZONE",
    "ABOVE_ZONE",
    "BELOW_ZONE",
    "APPROACHING_FROM_ABOVE",
    "APPROACHING_FROM_BELOW",
    "RETESTING_FROM_ABOVE",
    "RETESTING_FROM_BELOW",
    "BROKEN_UP",
    "BROKEN_DOWN",
]
QualityFailReason = Literal[
    "MINIMUM_EFFECTIVE_SESSIONS_NOT_MET",
    "MINIMUM_ACTIVE_WEEKS_NOT_MET",
    "MINIMUM_ACTIVITY_EQUIVALENT_SESSIONS_NOT_MET",
    "DOMINANT_SESSION_SHARE_EXCEEDED",
    "MINIMUM_CONSISTENCY_NOT_MET",
]
QualityGate = Literal["PASSED", "FAILED"]
DisplayClassification = Literal[
    "DIRECTIONAL",
    "INSUFFICIENT_DIRECTIONAL_EVIDENCE",
    "NEUTRAL_LIQUIDITY",
]
SelectionReason = Literal[
    "INSIDE_ZONE",
    "WITHIN_ATR_DISTANCE",
    "RECENT_CONTACT",
    "INSIDE_AND_RECENT",
]
DisplayRole = Literal[
    "ACTIVE",
    "NEAREST_DEMAND",
    "NEAREST_SUPPLY",
    "NEAREST_SUPPORT",
    "NEAREST_RESISTANCE",
    "STRONGEST_STRUCTURAL",
]
ProfileMode = Literal["STRUCTURAL", "ACTIVE"]
ProfileWeighting = Literal["TIME_DECAY", "ACTIVITY_NORMALIZED"]
SourceProfile = Literal["STRUCTURAL", "ACTIVE", "BOTH"]
DirectionalPhaseType = Literal["ACCUMULATION", "DISTRIBUTION"]
DirectionalPhaseStatus = Literal[
    "CANDIDATE",
    "ACTIVE",
    "CONFIRMED",
    "INVALIDATED",
    "CLOSED",
]


class ZoneEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    value: float | int | str
    direction: EvidenceDirection


class DataQuality(BaseModel):
    model_config = ConfigDict(frozen=True)

    ohlcv_interval: Literal["1d"] = "1d"
    historical_free_float_available: bool = False
    current_free_float_used: bool = False
    current_free_float_pct: float | None = None
    current_free_float_as_of: date | None = None
    current_float_shares: float | None = None
    current_free_float_source: str | None = None
    confidence: DataConfidence = "medium"
    input_rows: int = 0
    valid_rows: int = 0
    excluded_rows: int = 0
    duplicate_dates: list[date] = Field(default_factory=list)
    first_date: date | None = None
    last_date: date | None = None
    warnings: list[str] = Field(default_factory=list)


class CurrentZoneState(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: CurrentStateName
    evidence_score: int = Field(ge=0, le=100)
    detected_at: date | None = None
    confirmation_price: float | None = None
    invalidation_price: float | None = None
    transition_reasons: list[str] = Field(default_factory=list)
    active_zone_id: str | None = None
    active_episode_id: str | None = None
    # Current context (S6/S7). Additive, defaulted.
    current_market_role: CurrentMarketRole | None = None
    price_relation: PriceRelation | None = None
    selection_reason: SelectionReason | None = None
    distance_to_zone_percent: float | None = None
    distance_to_zone_atr: float | None = None
    sessions_since_last_contact: int | None = None
    confirmation_hold_sessions: int | None = None
    invalidation_hold_sessions: int | None = None


class VolumeZoneEpisode(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_id: str
    zone_id: str
    estimated_start_date: date
    first_detected_at: date
    last_active_at: date
    direction_assigned_at: date | None = None
    confirmed_at: date | None = None
    invalidated_at: date | None = None
    effective_sessions: float
    session_count: int
    active_weeks: int
    allocated_volume: float
    weighted_volume: float
    activity_equivalent_sessions: float
    demand_absorption_evidence: float
    supply_absorption_evidence: float
    evidence_balance: float
    consistency: float
    direction_label: DirectionLabel
    evidence_score: int = Field(ge=0, le=100)
    confidence: DataConfidence
    status: ZoneStatus
    confirmation_price: float | None = None
    invalidation_price: float | None = None
    evidence: list[ZoneEvidence] = Field(default_factory=list)
    # Identity / lifecycle separation (S1/S2/S5). Additive, defaulted.
    detected_signature: ZoneBehavior | None = None
    episode_signature: ZoneBehavior | None = None
    directional_classification_allowed: bool = True
    lifecycle_status: LifecycleStatus | None = None
    candidate_at: date | None = None
    entered_active_at: date | None = None
    raw_directional_score: int | None = None
    quality_gate: QualityGate | None = None
    quality_fail_reasons: list[QualityFailReason] = Field(default_factory=list)
    display_classification: DisplayClassification | None = None


class VolumeZone(BaseModel):
    model_config = ConfigDict(frozen=True)

    zone_id: str
    price_low: float
    price_high: float
    center_price: float
    estimated_start_date: date
    first_detected_at: date
    last_active_at: date
    raw_volume: float
    weighted_volume: float
    activity_score: float
    activity_equivalent_sessions: float
    effective_sessions: float
    active_weeks: int
    dominant_session_share: float
    freshness_score: float
    status: ZoneStatus
    behavior: ZoneBehavior
    direction_label: DirectionLabel
    evidence_score: int = Field(ge=0, le=100)
    evidence_balance: float
    consistency: float
    confirmation_price: float | None = None
    invalidation_price: float | None = None
    current_free_float_turnover: float | None = None
    current_free_float_turnover_is_estimate: bool = False
    evidence: list[ZoneEvidence] = Field(default_factory=list)
    episodes: list[VolumeZoneEpisode] = Field(default_factory=list)
    # Identity / lifecycle (mirrored from the active episode). Additive, defaulted.
    detected_signature: ZoneBehavior | None = None
    episode_signature: ZoneBehavior | None = None
    directional_classification_allowed: bool = True
    lifecycle_status: LifecycleStatus | None = None
    raw_directional_score: int | None = None
    quality_gate: QualityGate | None = None
    quality_fail_reasons: list[QualityFailReason] = Field(default_factory=list)
    display_classification: DisplayClassification | None = None
    # Display ordering (S7) and current (response-time) market role (S5/S6).
    display_priority: int | None = None
    display_role: DisplayRole | None = None
    current_market_role: CurrentMarketRole | None = None
    # Two-profile provenance (which profile(s) discovered the band) + strengths.
    source_profile: SourceProfile | None = None
    structural_strength: float | None = None
    active_strength: float | None = None
    current_relevance: float | None = None
    top_session_dates: list[date] = Field(default_factory=list)


class TimelinePoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    state: CurrentStateName
    evidence_score: int = Field(ge=0, le=100)
    # ``None`` during warm-up (insufficient data); a real number (sign preserved)
    # once the causal rolling window is available. 0 means computed-neutral.
    evidence_balance: float | None = None
    active_zone_id: str | None = None
    active_episode_id: str | None = None
    confirmation_price: float | None = None
    invalidation_price: float | None = None
    transition_reasons: list[str] = Field(default_factory=list)


class VolumeProfileBin(BaseModel):
    model_config = ConfigDict(frozen=True)

    price_low: float
    price_high: float
    center_price: float
    raw_volume: float
    weighted_volume: float
    activity_score: float
    contributing_sessions: int = 0


class ProfileMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: ProfileMode
    weighting: ProfileWeighting
    half_life_sessions: int | None = None
    lookback_sessions: int | None = None
    bin_count: int = 0
    bin_strategy: str = ""
    relative_volume_window: int = 0
    history_start: date | None = None
    history_end: date | None = None


class DirectionalPhase(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase_id: str
    phase: DirectionalPhaseType
    estimated_start_at: date | None = None
    base_end_at: date | None = None
    candidate_at: date
    active_at: date | None = None
    ended_at: date
    confirmed_at: date | None = None
    invalidated_at: date | None = None
    price_low: float
    price_high: float
    center_price: float
    average_balance: float
    peak_balance: float
    cumulative_evidence: float
    session_count: int
    evidence_score: int = Field(ge=0, le=100)
    status: DirectionalPhaseStatus
    confirmation_price: float | None = None
    invalidation_price: float | None = None
    linked_zone_ids: list[str] = Field(default_factory=list)
    setup_score: float | None = None
    historical_outcome_score: float | None = None
    subsequent_return_20: float | None = None
    subsequent_return_60: float | None = None
    maximum_favorable_excursion: float | None = None
    maximum_adverse_excursion: float | None = None
    expected_direction_return: float | None = None
    opposite_move_penalty: float | None = None
    outcome_lookahead_sessions: int | None = None
    # Backward-compatible alias retained for current clients. New UI should
    # prefer setup_score for live/setup quality and historical_outcome_score for
    # after-the-fact swing annotation.
    significance_score: float | None = None


class BacktestSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluated_sessions: int
    detected_zones: int
    directional_zones: int
    neutral_zones: int
    candidate_states: int
    confirmed_states: int
    invalidated_states: int
    state_changes: int
    average_signal_delay_sessions: float | None = None
    benchmark_notes: list[str] = Field(default_factory=list)


class VolumeZonesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    mic: str
    as_of: date
    calculation_version: str
    configuration_version: str
    data_quality: DataQuality
    current_state: CurrentZoneState
    active_zone: VolumeZone | None = None
    zones: list[VolumeZone] = Field(default_factory=list)
    profile: list[VolumeProfileBin] = Field(default_factory=list)
    timeline: list[TimelinePoint] = Field(default_factory=list)
    backtest: BacktestSummary | None = None
    # Two-profile model + selection context (S3/S7). Additive, defaulted.
    structural_profile: list[VolumeProfileBin] = Field(default_factory=list)
    structural_profile_metadata: ProfileMetadata | None = None
    active_profile_metadata: ProfileMetadata | None = None
    nearest_zone_above: VolumeZone | None = None
    nearest_zone_below: VolumeZone | None = None
    # Up to three zones highlighted on the chart; `zones` keeps the full set.
    highlighted_zone_ids: list[str] = Field(default_factory=list)
    # Accumulation/distribution phases derived from the daily evidence balance,
    # independent of profile zones (Etap 2).
    directional_episodes: list[DirectionalPhase] = Field(default_factory=list)
    # Sparse, conflict-resolved phases for user-facing chart overlays. Raw
    # directional_episodes remain available for diagnostics/debug.
    resolved_directional_episodes: list[DirectionalPhase] = Field(default_factory=list)
    # Historical major phases: resolved technical episodes ranked by
    # sign-aware follow-through, MFE/MAE, and breakout outcome. This is an
    # after-the-fact annotation layer, not a live signal.
    major_directional_phases: list[DirectionalPhase] = Field(default_factory=list)
