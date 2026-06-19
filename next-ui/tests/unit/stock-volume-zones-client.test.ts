import { afterEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'

import { server } from '../msw-server'
import { nextUiUnitStory } from '../allure'

afterEach(() => {
  server.resetHandlers()
  vi.resetModules()
  delete process.env.STOCK_API_URL
})

describe('stock volume-zone API client', () => {
  it('requests the deterministic volume-zone endpoint with encoded options', async () => {
    await nextUiUnitStory('Stock API client fetches deterministic volume-zone analysis', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'api-client', 'api-contract'],
    })
    const requests: Request[] = []
    server.use(http.get('http://stock:8001/stock/analysis/XWAR/PKO/volume-zones', ({ request }) => {
      requests.push(request)
      return HttpResponse.json({
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
          evidence_score: 61,
          detected_at: '2026-05-01',
          confirmation_price: 72.4,
          invalidation_price: 63.8,
          transition_reasons: ['HIGH_RELATIVE_VOLUME'],
          active_zone_id: 'zone-1',
          active_episode_id: 'zone-1-episode-1',
        },
        active_zone: null,
        zones: [],
        profile: [],
        directional_episodes: [],
        resolved_directional_episodes: [],
        major_directional_phases: [{
          phase_id: 'major-phase-1',
          phase: 'ACCUMULATION',
          estimated_start_at: '2026-01-10',
          base_end_at: '2026-01-18',
          candidate_at: '2026-01-20',
          active_at: null,
          ended_at: '2026-01-25',
          confirmed_at: '2026-01-25',
          invalidated_at: null,
          price_low: 63,
          price_high: 68,
          center_price: 65.5,
          average_balance: 0.42,
          peak_balance: 0.68,
          cumulative_evidence: 8.2,
          session_count: 12,
          evidence_score: 55,
          status: 'CONFIRMED',
          confirmation_price: 69,
          invalidation_price: 62,
          linked_zone_ids: [],
          setup_score: 61.4,
          historical_outcome_score: 72.8,
          subsequent_return_20: 12.4,
          subsequent_return_60: 24.2,
          maximum_favorable_excursion: 31.5,
          maximum_adverse_excursion: -4.1,
          expected_direction_return: 24.2,
          opposite_move_penalty: 4.1,
          outcome_lookahead_sessions: 60,
          significance_score: 61.4,
        }],
        timeline: [],
        backtest: null,
      })
    }))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getVolumeZones } = await import('@/lib/api/stock')

    const result = await getVolumeZones('XWAR', 'PKO', {
      mode: 'summary',
      dateFrom: '2026-01-01',
      includeTimeline: true,
      maxZones: 3,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error(result.error)
    expect(requests).toHaveLength(1)
    const url = new URL(requests[0]!.url)
    expect(url.pathname).toBe('/stock/analysis/XWAR/PKO/volume-zones')
    expect(url.searchParams.get('mode')).toBe('summary')
    expect(url.searchParams.get('date_from')).toBe('2026-01-01')
    expect(url.searchParams.get('include_timeline')).toBe('true')
    expect(url.searchParams.get('max_zones')).toBe('3')
    expect(result.data.major_directional_phases?.[0]?.historical_outcome_score).toBe(72.8)
  })
})
