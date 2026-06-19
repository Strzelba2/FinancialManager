from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class OhlcvCandle:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    index: int


@dataclass(frozen=True)
class ValidationResult:
    candles: list[OhlcvCandle]
    warnings: list[str]
    duplicate_dates: list[date]
    input_rows: int
    excluded_rows: int


@dataclass
class BinContribution:
    date: date
    session_index: int
    allocated_volume: float
    weighted_volume: float
    overlap_ratio: float
    close: float
    open: float
    high: float
    low: float
    relative_volume: float
    volume_percentile: float
    atr: float
    rejection_score: float
    close_change_atr: float


@dataclass
class PriceBin:
    index: int
    low: float
    high: float
    raw_volume: float = 0.0
    weighted_volume: float = 0.0
    effective_sessions: float = 0.0
    contributions: list[BinContribution] = field(default_factory=list)

    @property
    def center(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass(frozen=True)
class AnalysisContext:
    rolling_median_volume: list[float]
    volume_percentile: list[float]
    atr: list[float]
