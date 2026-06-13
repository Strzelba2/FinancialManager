import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
