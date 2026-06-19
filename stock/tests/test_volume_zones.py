from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

import allure
import pytest

from app.analysis.volume_zones import DEFAULT_CONFIG, VolumeZoneConfig, analyze_volume_zones
from app.analysis.volume_zones.data import normalize_ohlcv
from app.analysis.volume_zones.free_float import FreeFloatSnapshot, extract_free_float_snapshot
from app.analysis.volume_zones.indicators import causal_percentile
from app.analysis.volume_zones.profile import allocate_candle_to_bins, build_price_bins
from app.analysis.volume_zones.types import AnalysisContext, OhlcvCandle
from app.schemas.volume_zones import DirectionalPhase

pytestmark = pytest.mark.unit


def _row(day: date, open_: str, high: str, low: str, close: str, volume: int | None = 1000) -> dict[str, object]:
    return {
        "date_quote": day,
        "open": Decimal(open_),
        "high": Decimal(high),
        "low": Decimal(low),
        "close": Decimal(close),
        "volume": volume,
    }


def _zone_fixture(periods: int = 52) -> list[dict[str, object]]:
    start = date(2026, 1, 1)
    rows: list[dict[str, object]] = []
    for idx in range(periods):
        day = start + timedelta(days=idx)
        if idx < 16:
            close = 122 - idx * 1.2
            rows.append(_row(day, f"{close + 0.6:.2f}", f"{close + 1.2:.2f}", f"{close - 1.0:.2f}", f"{close:.2f}", 1000))
        elif idx < 40:
            rows.append(_row(day, "100.80", "104.00", "98.20", "103.40", 5200))
        else:
            close = 105 + (idx - 40) * 0.8
            rows.append(_row(day, f"{close - 0.4:.2f}", f"{close + 1.0:.2f}", f"{close - 1.1:.2f}", f"{close:.2f}", 1800))
    return rows


def _invalidated_demand_fixture() -> list[dict[str, object]]:
    start = date(2026, 1, 1)
    rows: list[dict[str, object]] = []
    for idx in range(26):
        day = start + timedelta(days=idx)
        rows.append(_row(day, "21.80", "23.00", "19.20", "22.70", 6500))
    for idx in range(26, 34):
        day = start + timedelta(days=idx)
        close = 18.5 - (idx - 26) * 0.7
        rows.append(_row(day, f"{close + 0.50:.2f}", f"{close + 0.90:.2f}", f"{close - 0.60:.2f}", f"{close:.2f}", 1800))
    return rows


@allure.epic("Unit Tests")
@allure.feature("Stock Volume Zones")
@allure.story("OHLCV validation reports diagnostics without silently repairing bad rows")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "market-data", "reports", "validation")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class VolumeZoneValidationTests(unittest.TestCase):
    def test_validation_excludes_invalid_rows_and_marks_flat_or_missing_volume_sessions(self) -> None:
        rows = [
            _row(date(2026, 1, 1), "10", "11", "9", "10", 100),
            _row(date(2026, 1, 1), "10", "11", "9", "10", 100),
            _row(date(2026, 1, 2), "10", "8", "9", "10", 100),
            _row(date(2026, 1, 3), "10", "10", "10", "10", None),
        ]

        result = normalize_ohlcv(rows)

        self.assertEqual(len(result.candles), 2)
        self.assertEqual(result.excluded_rows, 2)
        self.assertIn(date(2026, 1, 1), result.duplicate_dates)
        self.assertIn("DUPLICATE_DATE_EXCLUDED", result.warnings)
        self.assertIn("INVALID_OHLC_RANGE_EXCLUDED", result.warnings)
        self.assertIn("MISSING_VOLUME_TREATED_AS_ZERO", result.warnings)
        self.assertIn("FLAT_PRICE_SESSION", result.warnings)


@allure.epic("Unit Tests")
@allure.feature("Stock Volume Zones")
@allure.story("Volume allocation is deterministic and preserves one candle volume")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "market-data", "reports")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class VolumeProfileAllocationTests(unittest.TestCase):
    def test_wide_candle_allocates_across_bins_without_multiplying_volume(self) -> None:
        candle = OhlcvCandle(
            date=date(2026, 1, 1),
            open=10.0,
            high=20.0,
            low=10.0,
            close=19.0,
            volume=1000,
            index=0,
        )
        config = VolumeZoneConfig(price_bin_strategy="fixed_target_bin_count", target_bin_count=10)
        bins = build_price_bins([candle], config)

        allocations = allocate_candle_to_bins(candle, bins, config)

        self.assertGreater(len(allocations), 1)
        self.assertAlmostEqual(sum(item[1] for item in allocations), 1000.0, places=6)
        self.assertAlmostEqual(sum(item[2] for item in allocations), 1.0, places=6)

    def test_flat_candle_allocates_to_the_containing_bin(self) -> None:
        candle = OhlcvCandle(
            date=date(2026, 1, 1),
            open=10.0,
            high=10.0,
            low=10.0,
            close=10.0,
            volume=500,
            index=0,
        )
        config = VolumeZoneConfig(price_bin_strategy="fixed_target_bin_count", target_bin_count=10)
        bins = build_price_bins([candle], config)

        allocations = allocate_candle_to_bins(candle, bins, config)

        self.assertEqual(len(allocations), 1)
        self.assertAlmostEqual(allocations[0][1], 500.0, places=6)


@allure.epic("Unit Tests")
@allure.feature("Stock Volume Zones")
@allure.story("Causal indicators do not use future sessions")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "market-data", "reports", "causality")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class VolumeZoneCausalityTests(unittest.TestCase):
    def test_causal_percentile_for_past_day_is_unchanged_after_future_outlier(self) -> None:
        prefix = [100, 110, 120, 130]
        extended = [*prefix, 10_000]

        self.assertEqual(causal_percentile(prefix, window=10)[2], causal_percentile(extended, window=10)[2])

    def test_walk_forward_timeline_matches_prefix_result_after_future_data_is_added(self) -> None:
        rows = _zone_fixture(52)
        prefix_rows = rows[:42]
        config = DEFAULT_CONFIG.model_copy(update={"min_history_sessions": 25})

        prefix_result = analyze_volume_zones(
            prefix_rows,
            symbol="TST",
            mic="XWAR",
            include_timeline=False,
            max_zones=3,
            config=config,
        )
        full_result = analyze_volume_zones(
            rows,
            symbol="TST",
            mic="XWAR",
            mode="backtest",
            include_timeline=True,
            max_zones=3,
            config=config,
        )
        matching_point = next(point for point in full_result.timeline if point.date == prefix_result.as_of)

        self.assertEqual(matching_point.state, prefix_result.current_state.state)
        self.assertEqual(matching_point.evidence_score, prefix_result.current_state.evidence_score)
        self.assertEqual(matching_point.transition_reasons, prefix_result.current_state.transition_reasons)


@allure.epic("Unit Tests")
@allure.feature("Stock Volume Zones")
@allure.story("Volume zone analysis returns deterministic zones and explicit data limits")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "market-data", "reports", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class VolumeZoneAnalysisTests(unittest.TestCase):
    def test_analysis_returns_zones_without_free_float_snapshot_or_order_flow_claims(self) -> None:
        result = analyze_volume_zones(
            _zone_fixture(),
            symbol="TST",
            mic="XWAR",
            mode="backtest",
            include_timeline=True,
            max_zones=3,
        )

        self.assertEqual(result.symbol, "TST")
        self.assertEqual(result.data_quality.historical_free_float_available, False)
        self.assertEqual(result.data_quality.current_free_float_used, False)
        self.assertIn("FREE_FLOAT_SNAPSHOT_NOT_AVAILABLE", result.data_quality.warnings)
        self.assertIn("DAILY_OHLCV_PROXY_NOT_ORDER_FLOW", result.data_quality.warnings)
        self.assertLessEqual(len(result.zones), 3)
        self.assertTrue(result.profile)
        self.assertIsNotNone(result.backtest)
        self.assertGreaterEqual(result.backtest.evaluated_sessions, 1)

    def test_report_snapshot_free_float_is_used_without_claiming_historical_float_series(self) -> None:
        free_float = FreeFloatSnapshot(
            free_float_pct=40.18,
            shares_outstanding=18_473_162,
            as_of=date(2025, 9, 25),
            source="report_ai_snapshot",
        )

        result = analyze_volume_zones(
            _zone_fixture(),
            symbol="TST",
            mic="XWAR",
            max_zones=3,
            free_float=free_float,
        )

        self.assertEqual(result.data_quality.historical_free_float_available, False)
        self.assertEqual(result.data_quality.current_free_float_used, True)
        self.assertEqual(result.data_quality.current_free_float_pct, 40.18)
        self.assertEqual(result.data_quality.current_float_shares, round(free_float.float_shares))
        self.assertIn("FREE_FLOAT_SNAPSHOT_USED", result.data_quality.warnings)
        if result.zones:
            self.assertIsNotNone(result.zones[0].current_free_float_turnover)

    def test_extract_free_float_snapshot_reads_report_ai_payload_shape(self) -> None:
        payload = {
            "company": {"shares_outstanding": {"value": 18_473_162}},
            "shareholders": {
                "free_float_pct": {
                    "value": 40.18,
                    "as_of": "2025-09-25",
                }
            },
        }

        snapshot = extract_free_float_snapshot(payload, source="report_ai_snapshot")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.free_float_pct, 40.18)
        self.assertEqual(snapshot.as_of, date(2025, 9, 25))

    def test_invalidated_demand_zone_is_not_reported_as_active_accumulation(self) -> None:
        config = DEFAULT_CONFIG.model_copy(update={
            "min_history_sessions": 20,
            "target_bin_count": 24,
            "minimum_effective_sessions": 3.0,
            "minimum_activity_equivalent_sessions": 2.0,
            "minimum_active_weeks": 1,
            "minimum_consistency": 0.0,
            "maximum_dominant_session_share": 0.8,
            "active_zone_recent_sessions": 3,
        })

        result = analyze_volume_zones(
            _invalidated_demand_fixture(),
            symbol="TST",
            mic="XWAR",
            max_zones=3,
            config=config,
        )

        self.assertNotIn(result.current_state.state, {"ACCUMULATION_CANDIDATE", "ACCUMULATION_ACTIVE"})
        if result.active_zone is not None:
            self.assertNotEqual(result.active_zone.status, "ACTIVE")
        self.assertTrue(
            any(zone.status == "INVALIDATED" for zone in result.zones)
            or result.current_state.state in {"NEUTRAL", "FAILED_ACCUMULATION"}
        )

    def test_weak_evidence_stays_neutral_or_insufficient(self) -> None:
        config = DEFAULT_CONFIG.model_copy(update={"min_history_sessions": 25})

        result = analyze_volume_zones(
            _zone_fixture(),
            symbol="TST",
            mic="XWAR",
            max_zones=3,
            config=config,
        )

        weak_zones = [zone for zone in result.zones if zone.evidence_score < config.candidate_evidence_score_min]
        self.assertTrue(all(
            zone.direction_label in {"NEUTRAL_LIQUIDITY", "INSUFFICIENT_DIRECTIONAL_EVIDENCE"}
            for zone in weak_zones
        ))

    def test_zone_top_level_activity_describes_latest_episode(self) -> None:
        config = DEFAULT_CONFIG.model_copy(update={
            "min_history_sessions": 25,
            "maximum_episode_span_sessions": 20,
            "minimum_effective_sessions": 3.0,
            "minimum_activity_equivalent_sessions": 2.0,
            "minimum_active_weeks": 1,
            "maximum_dominant_session_share": 0.8,
        })

        result = analyze_volume_zones(
            _zone_fixture(90),
            symbol="TST",
            mic="XWAR",
            max_zones=3,
            config=config,
        )

        for zone in result.zones:
            self.assertTrue(zone.episodes)
            latest_episode = zone.episodes[-1]
            self.assertEqual(zone.effective_sessions, latest_episode.effective_sessions)
            self.assertLessEqual(zone.effective_sessions, latest_episode.session_count)


def _pressure_phases_fixture() -> list[dict[str, object]]:
    """Accumulation (lower wicks) -> neutral -> distribution (upper wicks)."""
    start = date(2025, 1, 1)
    rows: list[dict[str, object]] = []
    day = 0
    for _ in range(45):  # accumulation: close near high, long lower wick
        rows.append(_row(start + timedelta(days=day), "100.0", "101.0", "97.0", "100.8", 5000))
        day += 1
    for _ in range(30):  # neutral: tiny ranges, low volume
        rows.append(_row(start + timedelta(days=day), "100.0", "100.4", "99.6", "100.0", 700))
        day += 1
    for _ in range(45):  # distribution: close near low, long upper wick
        rows.append(_row(start + timedelta(days=day), "100.0", "103.0", "99.0", "99.2", 5000))
        day += 1
    return rows


def _two_profile_fixture() -> list[dict[str, object]]:
    """Long dwell near 100 (structural) + brief spike to ~140 (active)."""
    start = date(2020, 1, 1)
    rows: list[dict[str, object]] = []
    day = 0
    for idx in range(400):
        close = 100 + (0.5 if idx % 2 else -0.5)
        rows.append(_row(start + timedelta(days=day), "100.0", f"{close + 1:.2f}", f"{close - 1:.2f}", f"{close:.2f}", 1000))
        day += 1
    for _ in range(12):
        rows.append(_row(start + timedelta(days=day), "139.0", "141.0", "138.0", "140.0", 9000))
        day += 1
    for idx in range(60):
        close = 140 - (140 - 100) * (idx / 60)
        rows.append(_row(start + timedelta(days=day), f"{close:.2f}", f"{close + 1:.2f}", f"{close - 1:.2f}", f"{close:.2f}", 1200))
        day += 1
    return rows


@allure.epic("Unit Tests")
@allure.feature("Stock Volume Zones")
@allure.story("Two-profile detection, full zone set, and causal evidence balance")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "market-data", "reports", "volume-zones")
class VolumeZoneRegressionTests(unittest.TestCase):
    def test_mode_full_returns_all_zones_summary_limits_to_highlighted(self) -> None:
        rows = _two_profile_fixture()
        full = analyze_volume_zones(rows, symbol="TST", mic="XWAR", mode="full", max_zones=3)
        summary = analyze_volume_zones(rows, symbol="TST", mic="XWAR", mode="summary", max_zones=3)
        self.assertGreater(len(full.zones), 1)
        self.assertGreaterEqual(len(full.zones), len(summary.zones))
        self.assertLessEqual(len(summary.zones), 3)
        # Highlighted ids are the same curated set in both modes.
        self.assertEqual(set(summary.highlighted_zone_ids), set(full.highlighted_zone_ids))
        self.assertEqual({z.zone_id for z in summary.zones}, set(summary.highlighted_zone_ids))

    def test_both_profiles_contribute_candidate_zones(self) -> None:
        result = analyze_volume_zones(_two_profile_fixture(), symbol="TST", mic="XWAR", mode="full")
        centers = [z.center_price for z in result.zones]
        self.assertTrue(any(95 <= c <= 105 for c in centers), centers)  # structural dwell
        self.assertTrue(any(135 <= c <= 145 for c in centers), centers)  # active spike recovered
        sources = {z.source_profile for z in result.zones}
        self.assertTrue(sources.issubset({"STRUCTURAL", "ACTIVE", "BOTH"}), sources)
        # The active profile contributed (directly or via a merged BOTH band).
        self.assertTrue(any(z.source_profile in {"ACTIVE", "BOTH"} for z in result.zones))

    def test_timeline_covers_full_range_with_both_signs(self) -> None:
        rows = _pressure_phases_fixture()
        result = analyze_volume_zones(rows, symbol="TST", mic="XWAR", mode="full", include_timeline=True)
        values = [p.evidence_balance for p in result.timeline if p.evidence_balance is not None]
        self.assertTrue(any(v > 0 for v in values))
        self.assertTrue(any(v < 0 for v in values))
        # Full range: one point per session after the warm-up (not a recent slice).
        expected = len(rows) - (DEFAULT_CONFIG.min_history_sessions - 1)
        self.assertEqual(len(result.timeline), expected)
        self.assertEqual(result.timeline[-1].date, rows[-1]["date_quote"])

    def test_directional_phases_detect_accumulation_and_distribution(self) -> None:
        result = analyze_volume_zones(
            _pressure_phases_fixture(), symbol="TST", mic="XWAR", mode="full")
        episodes = result.directional_episodes
        self.assertTrue(episodes)
        phases = {e.phase for e in episodes}
        self.assertIn("ACCUMULATION", phases)
        self.assertIn("DISTRIBUTION", phases)
        for e in episodes:
            # Time-anchored span and a sane price box.
            self.assertLessEqual(e.candidate_at, e.ended_at)
            self.assertLess(e.price_low, e.price_high)
            self.assertGreaterEqual(e.session_count, 1)
            if e.phase == "ACCUMULATION":
                self.assertGreater(e.average_balance, 0)
            else:
                self.assertLess(e.average_balance, 0)

    def test_directional_phases_are_independent_of_zone_quality_gate(self) -> None:
        # Phases come from the daily balance, so they exist even when the zone
        # quality gate keeps every zone neutral.
        result = analyze_volume_zones(
            _pressure_phases_fixture(), symbol="TST", mic="XWAR", mode="full")
        self.assertTrue(result.directional_episodes)

    def _candle(self, day_index: int, o: float, h: float, lo: float, c: float) -> OhlcvCandle:
        return OhlcvCandle(
            date=date(2025, 1, 1) + timedelta(days=day_index),
            open=o, high=h, low=lo, close=c, volume=1000, index=day_index,
        )

    def _ctx(self, n: int) -> AnalysisContext:
        return AnalysisContext(
            rolling_median_volume=[1000.0] * n,
            volume_percentile=[1.0] * n,
            atr=[1.0] * n,
        )

    def _phase(
        self,
        *,
        phase_id: str,
        phase: str,
        candidate_idx: int,
        ended_idx: int,
        confirmed_idx: int | None = None,
        invalidated_idx: int | None = None,
        price_low: float = 10.0,
        price_high: float = 12.0,
        average_balance: float = 0.5,
        cumulative_evidence: float = 6.0,
        session_count: int = 12,
        evidence_score: int = 60,
    ) -> DirectionalPhase:
        sign = 1 if phase == "ACCUMULATION" else -1
        status = "CONFIRMED" if confirmed_idx is not None else (
            "INVALIDATED" if invalidated_idx is not None else "CLOSED"
        )
        return DirectionalPhase(
            phase_id=phase_id,
            phase=phase,
            estimated_start_at=date(2025, 1, 1) + timedelta(days=max(0, candidate_idx - 5)),
            base_end_at=date(2025, 1, 1) + timedelta(days=max(0, candidate_idx - 1)),
            candidate_at=date(2025, 1, 1) + timedelta(days=candidate_idx),
            active_at=None,
            ended_at=date(2025, 1, 1) + timedelta(days=ended_idx),
            confirmed_at=(
                date(2025, 1, 1) + timedelta(days=confirmed_idx)
                if confirmed_idx is not None else None
            ),
            invalidated_at=(
                date(2025, 1, 1) + timedelta(days=invalidated_idx)
                if invalidated_idx is not None else None
            ),
            price_low=price_low,
            price_high=price_high,
            center_price=(price_low + price_high) / 2.0,
            average_balance=average_balance,
            peak_balance=sign * max(abs(average_balance), 0.1),
            cumulative_evidence=cumulative_evidence,
            session_count=session_count,
            evidence_score=evidence_score,
            status=status,
            confirmation_price=price_high + 1.0 if phase == "ACCUMULATION" else price_low - 1.0,
            invalidation_price=price_low - 1.0 if phase == "ACCUMULATION" else price_high + 1.0,
            linked_zone_ids=[],
        )

    def test_directional_pressure_without_prior_base_does_not_create_phase(self) -> None:
        from app.analysis.volume_zones.episodes import detect_directional_episodes
        n = 60
        candles = [self._candle(i, 20 + i * 1.0, 21 + i * 1.0, 19 + i * 1.0, 20.5 + i * 1.0) for i in range(n)]
        balance = [0.6] * n
        phases = detect_directional_episodes(candles, balance, self._ctx(n), DEFAULT_CONFIG)
        self.assertEqual(phases, [])

    def test_accumulation_then_upside_breakout_confirms(self) -> None:
        from app.analysis.volume_zones.episodes import detect_directional_episodes
        candles = (
            [self._candle(i, 22.0, 22.3, 21.7, 22.0) for i in range(40)]
            + [self._candle(40 + i, 30.0, 30.3, 29.7, 30.0) for i in range(25)]
        )
        balance = [0.6] * 40 + [0.0] * 25  # regime ends, then price holds higher
        phases = detect_directional_episodes(candles, balance, self._ctx(len(candles)), DEFAULT_CONFIG)
        acc = [p for p in phases if p.phase == "ACCUMULATION"]
        self.assertTrue(acc)
        # Broken upward -> confirmed, never invalidated.
        self.assertTrue(any(p.status == "CONFIRMED" for p in acc))
        self.assertFalse(any(p.status == "INVALIDATED" for p in acc))

    def test_accumulation_phase_is_anchored_to_base_before_breakout(self) -> None:
        from app.analysis.volume_zones.episodes import detect_directional_episodes
        candles = []
        for i in range(14):
            px = 22.0 - i * 0.35
            candles.append(self._candle(i, px + 0.2, px + 0.5, px - 0.5, px))
        base_start = len(candles)
        for i in range(24):
            day = base_start + i
            close = 16.0 + (0.25 if i % 3 == 0 else -0.05)
            candles.append(self._candle(day, 16.1, 16.7, 15.4, close))
        breakout_start = len(candles)
        for i, close in enumerate([18.2, 18.8, 19.4, 21.5, 23.0, 24.0]):
            day = breakout_start + i
            candles.append(self._candle(day, close - 0.2, close + 0.5, close - 0.6, close))
        later_break_start = len(candles)
        for i, close in enumerate([14.7, 14.2, 13.9]):
            day = later_break_start + i
            candles.append(self._candle(day, close + 0.2, close + 0.5, close - 0.5, close))

        balance = [0.0] * breakout_start + [0.6] * 6 + [0.0] * 3
        phases = detect_directional_episodes(candles, balance, self._ctx(len(candles)), DEFAULT_CONFIG)

        self.assertEqual(len(phases), 1)
        phase = phases[0]
        self.assertEqual(phase.phase, "ACCUMULATION")
        self.assertEqual(phase.status, "CONFIRMED")
        self.assertIsNotNone(phase.confirmed_at)
        self.assertIsNone(phase.invalidated_at)
        self.assertLess(phase.estimated_start_at, phase.candidate_at)
        self.assertLessEqual(phase.price_high, 17.0)
        self.assertEqual(phase.ended_at, phase.confirmed_at)

    def test_false_accumulation_base_is_invalidated_without_confirmation(self) -> None:
        from app.analysis.volume_zones.episodes import detect_directional_episodes
        candles = [self._candle(i, 20.0, 20.8, 19.4, 20.1) for i in range(18)]
        for i, close in enumerate([19.0, 18.4, 17.7]):
            day = len(candles)
            candles.append(self._candle(day, close + 0.1, close + 0.4, close - 0.6, close))

        balance = [0.6] * 18 + [0.0] * 3
        phases = detect_directional_episodes(candles, balance, self._ctx(len(candles)), DEFAULT_CONFIG)

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].status, "INVALIDATED")
        self.assertIsNotNone(phases[0].invalidated_at)
        self.assertIsNone(phases[0].confirmed_at)

    def test_resolved_directional_phases_drop_weaker_overlapping_opposite_candidate(self) -> None:
        from app.analysis.volume_zones.episodes import resolve_directional_phases

        candles = [self._candle(i, 10.0, 12.0, 9.5, 10.8) for i in range(30)]
        acc = self._phase(
            phase_id="acc-strong",
            phase="ACCUMULATION",
            candidate_idx=6,
            ended_idx=16,
            confirmed_idx=16,
            price_low=10.0,
            price_high=12.0,
            average_balance=0.8,
            cumulative_evidence=14.0,
            session_count=18,
            evidence_score=80,
        )
        dist = self._phase(
            phase_id="dist-weak",
            phase="DISTRIBUTION",
            candidate_idx=7,
            ended_idx=17,
            confirmed_idx=17,
            price_low=10.2,
            price_high=12.2,
            average_balance=-0.2,
            cumulative_evidence=-2.0,
            session_count=8,
            evidence_score=20,
        )
        config = DEFAULT_CONFIG.model_copy(update={
            "phase_render_min_significance": 0.0,
            "phase_conflict_ambiguous_margin": 0.0,
        })

        resolved = resolve_directional_phases([acc, dist], candles, config)

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].phase, "ACCUMULATION")

    def test_historical_outcome_score_is_separate_from_setup_quality(self) -> None:
        from app.analysis.volume_zones.episodes import enrich_directional_phases

        config = DEFAULT_CONFIG.model_copy(update={
            "phase_outcome_short_sessions": 2,
            "phase_outcome_long_sessions": 6,
        })
        good_candles = [
            self._candle(i, close - 0.2, close + 0.4, close - 0.4, close)
            for i, close in enumerate([10, 10, 10, 10, 10, 11, 12, 13, 14, 15, 16, 17])
        ]
        bad_candles = [
            self._candle(i, close - 0.2, close + 0.4, close - 0.4, close)
            for i, close in enumerate([10, 10, 10, 10, 10, 11, 10, 9, 8, 7, 6, 5])
        ]
        phase = self._phase(
            phase_id="same-setup",
            phase="ACCUMULATION",
            candidate_idx=2,
            ended_idx=5,
            confirmed_idx=5,
            average_balance=0.55,
            cumulative_evidence=6.0,
            session_count=12,
            evidence_score=55,
        )

        good = enrich_directional_phases([phase], good_candles, config)[0]
        bad = enrich_directional_phases([phase], bad_candles, config)[0]

        self.assertEqual(good.setup_score, bad.setup_score)
        self.assertEqual(good.significance_score, good.setup_score)
        self.assertIsNotNone(good.historical_outcome_score)
        self.assertIsNotNone(bad.historical_outcome_score)
        self.assertGreater(good.historical_outcome_score or 0.0, bad.historical_outcome_score or 0.0)
        self.assertGreater(good.expected_direction_return or 0.0, 0.0)
        self.assertLess(bad.expected_direction_return or 0.0, 0.0)

    def test_major_phase_ranking_uses_historical_outcome_and_keeps_distribution(self) -> None:
        from app.analysis.volume_zones.episodes import rank_major_directional_phases

        closes = []
        for i in range(55):
            if i < 8:
                close = 20.0
            elif i < 20:
                close = 20.0 + (i - 8) * 1.2
            elif i < 38:
                close = 35.0
            elif i < 50:
                close = 35.0 - (i - 38) * 1.4
            else:
                close = 18.0
            closes.append(close)
        candles = [
            self._candle(i, close - 0.2, close + 0.5, close - 0.5, close)
            for i, close in enumerate(closes)
        ]
        phases = [
            self._phase(
                phase_id="acc-outcome",
                phase="ACCUMULATION",
                candidate_idx=5,
                ended_idx=8,
                confirmed_idx=8,
                price_low=19.2,
                price_high=20.8,
                average_balance=0.55,
                cumulative_evidence=6.5,
                session_count=12,
                evidence_score=55,
            ),
            self._phase(
                phase_id="dist-outcome",
                phase="DISTRIBUTION",
                candidate_idx=35,
                ended_idx=38,
                confirmed_idx=38,
                price_low=34.2,
                price_high=35.8,
                average_balance=-0.55,
                cumulative_evidence=-6.5,
                session_count=12,
                evidence_score=55,
            ),
        ]
        config = DEFAULT_CONFIG.model_copy(update={
            "phase_outcome_short_sessions": 3,
            "phase_outcome_long_sessions": 6,
            "phase_major_min_outcome_score": 10.0,
            "phase_major_max_count": 6,
            "phase_major_min_direction_count": 1,
            "phase_major_min_spacing_sessions": 5,
            "phase_swing_low_min_prior_drawdown_pct": 100.0,
        })

        major = rank_major_directional_phases(phases, candles, config)

        self.assertIn("ACCUMULATION", {phase.phase for phase in major})
        self.assertIn("DISTRIBUTION", {phase.phase for phase in major})
        self.assertTrue(all(phase.status == "CONFIRMED" for phase in major))
        self.assertTrue(all((phase.historical_outcome_score or 0.0) >= 10.0 for phase in major))

    def test_major_phase_ranking_ignores_high_setup_without_follow_through(self) -> None:
        from app.analysis.volume_zones.episodes import rank_major_directional_phases

        candles = [
            self._candle(i, close - 0.2, close + 0.5, close - 0.5, close)
            for i, close in enumerate([20, 20, 20, 20, 20, 21, 20, 19, 18, 17, 16, 15])
        ]
        phase = self._phase(
            phase_id="failed-follow-through",
            phase="ACCUMULATION",
            candidate_idx=2,
            ended_idx=5,
            confirmed_idx=5,
            average_balance=0.9,
            cumulative_evidence=12.0,
            session_count=18,
            evidence_score=90,
        )
        config = DEFAULT_CONFIG.model_copy(update={
            "phase_outcome_short_sessions": 2,
            "phase_outcome_long_sessions": 6,
            "phase_major_min_outcome_score": 20.0,
            "phase_swing_low_min_prior_drawdown_pct": 100.0,
        })

        self.assertEqual(rank_major_directional_phases([phase], candles, config), [])

    def test_swing_low_fallback_adds_historical_accumulation_to_major_layer(self) -> None:
        from app.analysis.volume_zones.episodes import rank_major_directional_phases

        closes = [30.0 - i * 0.7 for i in range(21)]
        closes.extend(16.0 + i * 0.6 for i in range(1, 35))
        candles = [
            self._candle(i, close - 0.2, close + 0.3, close - 0.3, close)
            for i, close in enumerate(closes)
        ]
        config = DEFAULT_CONFIG.model_copy(update={
            "phase_outcome_short_sessions": 5,
            "phase_outcome_long_sessions": 15,
            "phase_major_min_outcome_score": 5.0,
            "phase_major_max_count": 5,
            "phase_major_min_direction_count": 0,
            "phase_major_min_spacing_sessions": 5,
            "phase_swing_low_window_sessions": 10,
            "phase_swing_low_prior_sessions": 20,
            "phase_swing_low_forward_sessions": 20,
            "phase_swing_low_base_before_sessions": 5,
            "phase_swing_low_base_after_sessions": 2,
            "phase_swing_low_min_prior_drawdown_pct": 20.0,
            "phase_swing_low_min_followthrough_pct": 25.0,
        })

        major = rank_major_directional_phases([], candles, config)

        self.assertTrue(major)
        self.assertTrue(all(phase.phase == "ACCUMULATION" for phase in major))
        self.assertTrue(any(phase.candidate_at == candles[20].date for phase in major))
        self.assertTrue(all(phase.status == "CONFIRMED" for phase in major))
        self.assertTrue(all(phase.historical_outcome_score is not None for phase in major))

    def test_rolling_balance_warm_up_is_null_then_signed(self) -> None:
        from app.analysis.volume_zones.indicators import rolling_directional_balance
        from app.analysis.volume_zones.profile import build_analysis_context

        validation = normalize_ohlcv(_pressure_phases_fixture())
        context = build_analysis_context(validation.candles, DEFAULT_CONFIG)
        series = rolling_directional_balance(validation.candles, context, window=20)
        self.assertTrue(all(v is None for v in series[:19]))
        self.assertTrue(all(isinstance(v, float) for v in series[19:]))
        self.assertTrue(any(v > 0 for v in series if v is not None))
        self.assertTrue(any(v < 0 for v in series if v is not None))
