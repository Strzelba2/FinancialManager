import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import { TransactionsPage } from '@/features/wallet/components/TransactionsPage'
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

function makeRow(
  id: string,
  category: string | null = null,
  status: string | null = null,
) {
  return {
    id,
    amount: -25,
    description: `Transakcja ${id}`,
    balance_before: 100,
    balance_after: 75,
    date_transaction: '2026-06-01T10:00:00',
    account_id: 'acc-1',
    account_name: 'Konto testowe',
    category,
    status,
    ccy: 'PLN',
  }
}

function pageResponse(items: ReturnType<typeof makeRow>[]) {
  return HttpResponse.json({
    items,
    total: items.length,
    page: 1,
    size: 40,
    sum_by_ccy: { PLN: items.reduce((s, r) => s + r.amount, 0) },
  })
}

describe('TransactionsPage – delete', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
  })
  it('shows inline confirmation when the delete icon is clicked', async () => {
    await nextUiUnitStory('Wallet transactions delete icon click shows an inline confirmation', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'delete', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () => pageResponse([makeRow('tx-1')])),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Transakcja tx-1'))

    const deleteBtn = document.querySelector<HTMLButtonElement>(
      'tbody tr:first-child td:last-child button',
    )!
    fireEvent.click(deleteBtn)

    await screen.findByText('Czy na pewno usunąć?')
  })

  it('clicking cancel hides the confirmation without sending a request', async () => {
    await nextUiUnitStory('Wallet transactions cancel hides the inline delete confirmation', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'delete', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () => pageResponse([makeRow('tx-1')])),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Transakcja tx-1'))

    const deleteBtn = document.querySelector<HTMLButtonElement>(
      'tbody tr:first-child td:last-child button',
    )!
    fireEvent.click(deleteBtn)
    await screen.findByText('Czy na pewno usunąć?')

    // The ✕ cancel button appears next to the confirm button
    const cancelBtn = document.querySelector<HTMLButtonElement>(
      'tbody tr:first-child td:last-child button:last-child',
    )!
    fireEvent.click(cancelBtn)

    await waitFor(() => {
      expect(screen.queryByText('Czy na pewno usunąć?')).not.toBeInTheDocument()
    })
  })

  it('shows success toast and reloads after confirmed delete', async () => {
    await nextUiUnitStory('Wallet transactions confirmed delete shows success toast and reloads', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'delete', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () => pageResponse([makeRow('tx-1')])),
      http.delete('*/api/wallet/transactions/*', () =>
        HttpResponse.json({ success: true }),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Transakcja tx-1'))

    fireEvent.click(
      document.querySelector<HTMLButtonElement>('tbody tr:first-child td:last-child button')!,
    )
    await screen.findByText('Czy na pewno usunąć?')

    fireEvent.click(
      document.querySelector<HTMLButtonElement>('tbody tr:first-child td:last-child button:first-child')!,
    )

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Transakcja usunięta')
    })
  })

  it('shows error toast when delete request fails', async () => {
    await nextUiUnitStory('Wallet transactions failed delete shows error toast', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'delete', 'error-state', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () => pageResponse([makeRow('tx-1')])),
      http.delete('*/api/wallet/transactions/*', () =>
        HttpResponse.json({ error: 'Nie udało się usunąć transakcji' }, { status: 400 }),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Transakcja tx-1'))

    fireEvent.click(
      document.querySelector<HTMLButtonElement>('tbody tr:first-child td:last-child button')!,
    )
    await screen.findByText('Czy na pewno usunąć?')

    fireEvent.click(
      document.querySelector<HTMLButtonElement>('tbody tr:first-child td:last-child button:first-child')!,
    )

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled()
    })
  })
})

describe('TransactionsPage – loading states', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
  })
  it('shows empty state message when no transactions match the criteria', async () => {
    await nextUiUnitStory('Wallet transactions page shows empty state when no rows match the criteria', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'empty-state', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () =>
        HttpResponse.json({ items: [], total: 0, page: 1, size: 40, sum_by_ccy: {} }),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)

    await screen.findByText('Brak transakcji spełniających kryteria')
  })

  it('shows an inline error message when loading transactions fails', async () => {
    await nextUiUnitStory('Wallet transactions page shows inline error when loading fails', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'error-state', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () =>
        HttpResponse.json({ error: 'Nie udało się pobrać transakcji' }, { status: 500 }),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)

    await screen.findByText('Nie udało się pobrać transakcji')
  })
})

describe('TransactionsPage – inline edit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Radix UI Select calls scrollIntoView on the focused item; jsdom doesn't implement it.
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
  })
  it('clicking a category cell opens inline editor and saves on Zapisz', async () => {
    await nextUiUnitStory('Wallet transactions clicking a category cell opens the inline editor and saves', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'inline-edit', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () => pageResponse([makeRow('tx-1')])),
      http.patch('*/api/wallet/transactions', () =>
        HttpResponse.json({ updated: 1, failed: [] }),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Transakcja tx-1'))

    // Click the category span — td:nth-child(4) in the first body row
    const categoryCell = document.querySelector('tbody tr:first-child td:nth-child(4)')!
    fireEvent.click(within(categoryCell as HTMLElement).getByText('—'))

    // Dropdown is rendered with open=true; find the Żywność (FOOD) option
    const foodOption = await screen.findByRole('option', { name: 'Żywność' })
    fireEvent.click(foodOption)

    // Zapisz button becomes enabled once a cell is dirty
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Zapisz/i })).not.toBeDisabled()
    })
    fireEvent.click(screen.getByRole('button', { name: /Zapisz/i }))

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Zapisano'))
    })
  })

  it('shows an error toast when the save request fails', async () => {
    await nextUiUnitStory('Wallet transactions inline edit shows error toast when save fails', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'inline-edit', 'error-state', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () => pageResponse([makeRow('tx-1')])),
      http.patch('*/api/wallet/transactions', () =>
        HttpResponse.json({ error: 'Nie udało się zapisać zmian' }, { status: 422 }),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Transakcja tx-1'))

    const categoryCell = document.querySelector('tbody tr:first-child td:nth-child(4)')!
    fireEvent.click(within(categoryCell as HTMLElement).getByText('—'))

    const foodOption = await screen.findByRole('option', { name: 'Żywność' })
    fireEvent.click(foodOption)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Zapisz/i })).not.toBeDisabled()
    })
    fireEvent.click(screen.getByRole('button', { name: /Zapisz/i }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled()
    })
  })
})

describe('TransactionsPage – search and date filters', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
  })
  it('typing in the search box appends q param to the fetch URL', async () => {
    await nextUiUnitStory('Wallet transactions typing in the search box appends q param to the fetch URL', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'search', 'filters', 'next-ui'],
    })

    const captured: string[] = []
    server.use(
      http.get('*/api/wallet/transactions', ({ request }) => {
        captured.push(request.url)
        return pageResponse([])
      }),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await screen.findByText('Brak transakcji spełniających kryteria')

    fireEvent.change(screen.getByPlaceholderText('Szukaj…'), {
      target: { value: 'wynagrodzenie' },
    })

    await waitFor(() => {
      expect(captured.some((url) => url.includes('q=wynagrodzenie'))).toBe(true)
    })
  })

  it('clicking a date preset appends date_from and date_to to the fetch URL', async () => {
    await nextUiUnitStory('Wallet transactions clicking a date preset appends date_from and date_to to the URL', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'date-filter', 'filters', 'next-ui'],
    })

    const captured: string[] = []
    server.use(
      http.get('*/api/wallet/transactions', ({ request }) => {
        captured.push(request.url)
        return pageResponse([])
      }),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await screen.findByText('Brak transakcji spełniających kryteria')

    fireEvent.click(screen.getByRole('button', { name: '1M' }))

    await waitFor(() => {
      expect(captured.some((url) => url.includes('date_from=') && url.includes('date_to='))).toBe(true)
    })
  })
})
