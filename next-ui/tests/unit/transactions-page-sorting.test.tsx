import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from 'msw'
import { server } from '../msw-server'

import { TransactionsPage } from '@/features/wallet/components/TransactionsPage'
import { nextUiUnitStory } from '../allure'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

type RowInput = {
  id: string
  date: string
  accountName: string
  category: string | null
  status: string | null
}

function pageWithRows(items: RowInput[], page = 1, total = items.length) {
  return new Response(
    JSON.stringify({
      items: items.map((it) => ({
        id: it.id,
        amount: 100,
        description: `Opis ${it.id}`,
        balance_before: 1000,
        balance_after: 1100,
        date_transaction: it.date,
        account_id: 'acc-1',
        account_name: it.accountName,
        category: it.category,
        status: it.status,
        ccy: 'PLN',
      })),
      total,
      page,
      size: 40,
      sum_by_ccy: { PLN: 100 * items.length },
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )
}

const unsortedRows: RowInput[] = [
  { id: 'b', date: '2024-03-01T00:00:00', accountName: 'mBank', category: null, status: null },
  { id: 'a', date: '2024-01-01T00:00:00', accountName: 'Alior', category: null, status: null },
]

const dateAscRows: RowInput[] = [
  { id: 'a', date: '2024-01-01T00:00:00', accountName: 'Alior', category: null, status: null },
  { id: 'b', date: '2024-03-01T00:00:00', accountName: 'mBank', category: null, status: null },
]

const dateDescRows: RowInput[] = [
  { id: 'b', date: '2024-03-01T00:00:00', accountName: 'mBank', category: null, status: null },
  { id: 'a', date: '2024-01-01T00:00:00', accountName: 'Alior', category: null, status: null },
]

describe('TransactionsPage – server-side sort header clicks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })
  it('sort headers are visible when the table has rows', async () => {
    await nextUiUnitStory('Wallet transactions sortable column headers are present when rows exist', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () =>
        pageWithRows([
          { id: 'x', date: '2024-01-01T00:00:00', accountName: 'Alior', category: null, status: null },
        ]),
      ),
    )
    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)

    await waitFor(() => screen.getByText('Opis x'))

    expect(screen.getByRole('button', { name: /Sortuj po: Data/i })).toBeDefined()
    expect(screen.getByRole('button', { name: /Sortuj po: Konto/i })).toBeDefined()
    expect(screen.getByRole('button', { name: /Sortuj po: Kategoria/i })).toBeDefined()
    expect(screen.getByRole('button', { name: /Sortuj po: Status/i })).toBeDefined()
  })

  it('first click on a column header requests ascending server-side sorting', async () => {
    await nextUiUnitStory('Wallet transactions first sort click requests ascending server-side order', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui', 'api-contract'],
    })

    const requests: URL[] = []
    server.use(
      http.get('*/api/wallet/transactions', ({ request }) => {
        const url = new URL(request.url)
        requests.push(url)
        if (url.searchParams.get('sort_by') === 'date' && url.searchParams.get('sort_dir') === 'asc') {
          return pageWithRows(dateAscRows)
        }
        return pageWithRows(unsortedRows)
      }),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Opis b'))

    fireEvent.click(screen.getByRole('button', { name: /Sortuj po: Data/i }))

    await waitFor(() => {
      expect(requests.at(-1)?.searchParams.get('sort_by')).toBe('date')
      expect(requests.at(-1)?.searchParams.get('sort_dir')).toBe('asc')
    })

    const cells = screen.getAllByText(/^Opis /)
    expect(cells.at(0)?.textContent).toBe('Opis a')
    expect(cells.at(1)?.textContent).toBe('Opis b')
  })

  it('second click on the same header requests descending server-side sorting', async () => {
    await nextUiUnitStory('Wallet transactions second sort click requests descending server-side order', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui', 'api-contract'],
    })

    const requests: URL[] = []
    server.use(
      http.get('*/api/wallet/transactions', ({ request }) => {
        const url = new URL(request.url)
        requests.push(url)
        if (url.searchParams.get('sort_by') === 'date' && url.searchParams.get('sort_dir') === 'asc') {
          return pageWithRows(dateAscRows)
        }
        if (url.searchParams.get('sort_by') === 'date' && url.searchParams.get('sort_dir') === 'desc') {
          return pageWithRows(dateDescRows)
        }
        return pageWithRows(unsortedRows)
      }),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Opis b'))

    const btn = screen.getByRole('button', { name: /Sortuj po: Data/i })
    fireEvent.click(btn)
    await waitFor(() => expect(requests.at(-1)?.searchParams.get('sort_dir')).toBe('asc'))
    fireEvent.click(btn)

    await waitFor(() => {
      expect(requests.at(-1)?.searchParams.get('sort_by')).toBe('date')
      expect(requests.at(-1)?.searchParams.get('sort_dir')).toBe('desc')
    })

    const cells = screen.getAllByText(/^Opis /)
    expect(cells.at(0)?.textContent).toBe('Opis b')
    expect(cells.at(1)?.textContent).toBe('Opis a')
  })

  it('clicking a different header resets the requested sort direction to ascending', async () => {
    await nextUiUnitStory('Wallet transactions switching sort column requests ascending direction', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui', 'api-contract'],
    })

    const requests: URL[] = []
    server.use(
      http.get('*/api/wallet/transactions', ({ request }) => {
        const url = new URL(request.url)
        requests.push(url)
        return pageWithRows(unsortedRows)
      }),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Opis b'))

    const dateBtn = screen.getByRole('button', { name: /Sortuj po: Data/i })
    fireEvent.click(dateBtn)
    await waitFor(() => expect(requests.at(-1)?.searchParams.get('sort_dir')).toBe('asc'))
    fireEvent.click(dateBtn)
    await waitFor(() => expect(requests.at(-1)?.searchParams.get('sort_dir')).toBe('desc'))

    fireEvent.click(screen.getByRole('button', { name: /Sortuj po: Konto/i }))

    await waitFor(() => {
      expect(requests.at(-1)?.searchParams.get('sort_by')).toBe('account')
      expect(requests.at(-1)?.searchParams.get('sort_dir')).toBe('asc')
    })
  })

  it('server-side sorting resets pagination to the first page', async () => {
    await nextUiUnitStory('Wallet transactions sort change resets pagination before requesting rows', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'sorting', 'pagination', 'next-ui', 'api-contract'],
    })

    const requests: URL[] = []
    server.use(
      http.get('*/api/wallet/transactions', ({ request }) => {
        const url = new URL(request.url)
        requests.push(url)
        return pageWithRows(unsortedRows, Number(url.searchParams.get('page') ?? '1'), 120)
      }),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Opis b'))

    fireEvent.change(screen.getByLabelText(/Numer strony/i), { target: { value: '3' } })
    fireEvent.blur(screen.getByLabelText(/Numer strony/i))
    await waitFor(() => expect(requests.at(-1)?.searchParams.get('page')).toBe('3'))

    fireEvent.click(screen.getByRole('button', { name: /Sortuj po: Data/i }))

    await waitFor(() => {
      expect(requests.at(-1)?.searchParams.get('page')).toBe('1')
      expect(requests.at(-1)?.searchParams.get('sort_by')).toBe('date')
      expect(requests.at(-1)?.searchParams.get('sort_dir')).toBe('asc')
    })
  })
})
