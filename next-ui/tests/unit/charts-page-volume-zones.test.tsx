import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'

import { ChartsPage } from '@/features/wallet/components/ChartsPage'
import type { SyncCandlesResult, VolumeZonesResponse } from '@/lib/api/stock'
import { server } from '../msw-server'
import { nextUiUnitStory } from '../allure'

type ChartOption = {
  series?: Array<{ name?: string }>
}

const chartOptions = vi.hoisted(() => [] as ChartOption[])

vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option: ChartOption }) => {
    chartOptions.push(option)
    return <div data-testid="charts-page-echarts" />
  },
}))

const routerPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: routerPush,
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

function syncCandlesFixture(): SyncCandlesResult {
  return {
    symbol: 'PKN',
    name: 'PKNORLEN',
    fetched_rows: 6,
    upserted_rows: 0,
    returned_count: 6,
    items: [
      { date_quote: '2026-01-02', open: 45, high: 47, low: 44, close: 46, volume: 1200 },
      { date_quote: '2026-01-05', open: 46, high: 48, low: 45, close: 47, volume: 1300 },
      { date_quote: '2026-01-06', open: 47, high: 49, low: 46, close: 48, volume: 1800 },
      { date_quote: '2026-01-07', open: 48, high: 53, low: 47, close: 52, volume: 2200 },
      { date_quote: '2026-01-08', open: 52, high: 55, low: 51, close: 54, volume: 2100 },
      { date_quote: '2026-01-09', open: 54, high: 57, low: 53, close: 56, volume: 2300 },
    ],
  }
}

function volumeZonesFixture(): VolumeZonesResponse {
  return {
    symbol: 'PKN',
    mic: 'XWAR',
    as_of: '2026-01-09',
    calculation_version: '1.3.2',
    configuration_version: '1.3.2',
    data_quality: {
      ohlcv_interval: '1d',
      historical_free_float_available: false,
      current_free_float_used: false,
      current_free_float_pct: null,
      current_free_float_as_of: null,
      current_float_shares: null,
      current_free_float_source: null,
      confidence: 'medium',
      input_rows: 6,
      valid_rows: 6,
      excluded_rows: 0,
      duplicate_dates: [],
      first_date: '2026-01-02',
      last_date: '2026-01-09',
      warnings: [],
    },
    current_state: {
      state: 'MARKUP',
      evidence_score: 72,
      detected_at: '2026-01-06',
      confirmation_price: 53,
      invalidation_price: 44,
      transition_reasons: ['BASE_BREAKOUT_CONFIRMED'],
      active_zone_id: 'zone-1',
      active_episode_id: 'zone-1-episode-1',
    },
    active_zone: null,
    zones: [],
    profile: [],
    highlighted_zone_ids: [],
    directional_episodes: [
      {
        phase_id: 'raw-1',
        phase: 'ACCUMULATION',
        estimated_start_at: '2026-01-02',
        base_end_at: '2026-01-06',
        candidate_at: '2026-01-06',
        active_at: '2026-01-06',
        ended_at: '2026-01-08',
        confirmed_at: '2026-01-08',
        invalidated_at: null,
        price_low: 44,
        price_high: 49,
        center_price: 46.5,
        average_balance: 0.42,
        peak_balance: 0.61,
        cumulative_evidence: 5.4,
        session_count: 4,
        evidence_score: 68,
        status: 'CONFIRMED',
        confirmation_price: 53,
        invalidation_price: 44,
        linked_zone_ids: [],
        setup_score: 72,
        historical_outcome_score: 81,
        subsequent_return_20: 0.16,
        subsequent_return_60: 0.24,
        maximum_favorable_excursion: 0.22,
        maximum_adverse_excursion: -0.03,
        significance_score: 78,
      },
    ],
    resolved_directional_episodes: [],
    major_directional_phases: [
      {
        phase_id: 'major-1',
        phase: 'ACCUMULATION',
        estimated_start_at: '2026-01-02',
        base_end_at: '2026-01-06',
        candidate_at: '2026-01-06',
        active_at: '2026-01-06',
        ended_at: '2026-01-08',
        confirmed_at: '2026-01-08',
        invalidated_at: null,
        price_low: 44,
        price_high: 49,
        center_price: 46.5,
        average_balance: 0.42,
        peak_balance: 0.61,
        cumulative_evidence: 5.4,
        session_count: 4,
        evidence_score: 68,
        status: 'CONFIRMED',
        confirmation_price: 53,
        invalidation_price: 44,
        linked_zone_ids: [],
        setup_score: 72,
        historical_outcome_score: 81,
        subsequent_return_20: 0.16,
        subsequent_return_60: 0.24,
        maximum_favorable_excursion: 0.22,
        maximum_adverse_excursion: -0.03,
        significance_score: 78,
      },
    ],
    timeline: [
      {
        date: '2026-01-06',
        state: 'ACCUMULATION_CANDIDATE',
        evidence_score: 68,
        evidence_balance: 0.42,
        active_zone_id: 'zone-1',
        active_episode_id: 'zone-1-episode-1',
        confirmation_price: 53,
        invalidation_price: 44,
        transition_reasons: ['BASE_BREAKOUT_CONFIRMED'],
      },
    ],
    backtest: null,
  }
}

function latestSeriesNames(): string[] {
  return (chartOptions.at(-1)?.series ?? []).map((series) => series.name ?? '')
}

describe('ChartsPage volume-zone controls', () => {
  beforeEach(() => {
    chartOptions.length = 0
    routerPush.mockClear()
  })

  it('loads volume-zone analysis from the chart screen and keeps A/D disabling in the indicators menu', async () => {
    await nextUiUnitStory('Charts page renders resolved A/D controls only after volume zones are enabled', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'charts', 'next-ui', 'page'],
    })

    const syncRequests: unknown[] = []
    const volumeZoneUrls: string[] = []
    server.use(
      http.post('*/api/stock/candles/sync', async ({ request }) => {
        syncRequests.push(await request.json())
        return HttpResponse.json(syncCandlesFixture())
      }),
      http.get('*/api/stock/analysis/volume-zones', ({ request }) => {
        volumeZoneUrls.push(request.url)
        return HttpResponse.json(volumeZonesFixture())
      }),
    )

    render(
      <ChartsPage
        mic="XWAR"
        instruments={[{ symbol: 'PKN', shortname: 'PKNORLEN' }]}
        preselectedSymbol="PKN"
      />,
    )

    await screen.findByTestId('charts-page-echarts')
    await waitFor(() => {
      expect(syncRequests).toEqual([
        expect.objectContaining({ symbol: 'PKN', return_all: true }),
      ])
    })

    fireEvent.click(screen.getByRole('button', { name: /Wskaźniki/ }))
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Strefa wolumenowa' }))

    await waitFor(() => {
      expect(volumeZoneUrls).toHaveLength(1)
    })
    const url = new URL(volumeZoneUrls[0]!)
    expect(url.searchParams.get('mic')).toBe('XWAR')
    expect(url.searchParams.get('symbol')).toBe('PKN')
    expect(url.searchParams.get('mode')).toBe('full')
    expect(url.searchParams.get('include_timeline')).toBe('true')
    expect(url.searchParams.get('max_zones')).toBe('3')

    const phaseControls = await screen.findByRole('group', { name: 'Widoczność faz A/D' })
    expect(within(phaseControls).getByRole('button', { name: 'A/D historyczne' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(phaseControls).getByRole('button', { name: 'A/D bieżąca' })).toBeInTheDocument()
    expect(within(phaseControls).getByRole('button', { name: 'A/D debug' })).toBeInTheDocument()
    expect(within(phaseControls).queryByRole('button', { name: 'A/D off' })).not.toBeInTheDocument()

    await waitFor(() => {
      expect(latestSeriesNames()).toContain('Fazy A/D')
      expect(latestSeriesNames()).toContain('Wyniki faz A/D')
    })

    fireEvent.mouseDown(screen.getByRole('button', { name: 'Fazy A/D' }))
    await waitFor(() => {
      expect(latestSeriesNames()).not.toContain('Fazy A/D')
      expect(latestSeriesNames()).not.toContain('Wyniki faz A/D')
    })
  })
})
