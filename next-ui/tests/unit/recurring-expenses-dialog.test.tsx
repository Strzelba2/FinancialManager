import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'

import {
  RecurringExpensesDialog,
  type ExpenseWalletOpt,
} from '@/features/wallet/components/RecurringExpensesDialog'
import type { RecurringExpenseOut } from '@/lib/types/wallet'
import { server } from '../msw-server'
import { nextUiUnitStory } from '../allure'

const routerRefresh = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: routerRefresh }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const wallet: ExpenseWalletOpt = {
  id: 'wallet-1',
  name: 'Domowy',
  accounts: [
    { id: 'account-current', name: 'Konto osobiste', currency: 'PLN', accountType: 'CURRENT' },
    { id: 'account-savings', name: 'Oszczędności', currency: 'EUR', accountType: 'SAVINGS' },
  ],
}

const existingExpense: RecurringExpenseOut = {
  id: 'expense-1',
  wallet_id: 'wallet-1',
  name: 'Netflix',
  category: 'Streaming',
  amount: '49.99',
  currency: 'PLN',
  due_day: 12,
  account: 'Konto osobiste',
  note: null,
}

async function chooseOption(triggerIndex: number, name: RegExp | string) {
  fireEvent.click(screen.getAllByRole('combobox')[triggerIndex]!)
  fireEvent.click(await screen.findByRole('option', { name }))
}

function renderDialog(wallets: ExpenseWalletOpt[] = [wallet], expenses: RecurringExpenseOut[] = [existingExpense]) {
  return render(
    <RecurringExpensesDialog
      open
      onOpenChange={vi.fn()}
      initialExpenses={expenses}
      wallets={wallets}
      viewCurrency="PLN"
    />,
  )
}

describe('RecurringExpensesDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routerRefresh.mockClear()
    server.resetHandlers()
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('creates a recurring expense from category and deposit-account selects without brokerage accounts', async () => {
    await nextUiUnitStory('Wallet recurring dialog limits account selection to deposit accounts', {
      severity: 'critical',
      tags: ['wallet', 'recurring-expenses', 'accounts', 'financial-data', 'next-ui'],
    })

    const requests: Request[] = []
    server.use(
      http.post('*/api/wallet/recurring-expenses', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ success: true })
      }),
    )

    renderDialog([
      {
        ...wallet,
        accounts: [
          ...wallet.accounts,
          { id: 'account-brokerage', name: 'BOSSA cash', currency: 'PLN', accountType: 'BROKERAGE' },
        ],
      },
    ])

    fireEvent.click(screen.getByRole('button', { name: /Dodaj/i }))
    await screen.findByText('Dodaj stały wydatek')

    fireEvent.change(screen.getByPlaceholderText('np. Czynsz'), { target: { value: 'Internet' } })
    await chooseOption(0, 'Rachunki')

    fireEvent.click(screen.getAllByRole('combobox')[1]!)
    expect(screen.getByRole('option', { name: 'Konto osobiste · PLN' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Oszczędności · EUR' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /BOSSA cash/u })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('option', { name: 'Konto osobiste · PLN' }))

    fireEvent.change(screen.getByPlaceholderText('np. 1800'), { target: { value: '89,90' } })
    fireEvent.change(screen.getByPlaceholderText('np. 10'), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    await expect(requests[0]?.json()).resolves.toEqual({
      wallet_id: 'wallet-1',
      name: 'Internet',
      category: 'Rachunki',
      amount: '89.90',
      currency: 'PLN',
      due_day: 10,
      account: 'Konto osobiste',
    })
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Wydatek dodany')
      expect(routerRefresh).toHaveBeenCalled()
    })
  })

  it('keeps existing recurring categories available in the category select', async () => {
    await nextUiUnitStory('Wallet recurring dialog preserves existing custom category labels', {
      severity: 'normal',
      tags: ['wallet', 'recurring-expenses', 'categories', 'next-ui'],
    })

    renderDialog()

    fireEvent.click(screen.getByRole('button', { name: /Dodaj/i }))
    await screen.findByText('Dodaj stały wydatek')
    fireEvent.click(screen.getAllByRole('combobox')[0]!)

    expect(await screen.findByRole('option', { name: 'Streaming' })).toBeInTheDocument()
  })
})
