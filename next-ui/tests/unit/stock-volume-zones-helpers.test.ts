import { describe, expect, it } from 'vitest'

import {
  buildDirectionalEpisodeMarkArea,
  buildDirectionalEpisodeOutcomeSeries,
  buildEvidenceBalanceSeries,
  buildVolumeZoneMarkArea,
  buildVolumeZoneMarkLine,
  buildZoneLevelMarkLine,
  buildZoneHoverSeries,
  buildVolumeZoneProfileSeries,
  evidenceLabel,
  isZoneInvalidated,
  phaseOutcomeLabel,
  phaseShortLabel,
  zoneColor,
} from '@/features/wallet/components/volume-zones'
import type { DirectionalPhase } from '@/lib/api/stock'
import type { CandleDay, VolumeZonesResponse } from '@/lib/api/stock'
import { nextUiUnitStory } from '../allure'

const analysis: VolumeZonesResponse = {
  symbol: 'PKO',
  mic: 'XWAR',
  as_of: '2026-06-12',
  calculation_version: '1.0.0',
  configuration_version: '1.0.0',
  data_quality: {
    ohlcv_interval: '1d',
    historical_free_float_available: false,
    current_free_float_used: false,
    current_free_float_pct: null,
    current_free_float_as_of: null,
    current_float_shares: null,
    current_free_float_source: null,
    confidence: 'medium',
    input_rows: 40,
    valid_rows: 40,
    excluded_rows: 0,
    duplicate_dates: [],
    first_date: '2026-01-01',
    last_date: '2026-06-12',
    warnings: ['FREE_FLOAT_SNAPSHOT_NOT_AVAILABLE'],
  },
  current_state: {
    state: 'ACCUMULATION_CANDIDATE',
    evidence_score: 68,
    detected_at: '2026-05-20',
    confirmation_price: 72.4,
    invalidation_price: 63.8,
    transition_reasons: ['HIGH_RELATIVE_VOLUME'],
    active_zone_id: 'zone-1',
    active_episode_id: 'zone-1-episode-1',
  },
  active_zone: null,
  zones: [
    {
      zone_id: 'zone-1',
      price_low: 64.5,
      price_high: 69.2,
      center_price: 66.85,
      estimated_start_date: '2026-04-04',
      first_detected_at: '2026-04-15',
      last_active_at: '2026-06-10',
      raw_volume: 1000,
      weighted_volume: 900,
      activity_score: 72,
      activity_equivalent_sessions: 12.8,
      effective_sessions: 14.3,
      active_weeks: 5,
      dominant_session_share: 0.2,
      freshness_score: 92,
      status: 'ACTIVE',
      behavior: 'DEMAND_ABSORPTION_PROXY',
      direction_label: 'ACCUMULATION_CANDIDATE',
      evidence_score: 68,
      evidence_balance: 0.52,
      consistency: 0.67,
      confirmation_price: 72.4,
      invalidation_price: 63.8,
      current_free_float_turnover: null,
      current_free_float_turnover_is_estimate: false,
      evidence: [{ code: 'HIGH_RELATIVE_VOLUME', value: 1.84, direction: 'NEUTRAL' }],
      episodes: [],
    },
  ],
  profile: [
    {
      price_low: 64.5,
      price_high: 65.5,
      center_price: 65,
      raw_volume: 900,
      weighted_volume: 800,
      activity_score: 80,
    },
    {
      price_low: 65.5,
      price_high: 66.5,
      center_price: 66,
      raw_volume: 1000,
      weighted_volume: 1000,
      activity_score: 100,
    },
  ],
  timeline: [
    {
      date: '2026-06-11',
      state: 'ACCUMULATION_CANDIDATE',
      evidence_score: 60,
      evidence_balance: 0.4,
      active_zone_id: 'zone-1',
      active_episode_id: 'zone-1-episode-1',
      confirmation_price: 72.4,
      invalidation_price: 63.8,
      transition_reasons: ['HIGH_RELATIVE_VOLUME'],
    },
  ],
  backtest: null,
}

function phaseFixture(overrides: Partial<DirectionalPhase> = {}): DirectionalPhase {
  return {
    phase_id: 'phase-1',
    phase: 'ACCUMULATION',
    candidate_at: '2026-01-01',
    active_at: null,
    estimated_start_at: '2025-12-15',
    ended_at: '2026-02-01',
    confirmed_at: '2026-02-01',
    invalidated_at: null,
    price_low: 10,
    price_high: 12,
    center_price: 11,
    average_balance: 0.4,
    peak_balance: 0.6,
    cumulative_evidence: 8,
    session_count: 12,
    evidence_score: 40,
    status: 'CONFIRMED',
    confirmation_price: 13,
    invalidation_price: 9,
    linked_zone_ids: [],
    ...overrides,
  }
}

describe('volume-zone chart helpers', () => {
  it('maps deterministic evidence codes and zone colors without probability text', async () => {
    await nextUiUnitStory('Volume-zone helpers map deterministic evidence labels', {
      severity: 'normal',
      tags: ['stock', 'volume-zones', 'next-ui'],
    })

    expect(evidenceLabel('HIGH_RELATIVE_VOLUME')).toBe('Ponadprzeciętny wolumen')
    expect(evidenceLabel('UNKNOWN_CODE')).toBe('UNKNOWN_CODE')
    expect(zoneColor(analysis.zones[0]!)).toContain('rgba(34,197,94')
  })

  it('builds ECharts mark areas lines profile and evidence series', async () => {
    await nextUiUnitStory('Volume-zone helpers build ECharts overlays for the chart', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui'],
    })
    const candles: CandleDay[] = [
      { date_quote: '2026-06-11', open: 65, high: 70, low: 64, close: 68, volume: 1000 },
    ]
    const activeAnalysis = { ...analysis, active_zone: analysis.zones[0]! }

    expect(buildVolumeZoneMarkArea(activeAnalysis, { showZones: true, showProfile: true, profileOpacity: 0.18 })).toBeTruthy()
    expect(buildVolumeZoneMarkLine(activeAnalysis)).toBeTruthy()
    expect(buildVolumeZoneProfileSeries(activeAnalysis, { showZones: true, showProfile: true, profileOpacity: 0.18 })).toMatchObject({
      name: 'Profil ceny i wolumenu',
      type: 'custom',
    })
    expect(buildEvidenceBalanceSeries(candles, activeAnalysis, 1, 1)).toMatchObject({
      name: 'Siła dowodów',
      type: 'bar',
    })
  })

  it('describes distribution confirmation below and invalidation above', async () => {
    await nextUiUnitStory('Distribution levels use the correct confirmation side', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui'],
    })
    const supplyZone = {
      ...analysis.zones[0]!,
      behavior: 'SUPPLY_ABSORPTION_PROXY' as const,
      episode_signature: 'SUPPLY_ABSORPTION_PROXY' as const,
      direction_label: 'DISTRIBUTION_CANDIDATE',
    }
    const line = buildVolumeZoneMarkLine({
      ...analysis,
      active_zone: supplyZone,
    }) as { data: Array<{ label: { formatter: string } }> }

    expect(line.data[0]!.label.formatter).toContain('zamknięcia poniżej')
    expect(line.data[1]!.label.formatter).toContain('zamknięcia powyżej')
  })

  it('renders invalidated zones gray, not live green', async () => {
    await nextUiUnitStory('Invalidated zones do not read as live accumulation', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'next-ui'],
    })
    const invalidated = {
      ...analysis.zones[0]!,
      lifecycle_status: 'INVALIDATED' as const,
    }
    expect(isZoneInvalidated(invalidated)).toBe(true)
    const color = zoneColor(invalidated)
    expect(color).toContain('rgba(148,163,184')
    expect(color).not.toContain('rgba(34,197,94')
  })

  it('keeps negative balance and renders null as a gap, never green', async () => {
    await nextUiUnitStory('Evidence balance preserves sign and warm-up nulls', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'next-ui'],
    })
    const signed = {
      ...analysis,
      timeline: [
        { ...analysis.timeline[0]!, date: '2026-06-09', evidence_balance: -0.6 },
        { ...analysis.timeline[0]!, date: '2026-06-10', evidence_balance: null },
        { ...analysis.timeline[0]!, date: '2026-06-11', evidence_balance: 0.3 },
      ],
    }
    const candles: CandleDay[] = [
      { date_quote: '2026-06-09', open: 65, high: 66, low: 64, close: 65, volume: 10 },
      { date_quote: '2026-06-10', open: 65, high: 66, low: 64, close: 65, volume: 10 },
      { date_quote: '2026-06-11', open: 65, high: 66, low: 64, close: 65, volume: 10 },
    ]
    expect(buildEvidenceBalanceSeries(candles, signed, 1, 1)).toMatchObject({
      data: [-0.6, null, 0.3],
    })
  })

  it('sizes profile bars by raw_volume in raw mode and by activity in structural mode', async () => {
    await nextUiUnitStory('Profile modes drive bar length from the right field', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui'],
    })
    const sp = [
      { price_low: 10, price_high: 11, center_price: 10.5, raw_volume: 1000, weighted_volume: 5, activity_score: 30, contributing_sessions: 40 },
      { price_low: 30, price_high: 31, center_price: 30.5, raw_volume: 200, weighted_volume: 9, activity_score: 100, contributing_sessions: 8 },
    ]
    const a: VolumeZonesResponse = { ...analysis, structural_profile: sp, profile: sp }
    const opts = { showZones: true, showProfile: true, profileOpacity: 0.18 }
    const raw = buildVolumeZoneProfileSeries(a, { ...opts, profileMode: 'raw' }) as { data: Array<Array<number | string>> }
    const structural = buildVolumeZoneProfileSeries(a, { ...opts, profileMode: 'structural' }) as { data: Array<Array<number | string>> }
    // High-raw / low-activity bin: tall in raw mode, short in structural mode.
    expect(Number(raw.data[0]![2])).toBeCloseTo(100)
    expect(Number(structural.data[0]![2])).toBeCloseTo(30)
    // Tooltip payload carries raw_volume (idx 6) and contributing_sessions (idx 9).
    expect(Number(raw.data[0]![6])).toBe(1000)
    expect(Number(raw.data[0]![9])).toBe(40)
  })

  it('renders directional A/D phases as colored time boxes', async () => {
    await nextUiUnitStory('Directional phases render as green/red time+price boxes', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui'],
    })
    const episodes = [
      phaseFixture({ phase_id: 'p-acc', phase: 'ACCUMULATION', status: 'CONFIRMED' }),
      phaseFixture({
        phase_id: 'p-dist',
        phase: 'DISTRIBUTION',
        status: 'INVALIDATED',
        average_balance: -0.4,
        invalidated_at: '2026-02-05',
        confirmed_at: null,
      }),
    ]
    const a = { ...analysis, directional_episodes: episodes }
    expect(phaseShortLabel(episodes[0]!)).toBe('A')
    expect(phaseShortLabel(episodes[1]!)).toBe('D')
    expect(phaseOutcomeLabel(episodes[0]!)).toBe('A✓')
    expect(phaseOutcomeLabel(episodes[1]!)).toBe('D×')
    expect(buildDirectionalEpisodeMarkArea(a, { showZones: true, showProfile: false, profileOpacity: 0.18, showPhases: false })).toBeUndefined()
    const area = buildDirectionalEpisodeMarkArea(a, {
      showZones: true,
      showProfile: false,
      profileOpacity: 0.18,
      showPhases: true,
      phaseVisibility: 'debug',
    }) as { data: Array<Array<{ itemStyle?: { color?: string }; label?: { formatter?: string; show?: boolean } }>> }
    expect(area.data).toHaveLength(2)
    expect(area.data[0]![0]!.itemStyle!.color).toContain('rgba(34,197,94')
    expect(area.data[1]![0]!.itemStyle!.color).toContain('rgba(239,68,68')
    expect(area.data[1]![0]!.label!.formatter).toBe('D')
    expect(area.data[1]![0]!.label!.show).toBe(false)
    const resolver = (d: string | null | undefined) => (d === '2026-02-05' ? 7 : 0)
    const outcome = buildDirectionalEpisodeOutcomeSeries(a, {
      showZones: true,
      showProfile: false,
      profileOpacity: 0.18,
      showPhases: true,
      phaseVisibility: 'debug',
    }, resolver) as { data: Array<{ value: [number, number]; label: { formatter: string } }> }
    expect(outcome.data.map((point) => point.label.formatter)).toEqual(['A✓', 'D×'])
  })

  it('renders historical A/D from the major layer independently of zone visibility', async () => {
    await nextUiUnitStory('Historical A/D uses resolved major phases, not zone buttons', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui'],
    })

    const phases: DirectionalPhase[] = Array.from({ length: 10 }, (_, idx) => {
      const day = String(idx + 1).padStart(2, '0')
      return phaseFixture({
        phase_id: `phase-${idx + 1}`,
        phase: idx % 2 === 0 ? 'ACCUMULATION' : 'DISTRIBUTION',
        candidate_at: `2026-01-${day}`,
        active_at: null,
        estimated_start_at: `2025-12-${day}`,
        ended_at: `2026-02-${day}`,
        confirmed_at: idx % 3 === 0 ? `2026-02-${day}` : null,
        invalidated_at: idx % 3 === 1 ? `2026-02-${day}` : null,
        price_low: 10 + idx,
        price_high: 11 + idx,
        center_price: 10.5 + idx,
        average_balance: idx % 2 === 0 ? 0.4 : -0.4,
        peak_balance: idx % 2 === 0 ? 0.7 : -0.7,
        cumulative_evidence: 5,
        session_count: 8 + idx,
        evidence_score: 30 + idx,
        status: idx === 9 ? 'ACTIVE' : 'CONFIRMED',
        confirmation_price: 12 + idx,
        invalidation_price: 9 + idx,
        linked_zone_ids: idx < 8 ? ['zone-other'] : ['zone-1'],
        historical_outcome_score: 70 - idx,
        setup_score: 50 + idx,
      })
    })
    const major = phases.slice(1, 9).map((phase, idx) => ({
      ...phase,
      phase_id: `major-${idx + 1}`,
      status: 'CONFIRMED' as const,
      confirmed_at: phase.ended_at,
      invalidated_at: null,
    }))
    const a: VolumeZonesResponse = {
      ...analysis,
      highlighted_zone_ids: ['zone-1'],
      directional_episodes: phases,
      resolved_directional_episodes: phases.slice(8),
      major_directional_phases: major,
    }

    const opts = { showZones: true, showProfile: false, profileOpacity: 0.18, showPhases: true }
    const historicalWithSignificantZones = buildDirectionalEpisodeMarkArea(a, {
      ...opts,
      zoneVisibility: 'significant',
      phaseVisibility: 'significant',
    }) as { data: unknown[] }
    const historicalWithAllZones = buildDirectionalEpisodeMarkArea(a, {
      ...opts,
      zoneVisibility: 'all',
      phaseVisibility: 'significant',
    }) as { data: unknown[] }
    const current = buildDirectionalEpisodeMarkArea(a, {
      ...opts,
      phaseVisibility: 'current',
    }) as { data: unknown[] }
    const debug = buildDirectionalEpisodeMarkArea(a, {
      ...opts,
      phaseVisibility: 'debug',
    }) as { data: unknown[] }

    expect(historicalWithSignificantZones.data).toHaveLength(major.length)
    expect(historicalWithAllZones.data).toHaveLength(major.length)
    expect(current.data).toHaveLength(1)
    expect(debug.data).toHaveLength(phases.length)
  })

  it('draws zone formation box and dashed level lines separately', async () => {
    await nextUiUnitStory('Zone renders as a formation box plus dashed level lines', {
      severity: 'normal',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui'],
    })
    const resolver = (d: string | null | undefined) => (d === '2026-04-15' ? 2 : 0)
    const opts = { showZones: true, showProfile: false, profileOpacity: 0.18 }
    // markArea now carries one box per zone (no full-height extension band).
    const area = buildVolumeZoneMarkArea(analysis, opts, resolver, 5) as { data: unknown[] }
    expect(area.data).toHaveLength(1)
    // The level extension is a separate dashed markLine (2 lines: low + high).
    const line = buildZoneLevelMarkLine(analysis, opts, resolver, 5) as { data: unknown[] } | undefined
    expect(line?.data).toHaveLength(2)
  })

  it('exposes a per-zone hover tooltip overlay with the zone details', async () => {
    await nextUiUnitStory('Zone hover overlay carries the description tooltip', {
      severity: 'normal',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui'],
    })
    const resolver = () => 0
    const z = { ...analysis.zones[0]!, source_profile: 'BOTH' as const, structural_strength: 42, active_strength: 10, top_session_dates: ['2026-01-02', '2026-01-03'] }
    const a = { ...analysis, zones: [z] }
    const opts = { showZones: true, showProfile: false, profileOpacity: 0.18 }
    expect(buildZoneHoverSeries(a, opts)).toBeNull() // no resolver -> no overlay
    const series = buildZoneHoverSeries(a, opts, resolver, 5) as { data: Array<Array<number | string>>; encode: { y: number[] }; tooltip: { formatter: (p: { data: Array<number | string> }) => string } }
    expect(series.data).toHaveLength(1)
    // y-axis extent must come from the price dims, not the index dims, or the
    // price axis blows up to ~candle-count scale.
    expect(series.encode.y).toEqual([2, 3])
    const html = series.tooltip.formatter({ data: series.data[0]! })
    expect(html).toContain('Zakres ceny')
    expect(html).toContain('Raw volume')
    expect(html).toContain('Top dni: 2026-01-02')
    expect(html).toContain('Strukturalny + aktywny')
  })

  it('filters rendered zones by visibility mode', async () => {
    await nextUiUnitStory('Zone visibility modes select which zones render', {
      severity: 'normal',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui'],
    })
    const base = analysis.zones[0]!
    const multi: VolumeZonesResponse = {
      ...analysis,
      highlighted_zone_ids: ['zone-1'],
      active_zone: { ...base, zone_id: 'zone-1' },
      zones: [
        { ...base, zone_id: 'zone-1', display_priority: 1, lifecycle_status: 'ACTIVE' },
        { ...base, zone_id: 'zone-2', display_priority: null, lifecycle_status: 'CLOSED', center_price: 80 },
        { ...base, zone_id: 'zone-3', display_priority: null, lifecycle_status: null, center_price: 90 },
      ],
    }
    const opts = { showZones: true, showProfile: false, profileOpacity: 0.18 }
    const all = buildVolumeZoneMarkArea(multi, { ...opts, zoneVisibility: 'all' }) as { data: unknown[] }
    const significant = buildVolumeZoneMarkArea(multi, { ...opts, zoneVisibility: 'significant' }) as { data: unknown[] }
    const active = buildVolumeZoneMarkArea(multi, { ...opts, zoneVisibility: 'active' }) as { data: unknown[] }
    expect(all.data).toHaveLength(3)
    expect(significant.data).toHaveLength(1)
    expect(active.data).toHaveLength(1)
  })
})
