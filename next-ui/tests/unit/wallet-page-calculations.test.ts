import { describe, expect, it, vi } from 'vitest'

import { computeDashFlowData, computeExpensesYtd, computeGoalsProgress } from '@/app/(dashboard)/wallet/page'
import { computeDashFlowProfit } from '@/features/wallet/components/DashFlowCard'
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

describe('wallet page calculations', () => {
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
})
