import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import {
  TransactionsDialog,
  type TransactionAccountOpt,
} from '@/features/wallet/components/TransactionsDialog'
import { nextUiUnitStory } from '../allure'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

const ACCOUNT: TransactionAccountOpt = {
  id: 'account-1',
  name: 'Konto osobiste',
  walletName: 'Portfel',
  currency: 'PLN',
  available: '1000.00',
}

function fillManualForm() {
  fireEvent.change(screen.getByPlaceholderText(/-120\.50/), { target: { value: '100,00' } })
  fireEvent.change(screen.getByPlaceholderText(/5140\.30/), { target: { value: '1100,00' } })
  fireEvent.change(screen.getByPlaceholderText(/Biedronka/), { target: { value: 'Wynagrodzenie maj' } })
  fireEvent.click(screen.getByText(/Wybierz datę/i))
  fireEvent.click(screen.getByRole('button', { name: /Teraz/i }))
}

describe('TransactionsDialog – manual form', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
  })
  it('shows validation errors when required fields are empty on submit', async () => {
    await nextUiUnitStory('Wallet manual transaction form shows validation error when required fields are empty', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'manual', 'validation', 'next-ui'],
    })

    render(
      <TransactionsDialog
        open
        onOpenChange={vi.fn()}
        accounts={[ACCOUNT]}
        brokerageAccounts={[]}
      />,
    )

    // Submit without filling any field
    fireEvent.click(screen.getByRole('button', { name: /Dodaj transakcję/i }))

    await screen.findByText(/Podaj kwotę|Wybierz konto/i)
  })

  it('shows a success toast and closes the dialog on successful manual transaction', async () => {
    await nextUiUnitStory('Wallet manual transaction form shows success toast and closes the dialog', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'manual', 'success', 'next-ui'],
    })

    server.use(
      http.post('*/api/wallet/transactions', () =>
        HttpResponse.json({ success: true, summary: { created: 1 } }),
      ),
    )

    const onOpenChange = vi.fn()
    render(
      <TransactionsDialog
        open
        onOpenChange={onOpenChange}
        accounts={[ACCOUNT]}
        brokerageAccounts={[]}
      />,
    )

    fillManualForm()
    fireEvent.click(screen.getByRole('button', { name: /Dodaj transakcję/i }))

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Pomyślnie dodano transakcję')
    })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('shows an error message when the backend rejects the manual transaction', async () => {
    await nextUiUnitStory('Wallet manual transaction form shows error message when backend rejects the transaction', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'manual', 'error-state', 'next-ui'],
    })

    server.use(
      http.post('*/api/wallet/transactions', () =>
        HttpResponse.json(
          { error: 'Saldo po operacji w dniu … nie zgadza się' },
          { status: 422 },
        ),
      ),
    )

    const onOpenChange = vi.fn()
    render(
      <TransactionsDialog
        open
        onOpenChange={onOpenChange}
        accounts={[ACCOUNT]}
        brokerageAccounts={[]}
      />,
    )

    fillManualForm()
    fireEvent.click(screen.getByRole('button', { name: /Dodaj transakcję/i }))

    await screen.findByText(/Saldo po operacji/i)
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })
})

const SECOND_ACCOUNT: TransactionAccountOpt = {
  id: 'account-2',
  name: 'Konto oszczędnościowe',
  walletName: 'Portfel',
  currency: 'EUR',
  available: '500.00',
}

const LAST_ACCOUNT_KEY = 'transactions_last_manual_account'

function renderManual(accounts: TransactionAccountOpt[] = [ACCOUNT, SECOND_ACCOUNT]) {
  return render(
    <TransactionsDialog
      open
      onOpenChange={vi.fn()}
      accounts={accounts}
      brokerageAccounts={[]}
    />,
  )
}

function accountTrigger() {
  return screen.getAllByRole('combobox')[0]!
}

function selectSecondAccount() {
  fireEvent.click(accountTrigger())
  fireEvent.click(screen.getByRole('option', { name: /Konto oszczędnościowe/ }))
}

describe('TransactionsDialog – manual form remembers the last account', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('preselects the remembered account when it still exists', async () => {
    await nextUiUnitStory('Wallet manual transaction form preselects the remembered account', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'manual', 'usability', 'next-ui'],
    })
    window.localStorage.setItem(LAST_ACCOUNT_KEY, 'account-2')

    renderManual()

    expect(accountTrigger()).toHaveTextContent('Konto oszczędnościowe (EUR)')
  })

  it('falls back to the first account when the remembered account no longer exists', async () => {
    await nextUiUnitStory('Wallet manual transaction form falls back to the first account', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'manual', 'usability', 'next-ui'],
    })
    window.localStorage.setItem(LAST_ACCOUNT_KEY, 'deleted-account')

    renderManual()

    expect(accountTrigger()).toHaveTextContent('Konto osobiste (PLN)')
  })

  it('remembers the account after a successful add and preselects it on the next open', async () => {
    await nextUiUnitStory('Wallet manual transaction form remembers the account after a successful add', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'manual', 'usability', 'next-ui'],
    })
    const requests: unknown[] = []
    server.use(
      http.post('*/api/wallet/transactions', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ success: true, summary: { created: 1 } })
      }),
    )

    const { unmount } = renderManual()
    selectSecondAccount()
    fillManualForm()
    fireEvent.click(screen.getByRole('button', { name: /Dodaj transakcję/i }))

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Pomyślnie dodano transakcję'))
    expect(requests).toEqual([expect.objectContaining({ account_id: 'account-2' })])
    expect(window.localStorage.getItem(LAST_ACCOUNT_KEY)).toBe('account-2')

    unmount()
    renderManual()

    expect(accountTrigger()).toHaveTextContent('Konto oszczędnościowe (EUR)')
  })

  it('does not remember the account when the backend rejects the transaction', async () => {
    await nextUiUnitStory('Wallet manual transaction form keeps the remembered account on failure', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'manual', 'error-state', 'next-ui'],
    })
    server.use(
      http.post('*/api/wallet/transactions', () =>
        HttpResponse.json({ error: 'This insert would make the account balance negative.' }, { status: 422 }),
      ),
    )

    renderManual()
    selectSecondAccount()
    fillManualForm()
    fireEvent.click(screen.getByRole('button', { name: /Dodaj transakcję/i }))

    await screen.findByText(/would make the account balance negative/i)
    expect(window.localStorage.getItem(LAST_ACCOUNT_KEY)).toBeNull()
  })

  it('uses the first account when browser storage is blocked', async () => {
    await nextUiUnitStory('Wallet manual transaction form works without browser storage', {
      severity: 'minor',
      tags: ['wallet', 'transactions', 'manual', 'resilience', 'next-ui'],
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage blocked')
    })

    renderManual()

    expect(accountTrigger()).toHaveTextContent('Konto osobiste (PLN)')
  })
})
