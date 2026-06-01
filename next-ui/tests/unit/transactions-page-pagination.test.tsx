import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import { TransactionsPage } from '@/features/wallet/components/TransactionsPage'
import { nextUiUnitStory } from '../allure'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

function makePage(page: number, totalPages: number, size = 40) {
  const total = totalPages * size
  return {
    items: [
      {
        id: `item-p${page}`,
        amount: 10,
        description: `Transakcja strona ${page}`,
        balance_before: 100,
        balance_after: 110,
        date_transaction: '2024-01-01T00:00:00',
        account_id: 'acc-1',
        account_name: 'Konto',
        category: null,
        status: null,
        ccy: 'PLN',
      },
    ],
    total,
    page,
    size,
    sum_by_ccy: { PLN: 10 },
  }
}

const server = setupServer()

function transactionPageHandler(totalPages: number, requestedUrls?: string[]) {
  return http.get('*/api/wallet/transactions', ({ request }) => {
    requestedUrls?.push(request.url)
    const pageParam = new URL(request.url).searchParams.get('page')
    return HttpResponse.json(makePage(Number(pageParam ?? 1), totalPages))
  })
}

describe('TransactionsPage – pagination', () => {
  beforeAll(() => {
    server.listen({ onUnhandledRequest: 'error' })
  })

  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })

  afterAll(() => {
    server.close()
  })

  it('renders a page number input and a last-page button', async () => {
    await nextUiUnitStory('Wallet transactions pagination shows a page number input and last-page button', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'pagination', 'next-ui'],
    })

    server.use(transactionPageHandler(5))
    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)

    await waitFor(() => screen.getByText(/Transakcja strona 1/))

    expect(screen.getByRole('textbox', { name: /Numer strony/i })).toBeDefined()
    expect(screen.getByRole('button', { name: /Ostatnia strona/i })).toBeDefined()
  })

  it('page number input reflects the current page', async () => {
    await nextUiUnitStory('Wallet transactions page number input shows the current page', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'pagination', 'next-ui'],
    })

    server.use(transactionPageHandler(5))
    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)

    await waitFor(() => screen.getByText(/Transakcja strona 1/))

    const input = screen.getByRole('textbox', { name: /Numer strony/i }) as HTMLInputElement
    expect(input.value).toBe('1')
  })

  it('typing a page number and pressing Enter navigates to that page', async () => {
    await nextUiUnitStory('Wallet transactions typing a page number and Enter navigates to that page', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'pagination', 'next-ui'],
    })

    const requestedUrls: string[] = []
    server.use(transactionPageHandler(5, requestedUrls))

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText(/Transakcja strona 1/))

    const input = screen.getByRole('textbox', { name: /Numer strony/i })
    fireEvent.change(input, { target: { value: '3' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(requestedUrls.some((url) => url.includes('page=3'))).toBe(true)
    })
  })

  it('blurring the page input navigates to the entered page', async () => {
    await nextUiUnitStory('Wallet transactions blur on the page input navigates to the entered page', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'pagination', 'next-ui'],
    })

    const requestedUrls: string[] = []
    server.use(transactionPageHandler(5, requestedUrls))

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText(/Transakcja strona 1/))

    const input = screen.getByRole('textbox', { name: /Numer strony/i })
    fireEvent.change(input, { target: { value: '4' } })
    fireEvent.blur(input)

    await waitFor(() => {
      expect(requestedUrls.some((url) => url.includes('page=4'))).toBe(true)
    })
  })

  it('entering an out-of-range page number clamps to the last page', async () => {
    await nextUiUnitStory('Wallet transactions out-of-range page number is clamped to the allowed range', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'pagination', 'next-ui'],
    })

    const requestedUrls: string[] = []
    server.use(transactionPageHandler(3, requestedUrls))

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText(/Transakcja strona 1/))

    const input = screen.getByRole('textbox', { name: /Numer strony/i })
    fireEvent.change(input, { target: { value: '999' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(requestedUrls.some((url) => url.includes('page=3'))).toBe(true)
    })
  })

  it('last-page button navigates to the last page', async () => {
    await nextUiUnitStory('Wallet transactions last-page button navigates to the last page', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'pagination', 'next-ui'],
    })

    const requestedUrls: string[] = []
    server.use(transactionPageHandler(7, requestedUrls))

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText(/Transakcja strona 1/))

    fireEvent.click(screen.getByRole('button', { name: /Ostatnia strona/i }))

    await waitFor(() => {
      expect(requestedUrls.some((url) => url.includes('page=7'))).toBe(true)
    })
  })

  it('last-page button is disabled when already on the last page', async () => {
    await nextUiUnitStory('Wallet transactions last-page button is disabled when on the last page', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'pagination', 'next-ui'],
    })

    const requestedUrls: string[] = []
    server.use(transactionPageHandler(3, requestedUrls))

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText(/Transakcja strona 1/))

    fireEvent.click(screen.getByRole('button', { name: /Ostatnia strona/i }))
    await waitFor(() => {
      expect(requestedUrls.some((url) => url.includes('page=3'))).toBe(true)
    })

    await waitFor(() => screen.getByText(/Transakcja strona 3/))

    const lastBtn = screen.getByRole('button', { name: /Ostatnia strona/i }) as HTMLButtonElement
    expect(lastBtn.disabled).toBe(true)
  })
})
