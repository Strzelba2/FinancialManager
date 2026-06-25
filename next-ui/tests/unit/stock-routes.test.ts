import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createInstrument, createMarket, getInstruments, getMarkets } from '@/lib/api/stock'
import StockChartsRoute from '@/app/(dashboard)/stock/charts/[mic]/page'
import { GET as getInstrumentsRoute, POST as postInstrumentRoute } from '@/app/api/stock/instruments/route'
import { GET as getMarketsRoute, POST as postMarketRoute } from '@/app/api/stock/markets/route'
import { nextUiUnitStory } from '../allure'

vi.mock('@/features/wallet/components/ChartsPage', () => ({
  ChartsPage: () => null,
}))

vi.mock('@/lib/api/stock', () => ({
  createInstrument: vi.fn(),
  createMarket: vi.fn(),
  getInstruments: vi.fn(),
  getMarkets: vi.fn(),
}))

function jsonRequest(url: string, body: unknown) {
  return new NextRequest(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('stock route handlers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('lists markets with the only-with-instruments filter', async () => {
    await nextUiUnitStory('Stock markets route forwards only-with-instruments filter', {
      severity: 'normal',
      tags: ['stock', 'quotes', 'api-route'],
    })
    vi.mocked(getMarkets).mockResolvedValue({
      ok: true,
      data: [{ mic: 'XLON', name: 'London Stock Exchange' }],
    })

    const response = await getMarketsRoute(new Request('http://localhost/api/stock/markets?only_with_instruments=true'))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual([{ mic: 'XLON', name: 'London Stock Exchange' }])
    expect(getMarkets).toHaveBeenCalledWith({ onlyWithInstruments: true })
  })

  it('normalizes chart route markets and falls back to the first supported MIC', async () => {
    await nextUiUnitStory('Stock charts route normalizes market options for the charts page', {
      severity: 'normal',
      tags: ['stock', 'charts', 'api-route', 'next-ui'],
    })
    vi.mocked(getMarkets).mockResolvedValue({
      ok: true,
      data: [
        { mic: ' xlon ', name: ' London ' },
        { mic: 'BAD', name: 'Invalid' },
      ],
    })
    vi.mocked(getInstruments).mockResolvedValue({
      ok: true,
      data: [{ symbol: 'VOD', shortname: 'Vodafone' }],
    })

    const element = await StockChartsRoute({
      params: Promise.resolve({ mic: 'bad!' }),
      searchParams: Promise.resolve({ symbol: ' vod ' }),
    })

    expect(getMarkets).toHaveBeenCalledWith({ onlyWithInstruments: true })
    expect(getInstruments).toHaveBeenCalledWith('XLON')
    expect(element.props).toEqual({
      mic: 'XLON',
      marketOptions: [{ mic: 'XLON', name: 'London' }],
      instruments: [{ symbol: 'VOD', shortname: 'Vodafone' }],
      preselectedSymbol: 'VOD',
    })
  })

  it('creates a market with an uppercased MIC', async () => {
    await nextUiUnitStory('Stock markets route validates and normalizes manual market creation', {
      severity: 'critical',
      tags: ['stock', 'quotes', 'api-route', 'manual-instrument'],
    })
    vi.mocked(createMarket).mockResolvedValue({
      ok: true,
      data: {
        mic: 'XLON',
        name: 'London Stock Exchange',
        country: 'GB',
        timezone: 'Europe/London',
        currency: 'USD',
        active: true,
      },
      status: 201,
    })

    const response = await postMarketRoute(jsonRequest('http://localhost/api/stock/markets', {
      mic: 'xlon',
      name: 'London Stock Exchange',
      country: 'GB',
      timezone: 'Europe/London',
      currency: 'USD',
      active: true,
    }))

    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toEqual({
      mic: 'XLON',
      name: 'London Stock Exchange',
      country: 'GB',
      timezone: 'Europe/London',
      currency: 'USD',
      active: true,
    })
    expect(createMarket).toHaveBeenCalledWith({
      mic: 'XLON',
      name: 'London Stock Exchange',
      country: 'GB',
      timezone: 'Europe/London',
      currency: 'USD',
      active: true,
    })
  })

  it('returns validation errors for malformed market payloads', async () => {
    await nextUiUnitStory('Stock markets route rejects malformed manual market payloads', {
      severity: 'normal',
      tags: ['stock', 'quotes', 'api-route', 'validation'],
    })

    const response = await postMarketRoute(jsonRequest('http://localhost/api/stock/markets', {
      mic: 'BAD',
      name: '',
      country: 'GB',
      timezone: 'Europe/London',
      currency: 'USD',
    }))

    expect(response.status).toBe(422)
    expect(createMarket).not.toHaveBeenCalled()
  })

  it('requires mic when listing instruments', async () => {
    await nextUiUnitStory('Stock instruments route requires a market MIC filter', {
      severity: 'normal',
      tags: ['stock', 'quotes', 'api-route', 'validation'],
    })

    const response = await getInstrumentsRoute(new Request('http://localhost/api/stock/instruments'))

    expect(response.status).toBe(400)
    expect(getInstruments).not.toHaveBeenCalled()
  })

  it('creates an instrument with normalized symbol fields and quote source', async () => {
    await nextUiUnitStory('Stock instruments route forwards manual quote_source instruments', {
      severity: 'critical',
      tags: ['stock', 'quotes', 'api-route', 'manual-instrument'],
    })
    vi.mocked(createInstrument).mockResolvedValue({
      ok: true,
      data: {
        market_id: 'market-1',
        mic: 'XLON',
        market_mic: 'XLON',
        symbol: 'LNGA.UK',
        shortname: 'LNGA.UK',
        name: null,
        type: 'ETF',
        status: 'ACTIVE',
        currency: 'USD',
        isin: null,
        historical_source: null,
        quote_source: 'https://quotes.example/q/?s=lnga.uk',
      },
      status: 201,
    })

    const response = await postInstrumentRoute(jsonRequest('http://localhost/api/stock/instruments', {
      market_mic: 'xlon',
      symbol: 'lnga.uk',
      shortname: 'lnga.uk',
      name: '',
      type: 'ETF',
      status: 'ACTIVE',
      currency: 'USD',
      isin: '',
      historical_source: '',
      quote_source: 'https://quotes.example/q/?s=lnga.uk',
    }))

    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toEqual({
      market_id: 'market-1',
      mic: 'XLON',
      market_mic: 'XLON',
      symbol: 'LNGA.UK',
      shortname: 'LNGA.UK',
      name: null,
      type: 'ETF',
      status: 'ACTIVE',
      currency: 'USD',
      isin: null,
      historical_source: null,
      quote_source: 'https://quotes.example/q/?s=lnga.uk',
    })
    expect(createInstrument).toHaveBeenCalledWith({
      market_mic: 'XLON',
      symbol: 'LNGA.UK',
      shortname: 'LNGA.UK',
      name: null,
      type: 'ETF',
      status: 'ACTIVE',
      currency: 'USD',
      isin: null,
      historical_source: null,
      quote_source: 'https://quotes.example/q/?s=lnga.uk',
    })
  })

  it('rejects manual instruments with invalid quote_source URLs', async () => {
    await nextUiUnitStory('Stock instruments route validates quote_source URL format', {
      severity: 'normal',
      tags: ['stock', 'quotes', 'api-route', 'validation'],
    })

    const response = await postInstrumentRoute(jsonRequest('http://localhost/api/stock/instruments', {
      market_mic: 'XLON',
      symbol: 'LNGA.UK',
      shortname: 'LNGA.UK',
      type: 'ETF',
      status: 'ACTIVE',
      currency: 'USD',
      quote_source: 'not-a-url',
    }))

    expect(response.status).toBe(422)
    expect(createInstrument).not.toHaveBeenCalled()
  })
})
