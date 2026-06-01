import { describe, expect, it } from 'vitest'

import { computeDashFlowData, computeExpensesYtd } from '@/app/(dashboard)/wallet/page'
import { computeDashFlowProfit } from '@/features/wallet/components/DashFlowCard'
import type { WalletListItem } from '@/lib/types/wallet'
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

  it('adds tax status to Dash Flow and reduces profit by taxes', async () => {
    await nextUiUnitStory('Wallet dashboard Dash Flow reduces profit by transaction taxes', {
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
    expect(flow.inc).toEqual([1000])
    expect(flow.tax).toEqual([-190])
    expect(computeDashFlowProfit(flow)).toEqual([560])
  })
})
