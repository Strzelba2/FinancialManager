import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'

import { ChartsPage } from '@/features/wallet/components/ChartsPage'
import type { SyncCandlesResult, VolumeZonesResponse } from '@/lib/api/stock'
import { server } from '../msw-server'
import { nextUiUnitStory } from '../allure'

type ChartDataPoint = number | null | { value?: number | null; raw?: number | null; scaleMode?: string }
type ChartSeries = {
  id?: string
  name?: string
  data?: ChartDataPoint[]
  connectNulls?: boolean
  stack?: string
  areaStyle?: { color?: string; opacity?: number }
}
type ChartOption = {
  series?: ChartSeries[]
  tooltip?: { show?: boolean; formatter?: (params: unknown[]) => string }
  axisPointer?: { show?: boolean }
  yAxis?: Array<{ axisLabel?: { formatter?: (value: number) => string } }>
}
type ChartEvents = { click?: (params: unknown) => void }

const chartOptions = vi.hoisted(() => [] as ChartOption[])
const chartEvents = vi.hoisted(() => [] as ChartEvents[])

vi.mock('echarts-for-react', () => ({
  default: ({ option, onEvents }: { option: ChartOption; onEvents?: ChartEvents }) => {
    chartOptions.push(option)
    if (onEvents) chartEvents.push(onEvents)
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

function syncCandlesFixture(symbol = 'PKN', name = 'PKNORLEN', closes?: number[]): SyncCandlesResult {
  const baseItems = [
    { date_quote: '2026-01-02', open: 45, high: 47, low: 44, close: 46, volume: 1200 },
    { date_quote: '2026-01-05', open: 46, high: 48, low: 45, close: 47, volume: 1300 },
    { date_quote: '2026-01-06', open: 47, high: 49, low: 46, close: 48, volume: 1800 },
    { date_quote: '2026-01-07', open: 48, high: 53, low: 47, close: 52, volume: 2200 },
    { date_quote: '2026-01-08', open: 52, high: 55, low: 51, close: 54, volume: 2100 },
    { date_quote: '2026-01-09', open: 54, high: 57, low: 53, close: 56, volume: 2300 },
  ]
  const items = closes
    ? closes.map((close, index) => {
      const date = new Date(Date.UTC(2026, 0, 2 + index)).toISOString().slice(0, 10)
      const item = baseItems[index] ?? { volume: 1200 + (index * 100) }
      return {
        date_quote: date,
        open: Number((close * 0.98).toFixed(4)),
        high: Number((close * 1.02).toFixed(4)),
        low: Number((close * 0.96).toFixed(4)),
        close,
        volume: item.volume,
      }
    })
    : baseItems

  return {
    symbol,
    name,
    fetched_rows: items.length,
    upserted_rows: 0,
    returned_count: items.length,
    items,
  }
}

function latestOption(): ChartOption {
  return chartOptions.at(-1) ?? {}
}

function lineTooltipHtml(option: ChartOption, params: unknown[]): string {
  const formatter = option.tooltip?.formatter
  expect(formatter).toBeTypeOf('function')
  return formatter?.(params) ?? ''
}

function lineParam(seriesName: string, value: number, raw: number, scaleMode: string) {
  return {
    axisValue: '2026-01-02',
    seriesType: 'line',
    seriesName,
    marker: '<span></span>',
    color: '#3b82f6',
    value: { value },
    data: { value, raw, scaleMode },
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

function latestSeries(name: string): ChartSeries | undefined {
  return (chartOptions.at(-1)?.series ?? []).find((series) => series.name === name)
}

function clickChartSeries(seriesName: string) {
  chartEvents.at(-1)?.click?.({ componentType: 'series', seriesName })
}

function pointValue(point: ChartDataPoint | undefined): number | null {
  if (point == null) return null
  if (typeof point === 'number') return point
  return point.value ?? null
}

function pointRaw(point: ChartDataPoint | undefined): number | null {
  if (point == null || typeof point === 'number') return null
  return point.raw ?? null
}

describe('ChartsPage volume-zone controls', () => {
  beforeEach(() => {
    chartOptions.length = 0
    chartEvents.length = 0
    routerPush.mockClear()
    localStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('keeps selected line series while adding another market to the overlay', async () => {
    await nextUiUnitStory('Charts page overlays line series selected from different markets', {
      severity: 'normal',
      tags: ['stock', 'charts', 'markets', 'line-overlay', 'next-ui', 'page'],
    })

    const syncRequests: Array<{ symbol?: string }> = []
    server.use(
      http.get('*/api/stock/instruments', ({ request }) => {
        const url = new URL(request.url)
        const mic = url.searchParams.get('mic')
        if (mic === 'XLON') return HttpResponse.json([{ symbol: 'VOD', shortname: 'Vodafone' }])
        return HttpResponse.json([])
      }),
      http.post('*/api/stock/candles/sync', async ({ request }) => {
        const body = await request.json() as { symbol?: string }
        syncRequests.push(body)
        return HttpResponse.json(syncCandlesFixture(
          body.symbol ?? 'PKN',
          body.symbol === 'VOD' ? 'Vodafone' : 'PKNORLEN',
          body.symbol === 'VOD' ? [2, 2.2, 2.1, 2.4, 2.8, 3] : undefined,
        ))
      }),
    )

    render(
      <ChartsPage
        mic="XWAR"
        marketOptions={[
          { mic: 'XWAR', name: 'GPW' },
          { mic: 'XLON', name: 'London' },
        ]}
        instruments={[{ symbol: 'PKN', shortname: 'PKNORLEN' }]}
        preselectedSymbol={null}
      />,
    )

    const instrumentInput = screen.getByPlaceholderText('Dodaj instrument…')
    fireEvent.change(instrumentInput, { target: { value: 'PKN' } })
    fireEvent.mouseDown(await screen.findByRole('button', { name: /PKN/ }))
    expect(screen.getByText('PKN · GPW')).toBeInTheDocument()

    const marketSelect = screen.getByRole('combobox', { name: 'Market' })
    expect(within(marketSelect).getByText('GPW')).toBeInTheDocument()
    fireEvent.click(marketSelect)
    const londonOption = await screen.findByRole('option', { name: 'London' })
    fireEvent.click(londonOption)

    expect(routerPush).not.toHaveBeenCalled()
    expect(screen.getByText('PKN · GPW')).toBeInTheDocument()

    fireEvent.change(instrumentInput, { target: { value: 'VOD' } })
    fireEvent.mouseDown(await screen.findByRole('button', { name: /VOD/ }))
    expect(screen.getByText('VOD · London')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Liniowy/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Nakładany' }))
    fireEvent.click(screen.getByRole('button', { name: /Sync & Render/ }))

    await waitFor(() => {
      expect(syncRequests.map((request) => request.symbol)).toEqual(['PKN', 'VOD'])
    })
    await waitFor(() => {
      expect(latestSeriesNames()).toContain('PKN · GPW')
      expect(latestSeriesNames()).toContain('VOD · London')
    })
    expect(latestSeries('PKN · GPW')?.connectNulls).toBe(true)
    expect(pointValue(latestSeries('PKN · GPW')?.data?.[0])).toBeCloseTo(0)
    expect(pointValue(latestSeries('PKN · GPW')?.data?.[1])).toBeCloseTo(0)
    expect(pointRaw(latestSeries('PKN · GPW')?.data?.[1])).toBeCloseTo(46)
    expect(pointValue(latestSeries('VOD · London')?.data?.[0])).toBeCloseTo(0)
    expect(pointValue(latestSeries('VOD · London')?.data?.[1])).toBeCloseTo(20)
    expect(pointRaw(latestSeries('VOD · London')?.data?.[1])).toBeCloseTo(2.2)

    fireEvent.click(screen.getByRole('button', { name: 'Indeks 100' }))
    await waitFor(() => {
      expect(pointValue(latestSeries('VOD · London')?.data?.[0])).toBeCloseTo(100)
      expect(pointValue(latestSeries('VOD · London')?.data?.[1])).toBeCloseTo(110)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Zmiana %' }))
    await waitFor(() => {
      expect(pointValue(latestSeries('VOD · London')?.data?.[0])).toBeCloseTo(0)
      expect(pointValue(latestSeries('VOD · London')?.data?.[1])).toBeCloseTo(10)
    })
  })

  it('scales line indicators and keeps raw prices visible in the tooltip', async () => {
    await nextUiUnitStory('Charts page scales overlay indicators and tooltip values for line comparison', {
      severity: 'normal',
      tags: ['stock', 'charts', 'line-overlay', 'indicators', 'next-ui', 'page'],
    })

    const closes = Array.from({ length: 25 }, (_, index) => 2 + (index * 0.5))
    server.use(
      http.post('*/api/stock/candles/sync', () => (
        HttpResponse.json(syncCandlesFixture('PKN', 'PKNORLEN', closes))
      )),
    )

    render(
      <ChartsPage
        mic="XWAR"
        instruments={[{ symbol: 'PKN', shortname: 'PKNORLEN' }]}
        preselectedSymbol={null}
      />,
    )

    const instrumentInput = screen.getByPlaceholderText('Dodaj instrument…')
    fireEvent.change(instrumentInput, { target: { value: 'PKN' } })
    fireEvent.mouseDown(await screen.findByRole('button', { name: /PKN/ }))
    fireEvent.click(screen.getByRole('button', { name: /Liniowy/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Nakładany' }))
    fireEvent.click(screen.getByRole('button', { name: /Sync & Render/ }))

    await screen.findByTestId('charts-page-echarts')

    fireEvent.click(screen.getByRole('button', { name: /Wskaźniki/ }))
    fireEvent.mouseDown(screen.getByRole('button', { name: 'SMA 7' }))
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'SMA 7' })).not.toBeInTheDocument()
      expect(latestOption().axisPointer?.show).toBe(false)
    })
    fireEvent.click(screen.getByRole('button', { name: /Wskaźniki/ }))
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Bollinger Bands (20)' }))

    await waitFor(() => {
      expect(latestSeriesNames()).toContain('PKN · GPW SMA7')
      expect(latestSeriesNames()).toContain('BB Upper')
      expect(latestSeriesNames()).toContain('BB Lower')
      expect(screen.queryByRole('button', { name: 'Bollinger Bands (20)' })).not.toBeInTheDocument()
      expect(latestOption().axisPointer?.show).toBe(false)
    })

    const smaPoint = latestSeries('PKN · GPW SMA7')?.data?.[6]
    expect(pointRaw(smaPoint)).toBeCloseTo(3.5)
    expect(pointValue(smaPoint)).toBeCloseTo(12.5)

    const bbPoint = latestSeries('BB Upper')?.data?.[19]
    expect(pointRaw(bbPoint)).not.toBeNull()
    expect(pointValue(bbPoint)).not.toBeNull()

    fireEvent.click(screen.getByTitle('Crosshair'))
    await waitFor(() => {
      expect(latestOption().axisPointer?.show).toBe(true)
    })

    const indexAxisFormatter = latestOption().yAxis?.[0]?.axisLabel?.formatter
    expect(indexAxisFormatter?.(12.345)).toBe('12.35%')

    const tooltipHtml = lineTooltipHtml(latestOption(), [
      lineParam('USDPLN · PLN', 110, 2.2, 'index100'),
      lineParam('WIG · Global Indexes', 120, 1234, 'index100'),
      lineParam('CPIYPL.M · MACRO', 25, 4.6, 'rangePercent'),
      lineParam('PKN · GPW', 10, 46, 'percent'),
      lineParam('Raw price', 46, 46, 'price'),
    ])
    expect(tooltipHtml).toContain('110.00 · 2.2000')
    expect(tooltipHtml).toMatch(/120\.00 · 1.?234/u)
    expect(tooltipHtml).toContain('25.00% · 4.6000')
    expect(tooltipHtml).toContain('10.00% · 46.00')
    expect(tooltipHtml).toContain('46.00')

    fireEvent.click(screen.getByRole('button', { name: 'Indeks 100' }))
    await waitFor(() => {
      const index100AxisFormatter = latestOption().yAxis?.[0]?.axisLabel?.formatter
      expect(index100AxisFormatter?.(123.456)).toBe('123.46')
    })
  })

  it('opens Bollinger settings from a band line and persists the edited period with chart settings', async () => {
    await nextUiUnitStory('Charts page edits and saves Bollinger indicator settings from the chart line', {
      severity: 'normal',
      tags: ['stock', 'charts', 'indicators', 'bollinger', 'next-ui', 'page'],
    })

    const closes = Array.from({ length: 40 }, (_, index) => 10 + index)
    server.use(
      http.post('*/api/stock/candles/sync', () => (
        HttpResponse.json(syncCandlesFixture('PKN', 'PKNORLEN', closes))
      )),
    )

    render(
      <ChartsPage
        mic="XWAR"
        instruments={[{ symbol: 'PKN', shortname: 'PKNORLEN' }]}
        preselectedSymbol="PKN"
      />,
    )

    await screen.findByTestId('charts-page-echarts')

    fireEvent.click(screen.getByRole('button', { name: /Wskaźniki/ }))
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Bollinger Bands (20)' }))

    await waitFor(() => {
      expect(pointValue(latestSeries('BB Upper')?.data?.[19])).not.toBeNull()
      expect(screen.queryByRole('button', { name: 'Bollinger Bands (20)' })).not.toBeInTheDocument()
      expect(latestOption().axisPointer?.show).toBe(false)
    })

    act(() => clickChartSeries('BB Upper'))

    const dialog = await screen.findByRole('dialog', { name: 'Bollinger Bands (20, 2)' })
    fireEvent.change(within(dialog).getByLabelText('Period'), { target: { value: '33' } })
    fireEvent.click(within(dialog).getByLabelText('Channel fill'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'OK' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Bollinger Bands (20, 2)' })).not.toBeInTheDocument()
      expect(pointValue(latestSeries('BB Upper')?.data?.[19])).toBeNull()
      expect(pointValue(latestSeries('BB Upper')?.data?.[32])).not.toBeNull()
      expect(latestSeriesNames()).toContain('BB Fill')
    })
    expect(latestSeries('BB Fill')?.stack).toBe('bb-fill')
    expect(latestSeries('BB Fill')?.areaStyle?.color).toBe('rgba(245,158,11,0.10)')

    fireEvent.click(screen.getByTitle('Zapisz rysunki i wskaźniki'))

    const rawSaved = localStorage.getItem('chart_state_PKN · GPW')
    expect(rawSaved).not.toBeNull()
    const saved = JSON.parse(rawSaved ?? '{}') as {
      indicators?: string[]
      indicatorSettings?: { bollinger?: { period?: number; standardDeviations?: number; channelFill?: boolean } }
    }
    expect(saved.indicators).toContain('bb')
    expect(saved.indicatorSettings?.bollinger?.period).toBe(33)
    expect(saved.indicatorSettings?.bollinger?.standardDeviations).toBe(2)
    expect(saved.indicatorSettings?.bollinger?.channelFill).toBe(true)
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
      expect(screen.queryByRole('button', { name: 'Strefa wolumenowa' })).not.toBeInTheDocument()
      expect(latestOption().axisPointer?.show).toBe(false)
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

    fireEvent.click(screen.getByRole('button', { name: /Wskaźniki/ }))
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Fazy A/D' }))
    await waitFor(() => {
      expect(latestSeriesNames()).not.toContain('Fazy A/D')
      expect(latestSeriesNames()).not.toContain('Wyniki faz A/D')
    })
  })
})
