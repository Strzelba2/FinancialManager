import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'

import { WalletManagerPage } from '@/features/wallet/components/WalletManagerPage'
import type { WalletManagerNode } from '@/lib/api/wallet'
import type { FxRates } from '@/lib/api/nbp'
import { nextUiUnitStory } from '../allure'

const routerRefresh = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: routerRefresh }),
}))

const fxRates: FxRates = {
  'USD/PLN': 4,
  'EUR/PLN': 4.5,
  'PLN/USD': 0.25,
  'PLN/EUR': 0.2222,
  'USD/EUR': 0.8889,
  'EUR/USD': 1.125,
  'CHF/PLN': 4.6,
  'CHF/USD': 1.15,
  'CHF/EUR': 1.0222,
  'GBP/PLN': 5,
  'GBP/USD': 1.25,
  'GBP/EUR': 1.1111,
}

function walletNode(): WalletManagerNode {
  return {
    id: 'wallet-1',
    name: 'FUNDUSZ Rodzinny',
    deposit_accounts: [],
    brokerage_accounts: [
      {
        id: '11111111-1111-4111-8111-111111111111',
        name: 'Maklerskie ING Artur',
        ccy: 'PLN',
        sum_cash_accounts: '200',
        positions_value: '1000',
        positions_count: 2,
        events_per_month: 4,
        cash_accounts: [
          {
            deposit_account_id: 'cash-pln',
            name: 'Maklerskie ING Artur',
            ccy: 'PLN',
            available: '100',
          },
          {
            deposit_account_id: 'cash-usd',
            name: 'Maklerskie ING Artur · USD',
            ccy: 'USD',
            available: '25',
          },
        ],
        positions: [
          {
            symbol: 'PKO',
            mic: 'XWAR',
            currency: 'PLN',
            value: '800',
            value_default_ccy: '800',
            pnl_pct: '0.5',
          },
          {
            symbol: 'CPS',
            mic: 'XWAR',
            currency: 'PLN',
            value: '200',
            value_default_ccy: '200',
            pnl_pct: '-0.25',
          },
        ],
      },
    ],
    metals: null,
    real_estate: null,
    snapshots: {},
  }
}

function renderManager(wallets: WalletManagerNode[] = [walletNode()]) {
  return render(<WalletManagerPage wallets={wallets} fxRates={fxRates} />)
}

function openBrokerageActionsMenu() {
  const trigger = screen.getByRole('button', { name: /Akcje dla Maklerskie ING Artur/i })
  fireEvent.keyDown(trigger, { key: 'Enter', code: 'Enter' })
}

describe('WalletManagerPage', () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    routerRefresh.mockClear()
    server.resetHandlers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })
  it('shows brokerage cash, positions and total with converted cash subaccounts', async () => {
    await nextUiUnitStory('Wallet manager shows brokerage cash and positions as separate financial values', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'wallet-manager', 'cash-subaccounts', 'next-ui'],
    })

    renderManager()

    fireEvent.click(screen.getByRole('button', { name: /Pokaż szczegóły Maklerskie ING Artur/i }))

    expect(screen.getByText('Gotówka')).toBeInTheDocument()
    expect(screen.getByText('Pozycje')).toBeInTheDocument()
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.getAllByText(/1200,00\s*PLN/).length).toBeGreaterThan(0)

    expect(screen.getByText('Maklerskie ING Artur · USD')).toBeInTheDocument()
    expect(screen.getByText(/25,00\s*USD/)).toBeInTheDocument()
    expect(screen.getByText(/≈\s*100,00\s*PLN/)).toBeInTheDocument()
    expect(screen.getByText('PKO')).toBeInTheDocument()
    expect(screen.getByText('+50.0%')).toBeInTheDocument()
  })

  it('converts CHF brokerage cash subaccounts to the view currency', async () => {
    await nextUiUnitStory('Wallet manager converts CHF cash subaccounts to the selected view currency', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'wallet-manager', 'fx', 'money', 'next-ui'],
    })

    const node = walletNode()
    node.brokerage_accounts![0]!.cash_accounts!.push({
      deposit_account_id: 'cash-chf',
      name: 'Maklerskie ING Artur · CHF',
      ccy: 'CHF',
      available: '10',
    })

    renderManager([node])

    fireEvent.click(screen.getByRole('button', { name: /Pokaż szczegóły Maklerskie ING Artur/i }))

    expect(screen.getByText('Maklerskie ING Artur · CHF')).toBeInTheDocument()
    expect(screen.getByText(/10,00\s*CHF/)).toBeInTheDocument()
    // 10 CHF * 4.6 (CHF/PLN) = 46,00 PLN — previously left unconverted.
    expect(screen.getByText(/≈\s*46,00\s*PLN/)).toBeInTheDocument()
  })

  it('adds a brokerage currency subaccount from wallet manager', async () => {
    await nextUiUnitStory('Wallet manager submits brokerage currency subaccounts through the local API route', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'wallet-manager', 'api-contract', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(
      http.post('*/api/wallet/brokerage/cash-links/ensure', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ ok: true })
      }),
    )

    renderManager()

    fireEvent.click(screen.getByRole('button', { name: /Pokaż szczegóły Maklerskie ING Artur/i }))
    expect(screen.queryByRole('menuitem', { name: /Subkonto walutowe/i })).not.toBeInTheDocument()

    openBrokerageActionsMenu()
    fireEvent.click(await screen.findByRole('menuitem', { name: /Subkonto walutowe/i }))
    fireEvent.change(screen.getByLabelText(/Numer \/ identyfikator/i), {
      target: { value: 'BOSSA-IKE-USD' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Podepnij/i }))

    await waitFor(() => expect(requests).toHaveLength(1))
    await expect(requests[0]?.json()).resolves.toEqual({
      brokerage_account_id: '11111111-1111-4111-8111-111111111111',
      cash_accounts: [
        {
          currency: 'USD',
          account_number: 'BOSSA-IKE-USD',
          name: 'Maklerskie ING Artur · USD',
        },
      ],
    })
    expect(routerRefresh).toHaveBeenCalled()
  })

  it('exposes brokerage event navigation from the account actions menu', async () => {
    await nextUiUnitStory('Wallet manager exposes brokerage event navigation from account actions menu', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'wallet-manager', 'navigation', 'next-ui'],
    })

    renderManager()

    fireEvent.click(screen.getByRole('button', { name: /Pokaż szczegóły Maklerskie ING Artur/i }))
    expect(screen.queryByRole('menuitem', { name: /Dodaj event/i })).not.toBeInTheDocument()

    openBrokerageActionsMenu()
    const addEvent = await screen.findByRole('menuitem', { name: /Dodaj event/i })

    expect(addEvent).toHaveAttribute(
      'href',
      '/wallet/brokerage/events?account=11111111-1111-4111-8111-111111111111',
    )
  })

  it('deletes brokerage account through wallet manager after confirmation', async () => {
    await nextUiUnitStory('Wallet manager deletes brokerage accounts through an ownership-checked API route', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'wallet-manager', 'ownership', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(
      http.delete('*/api/wallet/brokerage/accounts/11111111-1111-4111-8111-111111111111', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ ok: true })
      }),
    )

    renderManager()

    fireEvent.click(screen.getByRole('button', { name: /Pokaż szczegóły Maklerskie ING Artur/i }))
    expect(screen.queryByRole('menuitem', { name: /Usuń rachunek/i })).not.toBeInTheDocument()

    openBrokerageActionsMenu()
    fireEvent.click(await screen.findByRole('menuitem', { name: /Usuń rachunek/i }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Maklerskie ING Artur/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: /Usuń/i }))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(routerRefresh).toHaveBeenCalled()
  })
})
