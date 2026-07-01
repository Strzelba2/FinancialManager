import { describe, expect, it, vi } from 'vitest'

import {
  buildPerfRowsFromHoldings,
  computeAssetsChartData,
  computeDashFlowData,
  computeExpensesYtd,
  computeGoalsProgress,
} from '@/app/(dashboard)/wallet/page'
import { computeDashFlowProfit } from '@/features/wallet/components/DashFlowCard'
import type { HoldingRawRow } from '@/lib/api/holdings'
import type { WalletListItem, YearGoalOut } from '@/lib/types/wallet'
import { nextUiUnitStory } from '../allure'

function walletFixture(overrides: Partial<WalletListItem> = {}): WalletListItem {
  return {
    id: 'wallet-1',
    name: 'Main wallet',
    accounts: [],
    brokerage_accounts: [],
    debts: [],
    real_estates: [],
    metal_holdings: [],
    capital_gains_deposit_ytd: {},
    capital_gains_broker_ytd: {},
    capital_gains_real_estate_ytd: {},
    capital_gains_metal_ytd: {},
    expense_ytd_by_currency: {},
    income_ytd_by_currency: {},
    top_gainers: [],
    top_losers: [],
    last_brokerage_events: [],
    recurring_expenses_top: [],
    dash_flow_8m: [],
    ...overrides,
  }
}

function performanceFixture(symbol: string, pnlPct: number, pnlAmount: number): HoldingRawRow {
  const cost = 1000
  const value = cost + pnlAmount
  return {
    id: symbol,
    accountId: 'aggregated',
    symbol,
    instrumentMic: 'XWAR',
    name: symbol,
    currency: 'PLN',
    accountsDisp: '2 rachunki',
    accountBreakdown: [
      { accountId: 'account-1', accountName: 'Rachunek 1', quantity: 5, costRaw: cost / 2 },
      { accountId: 'account-2', accountName: 'Rachunek 2', quantity: 5, costRaw: cost / 2 },
    ],
    quantity: 10,
    avgCostRaw: cost / 10,
    priceRaw: value / 10,
    costRaw: cost,
    valueRaw: value,
    pnlAmountRaw: pnlAmount,
    pnlPct,
    costView: cost,
    valueView: value,
    pnlView: pnlAmount,
    changePct: 0,
    quoteMissing: false,
  }
}

describe('wallet page calculations', () => {
  it('selects five of six cross-wallet aggregated gainers and losers', async () => {
    await nextUiUnitStory('Wallet dashboard ranks aggregated holdings across every selected wallet', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'money', 'next-ui'],
    })

    const rows = [
      performanceFixture('GAIN-1', 0.5, 500),
      performanceFixture('GAIN-2', 1, 1000),
      performanceFixture('GAIN-3', 0.8, 800),
      performanceFixture('GAIN-4', 0.7, 700),
      performanceFixture('GAIN-5', 0.6, 600),
      performanceFixture('GAIN-6', 0.4, 400),
      performanceFixture('LOSS-1', -0.6, -600),
      performanceFixture('LOSS-2', -0.9, -900),
      performanceFixture('LOSS-3', -0.8, -800),
      performanceFixture('LOSS-4', -0.7, -700),
      performanceFixture('LOSS-5', -0.5, -500),
      performanceFixture('LOSS-6', -0.4, -400),
    ]

    const gainers = buildPerfRowsFromHoldings(rows, 'PLN', 'desc')
    const losers = buildPerfRowsFromHoldings(rows, 'PLN', 'asc')

    expect(gainers.map((row) => row.sym)).toEqual(['GAIN-2', 'GAIN-3', 'GAIN-4', 'GAIN-5', 'GAIN-1'])
    expect(losers.map((row) => row.sym)).toEqual(['LOSS-2', 'LOSS-3', 'LOSS-4', 'LOSS-1', 'LOSS-5'])
    expect(gainers.every((row) => row.pl_pct > 0)).toBe(true)
    expect(losers.every((row) => row.pl_pct < 0)).toBe(true)
    expect(gainers[0]).toMatchObject({ pl_pct: 100, pl_abs_fmt: '+1\u00a0000 PLN' })
    expect(losers[0]).toMatchObject({ pl_pct: -90, pl_abs_fmt: '-900 PLN' })
  })

  it('shows YTD expenses as an absolute value while preserving the existing aggregate', async () => {
    await nextUiUnitStory('Wallet dashboard YTD expenses use absolute display value', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'money', 'next-ui'],
    })

    const expenses = computeExpensesYtd([
      walletFixture({ expense_ytd_by_currency: { PLN: '-143630.00' } }),
      walletFixture({ expense_ytd_by_currency: { PLN: '-45.00' } }),
    ], 'PLN', null)

    expect(expenses.toFixed(2)).toBe('143675.00')
  })

  it('shows full income in Dash Flow and adds capital to profit', async () => {
    await nextUiUnitStory('Wallet dashboard Dash Flow profit includes income and capital', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'money', 'next-ui'],
    })

    const flow = computeDashFlowData([
      walletFixture({
        dash_flow_8m: [
          {
            month: '2026-05',
            income_by_currency: { PLN: '1050.00' },
            expense_by_currency: { PLN: '-300.00' },
            tax_by_currency: { PLN: '-190.00' },
            capital_by_currency: { PLN: '50.00' },
          },
        ],
      }),
    ], 'PLN', null)

    expect(flow.months).toEqual(['2026-05'])
    expect(flow.inc).toEqual([1050])
    expect(flow.tax).toEqual([-190])
    expect(flow.cap).toEqual([50])
    expect(computeDashFlowProfit(flow)).toEqual([610])
  })

  it('uses positive expenses and separate capital gains in YTD goals', async () => {
    await nextUiUnitStory('Wallet dashboard YTD goals separate income expenses and capital gains', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'money', 'next-ui'],
    })

    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-13T12:00:00Z'))

    const goals: YearGoalOut[] = [
      {
        id: 'goal-1',
        wallet_id: 'wallet-1',
        year: 2026,
        rev_target_year: '12000.00',
        exp_budget_year: '6000.00',
        capital_gain_target_year: '2400.00',
        currency: 'PLN',
      },
    ]

    try {
      const progress = computeGoalsProgress(goals, [
        walletFixture({
          income_ytd_by_currency: { PLN: '5000.00' },
          expense_ytd_by_currency: { PLN: '-1200.00' },
          capital_gains_broker_ytd: { PLN: '700.00' },
          capital_gains_metal_ytd: { PLN: '-100.00' },
        }),
      ], 2026, 'PLN', null)

      expect(progress).not.toBeNull()
      expect(progress?.revActual).toBe(5000)
      expect(progress?.expActual).toBe(1200)
      expect(progress?.capActual).toBe(600)
      expect(progress?.capTarget).toBe(1200)
    } finally {
      vi.useRealTimers()
    }
  })

  it('uses nominal assets only when CPI is missing', async () => {
    await nextUiUnitStory('Wallet dashboard assets chart keeps nominal assets when CPI is unavailable', {
      severity: 'critical',
      tags: ['wallet', 'dashboard', 'snapshots', 'cpi', 'next-ui'],
    })

    const chart = computeAssetsChartData(
      { months: ['2026-05', '2026-06'], values: [1000, 1100] },
      null,
      'PLN',
    )

    expect(chart.months).toEqual(['2026-05', '2026-06'])
    expect(chart.nominal).toEqual([1000, 1100])
    expect(chart.real).toEqual([])
    expect(chart.inflacja).toEqual([])
    expect(chart.mom).toEqual([0, 100])
  })

  it('derives real assets from CPI YoY rates', async () => {
    await nextUiUnitStory('Wallet dashboard assets chart converts YoY CPI rates into a real assets series', {
      severity: 'critical',
      tags: ['wallet', 'dashboard', 'snapshots', 'cpi', 'inflation', 'next-ui'],
    })

    const chart = computeAssetsChartData(
      { months: ['2026-05', '2026-06'], values: [1000, 1100] },
      { index_by_month: { '2026-05': 12, '2026-06': 12 } },
      'PLN',
    )

    expect(chart.nominal).toEqual([1000, 1100])
    expect(chart.inflacja).toEqual([12, 12])
    expect(chart.real[0]).toBeCloseTo(1000, 5)
    expect(chart.real[1]).toBeLessThan(1100)
    expect(chart.real[1]).toBeCloseTo(1089.66, 2)
  })

  it('distinguishes CPI index values from YoY CPI rates', async () => {
    await nextUiUnitStory('Wallet dashboard assets chart uses CPI index values directly when CPI is not a YoY rate', {
      severity: 'critical',
      tags: ['wallet', 'dashboard', 'snapshots', 'cpi-index', 'inflation', 'next-ui'],
    })

    const chart = computeAssetsChartData(
      { months: ['2026-05', '2026-06'], values: [1000, 1100] },
      { index_by_month: { '2026-05': 100, '2026-06': 110 } },
      'PLN',
    )

    expect(chart.inflacja[0]).toBeCloseTo(0, 5)
    expect(chart.inflacja[1]).toBeCloseTo(10, 5)
    expect(chart.real[0]).toBeCloseTo(1000, 5)
    expect(chart.real[1]).toBeCloseTo(1000, 5)
  })
})
