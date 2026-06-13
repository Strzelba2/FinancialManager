import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchHoldings } from '@/lib/api/holdings'
import { getFxRates } from '@/lib/api/nbp'
import { getQuotesBySymbols } from '@/lib/api/stock'
import { listBrokerageAccounts, listHoldings } from '@/lib/api/wallet'
import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/wallet', () => ({
  listBrokerageAccounts: vi.fn(),
  listHoldings: vi.fn(),
}))

vi.mock('@/lib/api/stock', () => ({
  getQuotesBySymbols: vi.fn(),
}))

vi.mock('@/lib/api/nbp', () => ({
  getFxRates: vi.fn(),
}))

describe('holdings API aggregation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('aggregates holdings by symbol and marks missing quotes as incomplete value', async () => {
    await nextUiUnitStory('Holdings API does not count missing quotes as zero-value losses', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'quotes', 'financial-data'],
    })
    vi.mocked(listHoldings).mockResolvedValue([
      {
        account_id: 'account-1',
        account_name: 'Makler PLN',
        instrument_id: 'instrument-1',
        instrument_symbol: 'LNGA',
        instrument_mic: 'XLON',
        instrument_name: 'WisdomTree Natural Gas',
        instrument_currency: 'USD',
        quantity: '10',
        avg_cost: '2.00',
      },
      {
        account_id: 'account-2',
        account_name: 'Makler USD',
        instrument_id: 'instrument-1',
        instrument_symbol: 'LNGA',
        instrument_mic: 'XLON',
        instrument_name: 'WisdomTree Natural Gas',
        instrument_currency: 'USD',
        quantity: '5',
        avg_cost: '4.00',
      },
      {
        account_id: 'account-1',
        account_name: 'Makler PLN',
        instrument_id: 'instrument-2',
        instrument_symbol: 'MISSING',
        instrument_mic: 'XLON',
        instrument_name: 'Missing Quote ETF',
        instrument_currency: 'USD',
        quantity: '3',
        avg_cost: '7.00',
      },
    ])
    vi.mocked(listBrokerageAccounts).mockResolvedValue([{ id: 'account-1', name: 'Makler PLN' }])
    vi.mocked(getFxRates).mockResolvedValue({ 'USD/PLN': 4 } as never)
    vi.mocked(getQuotesBySymbols).mockResolvedValue({
      LNGA: { symbol: 'LNGA', price: '5.00', currency: 'USD', change_pct: '1.5' },
    } as never)

    const result = await fetchHoldings({ userId: 'user-1', view_ccy: 'PLN' })

    expect(listHoldings).toHaveBeenCalledWith('user-1', {
      q: undefined,
      brokerage_account_id: undefined,
    })
    expect(getQuotesBySymbols).toHaveBeenCalledWith(['LNGA', 'MISSING'])
    expect(result.totalValueView).toBe(300)
    expect(result.totalCostView).toBe(160)
    expect(result.rows[0]).toMatchObject({
      symbol: 'LNGA',
      accountsDisp: '2 rachunki',
      quantity: 15,
      avgCostRaw: 40 / 15,
      valueRaw: 75,
      valueView: 300,
      pnlView: 140,
      quoteMissing: false,
    })
    expect(result.rows[1]).toMatchObject({
      symbol: 'MISSING',
      valueView: null,
      pnlView: null,
      quoteMissing: true,
    })
  })
})
