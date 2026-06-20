import { beforeEach, describe, expect, it, vi } from 'vitest'

import WalletPage from '@/app/(dashboard)/wallet/page'
import { fetchHoldings } from '@/lib/api/holdings'
import { getFxRates } from '@/lib/api/nbp'
import { getStockServiceStatus } from '@/lib/api/stock'
import {
  getLatestRealEstatePrice,
  listRecurringExpenses,
  listWalletGoals,
  syncUser,
} from '@/lib/api/wallet'
import type { WalletListItem, WalletSyncResponse } from '@/lib/types/wallet'
import { nextUiUnitStory } from '../allure'

const mocks = vi.hoisted(() => ({
  headerGet: vi.fn(),
}))

vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({ get: mocks.headerGet })),
}))

vi.mock('@/lib/api/session', () => ({
  saveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  getLatestRealEstatePrice: vi.fn(),
  listRecurringExpenses: vi.fn(),
  listWalletGoals: vi.fn(),
  syncUser: vi.fn(),
}))

vi.mock('@/lib/api/holdings', () => ({
  fetchHoldings: vi.fn(),
}))

vi.mock('@/lib/api/nbp', () => ({
  getFxRates: vi.fn(),
}))

vi.mock('@/lib/api/stock', () => ({
  getStockServiceStatus: vi.fn(),
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

function walletFixture(id: string, name: string, brokerageAccountId: string): WalletListItem {
  return {
    id,
    name,
    accounts: [{
      id: `${id}-current`,
      name: `${name} current account`,
      bank_id: 'bank-1',
      account_type: 'CURRENT',
      currency: 'PLN',
      available: '1000.00',
      blocked: '0.00',
      last_transactions: [],
    }],
    brokerage_accounts: [{
      id: brokerageAccountId,
      name: `${name} brokerage account`,
      totals_by_currency: { PLN: '1000.00' },
    }],
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
  }
}

describe('wallet page holdings integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.headerGet.mockImplementation((name: string) => {
      if (name === 'x-user') return 'artur'
      if (name === 'x-user-id') return 'wallet-user-1'
      return ''
    })
  })

  it('loads symbol-aggregated holdings from every selected wallet for performance cards', async () => {
    await nextUiUnitStory('Wallet dashboard loads cross-wallet holdings for performance ranking', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'money', 'next-ui'],
    })

    const walletData = {
      user_id: 'wallet-user-1',
      first_name: 'Artur',
      wallets: [
        walletFixture('wallet-alpha', 'Alpha', 'brokerage-alpha'),
        walletFixture('wallet-beta', 'Beta', 'brokerage-beta'),
      ],
      banks: [{ id: 'bank-1', name: 'Test Bank', shortname: 'TB' }],
      last_favorite_items: [],
      last_price_alerts: [],
      assets_8m_total: null,
      cpi_8m: null,
    } satisfies WalletSyncResponse

    vi.mocked(syncUser).mockResolvedValue(walletData)
    vi.mocked(fetchHoldings).mockResolvedValue({
      rows: [],
      totalValueView: 0,
      totalCostView: 0,
      viewCcy: 'EUR',
      fxRates: null,
      brokerageAccounts: [],
    })
    vi.mocked(getFxRates).mockResolvedValue(null)
    vi.mocked(getStockServiceStatus).mockResolvedValue({ available: true })
    vi.mocked(getLatestRealEstatePrice).mockResolvedValue(null)
    vi.mocked(listWalletGoals).mockResolvedValue({ ok: true, data: [], status: 200 })
    vi.mocked(listRecurringExpenses).mockResolvedValue({ ok: true, data: [], status: 200 })

    await WalletPage({
      searchParams: Promise.resolve({ wallet: 'all', currency: 'EUR' }),
    })

    expect(fetchHoldings).toHaveBeenCalledOnce()
    expect(fetchHoldings).toHaveBeenCalledWith({
      userId: 'wallet-user-1',
      brokerage_account_id: ['brokerage-alpha', 'brokerage-beta'],
      group_mode: 'SYMBOL',
      view_ccy: 'EUR',
    })
  })
})
