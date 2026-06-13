import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { nextUiUnitStory } from '../allure'

const listBrokerageEvents = vi.fn()
const getFxRates = vi.fn()

vi.mock('@/lib/api/wallet', () => ({
  listBrokerageEvents,
}))

vi.mock('@/lib/api/nbp', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/nbp')>('@/lib/api/nbp')
  return {
    ...actual,
    getFxRates,
  }
})

describe('brokerage events API aggregation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.resetModules()
  })

  it('uses live NBP rates to convert brokerage event values', async () => {
    await nextUiUnitStory('Brokerage events API converts values with live NBP rates when available', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'fx', 'next-ui', 'api-client'],
    })

    listBrokerageEvents.mockResolvedValue({
      ok: true,
      data: {
        items: [
          {
            id: 'event-1',
            trade_at: '2026-06-11T09:00:00.000Z',
            brokerage_account_id: 'acc-1',
            brokerage_account_name: 'Makler',
            instrument_symbol: 'LNGA.UK',
            instrument_name: 'LNGA',
            kind: 'BUY',
            quantity: '2',
            price: '10',
            currency: 'USD',
            split_ratio: '0',
            note: null,
          },
        ],
        total: 1,
        page: 1,
        sum_by_ccy: { USD: 20 },
      },
    })
    getFxRates.mockResolvedValue({
      'USD/PLN': 4,
      'EUR/PLN': 4.2,
      'PLN/USD': 0.25,
      'PLN/EUR': 0.2381,
      'USD/EUR': 0.9524,
      'EUR/USD': 1.05,
      'CHF/PLN': 0,
      'CHF/USD': 0,
      'CHF/EUR': 0,
      'GBP/PLN': 0,
      'GBP/USD': 0,
      'GBP/EUR': 0,
    })

    const { fetchEventsPage } = await import('@/lib/api/brokerageEvents')
    const result = await fetchEventsPage({ userId: 'user-1', view_ccy: 'PLN' })

    expect(result.fxRates).not.toBeNull()
    expect(result.rows).toHaveLength(1)
    expect(result.rows[0]?.priceNative).toBe(10)
    expect(result.rows[0]?.priceView).toBe(40)
    expect(result.rows[0]?.notionalView).toBe(80)
    expect(result.pageNotional).toBe(80)
    expect(result.allNotional).toBe(80)
  })

  it('does not invent hardcoded FX rates when NBP is unavailable', async () => {
    await nextUiUnitStory('Brokerage events API avoids fake fallback FX rates when NBP is unavailable', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'fx', 'next-ui', 'api-client'],
    })

    listBrokerageEvents.mockResolvedValue({
      ok: true,
      data: {
        items: [
          {
            id: 'event-1',
            trade_at: '2026-06-11T09:00:00.000Z',
            brokerage_account_id: 'acc-1',
            brokerage_account_name: 'Makler',
            instrument_symbol: 'LNGA.UK',
            instrument_name: 'LNGA',
            kind: 'BUY',
            quantity: '2',
            price: '10',
            currency: 'USD',
            split_ratio: '0',
            note: null,
          },
        ],
        total: 1,
        page: 1,
        sum_by_ccy: { USD: 20 },
      },
    })
    getFxRates.mockResolvedValue(null)

    const { fetchEventsPage } = await import('@/lib/api/brokerageEvents')
    const result = await fetchEventsPage({ userId: 'user-1', view_ccy: 'PLN' })

    expect(result.fxRates).toBeNull()
    expect(result.rows).toHaveLength(1)
    expect(result.rows[0]?.priceNative).toBe(10)
    expect(result.rows[0]?.priceView).toBe(10)
    expect(result.rows[0]?.notionalView).toBe(20)
    expect(result.pageNotional).toBe(20)
    expect(result.allNotional).toBe(20)
  })
})
