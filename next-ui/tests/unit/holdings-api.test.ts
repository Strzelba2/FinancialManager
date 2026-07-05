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
      accountBreakdown: [
        { accountId: 'account-1', accountName: 'Makler PLN', quantity: 10, costRaw: 20 },
        { accountId: 'account-2', accountName: 'Makler USD', quantity: 5, costRaw: 20 },
      ],
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

  it('uses quote display name when wallet mirror still stores a stale symbol-like name', async () => {
    await nextUiUnitStory('Holdings API prefers quote display names over stale wallet mirrors', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'quotes', 'financial-data'],
    })
    vi.mocked(listHoldings).mockResolvedValue([
      {
        account_id: 'account-1',
        account_name: 'Makler PLN',
        instrument_id: 'instrument-inp',
        instrument_symbol: 'INP',
        instrument_mic: 'XWAR',
        instrument_name: 'inp',
        instrument_currency: 'PLN',
        quantity: '100',
        avg_cost: '7.00',
      },
    ])
    vi.mocked(listBrokerageAccounts).mockResolvedValue([{ id: 'account-1', name: 'Makler PLN' }])
    vi.mocked(getFxRates).mockResolvedValue(null)
    vi.mocked(getQuotesBySymbols).mockResolvedValue({
      INP: { symbol: 'INP', name: 'INPRO', price: '8.25', currency: 'PLN', change_pct: '1.5' },
    } as never)

    const result = await fetchHoldings({ userId: 'user-1', view_ccy: 'PLN' })

    expect(result.rows).toHaveLength(1)
    expect(result.rows[0]).toMatchObject({
      symbol: 'INP',
      name: 'INPRO',
      valueRaw: 825,
      quoteMissing: false,
    })
  })

  it('aggregates twelve ranked symbols across accounts from different wallets', async () => {
    await nextUiUnitStory('Holdings API aggregates cross-wallet quantities and costs before ranking', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'money', 'financial-data'],
    })

    const holding = (
      accountId: string,
      accountName: string,
      symbol: string,
      quantity: string,
      avgCost: string,
    ) => ({
      account_id: accountId,
      account_name: accountName,
      instrument_id: `instrument-${symbol}`,
      instrument_symbol: symbol,
      instrument_mic: 'XWAR',
      instrument_name: symbol,
      instrument_currency: 'PLN',
      quantity,
      avg_cost: avgCost,
    })

    vi.mocked(listHoldings).mockResolvedValue([
      holding('alpha', 'Portfel Alpha', 'GAIN-1', '2', '50'),
      holding('beta', 'Portfel Beta', 'GAIN-1', '3', '100'),
      holding('alpha', 'Portfel Alpha', 'GAIN-2', '10', '10'),
      holding('beta', 'Portfel Beta', 'GAIN-3', '10', '10'),
      holding('alpha', 'Portfel Alpha', 'GAIN-4', '10', '10'),
      holding('beta', 'Portfel Beta', 'GAIN-5', '10', '10'),
      holding('alpha', 'Portfel Alpha', 'GAIN-6', '10', '10'),
      holding('alpha', 'Portfel Alpha', 'LOSS-1', '2', '100'),
      holding('beta', 'Portfel Beta', 'LOSS-1', '2', '50'),
      holding('alpha', 'Portfel Alpha', 'LOSS-2', '10', '10'),
      holding('beta', 'Portfel Beta', 'LOSS-3', '10', '10'),
      holding('alpha', 'Portfel Alpha', 'LOSS-4', '10', '10'),
      holding('beta', 'Portfel Beta', 'LOSS-5', '10', '10'),
      holding('alpha', 'Portfel Alpha', 'LOSS-6', '10', '10'),
    ])
    vi.mocked(listBrokerageAccounts).mockResolvedValue([
      { id: 'alpha', name: 'Portfel Alpha' },
      { id: 'beta', name: 'Portfel Beta' },
    ])
    vi.mocked(getFxRates).mockResolvedValue(null)
    vi.mocked(getQuotesBySymbols).mockResolvedValue({
      'GAIN-1': { symbol: 'GAIN-1', price: '120', currency: 'PLN', change_pct: '0' },
      'GAIN-2': { symbol: 'GAIN-2', price: '20', currency: 'PLN', change_pct: '0' },
      'GAIN-3': { symbol: 'GAIN-3', price: '18', currency: 'PLN', change_pct: '0' },
      'GAIN-4': { symbol: 'GAIN-4', price: '17', currency: 'PLN', change_pct: '0' },
      'GAIN-5': { symbol: 'GAIN-5', price: '16', currency: 'PLN', change_pct: '0' },
      'GAIN-6': { symbol: 'GAIN-6', price: '14', currency: 'PLN', change_pct: '0' },
      'LOSS-1': { symbol: 'LOSS-1', price: '30', currency: 'PLN', change_pct: '0' },
      'LOSS-2': { symbol: 'LOSS-2', price: '1', currency: 'PLN', change_pct: '0' },
      'LOSS-3': { symbol: 'LOSS-3', price: '2', currency: 'PLN', change_pct: '0' },
      'LOSS-4': { symbol: 'LOSS-4', price: '3', currency: 'PLN', change_pct: '0' },
      'LOSS-5': { symbol: 'LOSS-5', price: '5', currency: 'PLN', change_pct: '0' },
      'LOSS-6': { symbol: 'LOSS-6', price: '6', currency: 'PLN', change_pct: '0' },
    } as never)

    const result = await fetchHoldings({
      userId: 'user-1',
      brokerage_account_id: ['alpha', 'beta'],
      group_mode: 'SYMBOL',
      view_ccy: 'PLN',
    })

    expect(listHoldings).toHaveBeenCalledWith('user-1', {
      q: undefined,
      brokerage_account_id: ['alpha', 'beta'],
    })
    expect(result.rows).toHaveLength(12)
    expect(result.rows.find((item) => item.symbol === 'GAIN-1')).toMatchObject({
      accountsDisp: '2 rachunki',
      accountBreakdown: [
        { accountId: 'alpha', accountName: 'Portfel Alpha', quantity: 2, costRaw: 100 },
        { accountId: 'beta', accountName: 'Portfel Beta', quantity: 3, costRaw: 300 },
      ],
      quantity: 5,
      avgCostRaw: 80,
      costRaw: 400,
      valueRaw: 600,
      pnlAmountRaw: 200,
      pnlPct: 0.5,
      pnlView: 200,
    })
    expect(result.rows.find((item) => item.symbol === 'LOSS-1')).toMatchObject({
      accountsDisp: '2 rachunki',
      accountBreakdown: [
        { accountId: 'alpha', accountName: 'Portfel Alpha', quantity: 2, costRaw: 200 },
        { accountId: 'beta', accountName: 'Portfel Beta', quantity: 2, costRaw: 100 },
      ],
      quantity: 4,
      avgCostRaw: 75,
      costRaw: 300,
      valueRaw: 120,
      pnlAmountRaw: -180,
      pnlPct: -0.6,
      pnlView: -180,
    })
  })
})
