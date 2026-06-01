import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from 'msw'
import { setupServer } from 'msw/node'

import { sortRows, TransactionsPage } from '@/features/wallet/components/TransactionsPage'
import type { SortDir, SortField, TxRow } from '@/features/wallet/components/TransactionsPage'
import { nextUiUnitStory } from '../allure'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

function makeRow(overrides: Partial<TxRow> & { id: string }): TxRow {
  return {
    dateFmt: '01.01.2024, 12:00',
    dateRaw: '2024-01-01T12:00:00',
    description: 'Test',
    accountName: 'Konto',
    accountId: 'acc-1',
    category: null,
    status: null,
    amount: '100',
    balanceBefore: '1000',
    balanceAfter: '1100',
    ccy: 'PLN',
    ...overrides,
  }
}

function pageWithRows(items: { id: string; date: string; accountName: string; category: string | null; status: string | null }[]) {
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
      total: items.length,
      page: 1,
      size: 40,
      sum_by_ccy: { PLN: 100 * items.length },
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )
}

// ── Pure sort logic ─────────────────────────────────────────────────────────

describe('sortRows – pure function', () => {
  const rows: TxRow[] = [
    makeRow({ id: '1', dateRaw: '2024-03-01T00:00:00', accountName: 'Żabka', category: 'FOOD', status: 'EXPENSE' }),
    makeRow({ id: '2', dateRaw: '2024-01-15T00:00:00', accountName: 'Alior', category: 'FUEL', status: 'INCOME' }),
    makeRow({ id: '3', dateRaw: '2024-06-10T00:00:00', accountName: 'mBank', category: null, status: null }),
  ]

  // FOOD → 'Żywność', FUEL → 'Paliwo', null → ''
  // STATUS: EXPENSE → 'Wydatek', INCOME → 'Przychód', null → ''
  const cases: Array<{ field: SortField; dir: SortDir; expectedIds: string[] }> = [
    { field: 'date',     dir: 'asc',  expectedIds: ['2', '1', '3'] },
    { field: 'date',     dir: 'desc', expectedIds: ['3', '1', '2'] },
    { field: 'account',  dir: 'asc',  expectedIds: ['2', '3', '1'] },
    { field: 'account',  dir: 'desc', expectedIds: ['1', '3', '2'] },
    { field: 'category', dir: 'asc',  expectedIds: ['3', '2', '1'] }, // '' < 'Paliwo' < 'Żywność'
    { field: 'category', dir: 'desc', expectedIds: ['1', '2', '3'] },
    { field: 'status',   dir: 'asc',  expectedIds: ['3', '2', '1'] }, // '' < 'Przychód' < 'Wydatek'
    { field: 'status',   dir: 'desc', expectedIds: ['1', '2', '3'] },
  ]

  for (const { field, dir, expectedIds } of cases) {
    it(`sorts by "${field}" ${dir}`, async () => {
      await nextUiUnitStory(`Wallet transactions sortRows sorts by ${field} ${dir}`, {
        severity: 'normal',
        tags: ['wallet', 'transactions', 'sorting', 'next-ui'],
      })

      const result = sortRows(rows, field, dir)
      expect(result.map((r) => r.id)).toEqual(expectedIds)
    })
  }

  it('does not mutate the source array', async () => {
    await nextUiUnitStory('Wallet transactions sortRows does not mutate the source array', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui'],
    })

    const original = [...rows]
    sortRows(rows, 'date', 'asc')
    expect(rows.map((r) => r.id)).toEqual(original.map((r) => r.id))
  })
})

// ── Component: header click behavior ────────────────────────────────────────

const server = setupServer()

describe('TransactionsPage – sort header clicks', () => {
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

  it('first click on a column header sorts rows ascending', async () => {
    await nextUiUnitStory('Wallet transactions first click on a column header sorts rows ascending', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () =>
        pageWithRows([
          { id: 'b', date: '2024-03-01T00:00:00', accountName: 'mBank', category: null, status: null },
          { id: 'a', date: '2024-01-01T00:00:00', accountName: 'Alior', category: null, status: null },
        ]),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Opis a'))

    fireEvent.click(screen.getByRole('button', { name: /Sortuj po: Data/i }))

    const cells = screen.getAllByText(/^Opis /)
    expect(cells.at(0)?.textContent).toBe('Opis a')
    expect(cells.at(1)?.textContent).toBe('Opis b')
  })

  it('second click on the same header reverses the sort direction to descending', async () => {
    await nextUiUnitStory('Wallet transactions second click on a column header reverses the sort direction', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () =>
        pageWithRows([
          { id: 'b', date: '2024-03-01T00:00:00', accountName: 'mBank', category: null, status: null },
          { id: 'a', date: '2024-01-01T00:00:00', accountName: 'Alior', category: null, status: null },
        ]),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Opis a'))

    const btn = screen.getByRole('button', { name: /Sortuj po: Data/i })
    fireEvent.click(btn)
    fireEvent.click(btn)

    const cells = screen.getAllByText(/^Opis /)
    expect(cells.at(0)?.textContent).toBe('Opis b')
    expect(cells.at(1)?.textContent).toBe('Opis a')
  })

  it('clicking a different header resets the sort direction to ascending', async () => {
    await nextUiUnitStory('Wallet transactions switching sort column resets direction to ascending', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () =>
        pageWithRows([
          { id: 'b', date: '2024-03-01T00:00:00', accountName: 'mBank', category: null, status: null },
          { id: 'a', date: '2024-01-01T00:00:00', accountName: 'Alior', category: null, status: null },
        ]),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Opis a'))

    const dateBtn = screen.getByRole('button', { name: /Sortuj po: Data/i })
    fireEvent.click(dateBtn)
    fireEvent.click(dateBtn)

    fireEvent.click(screen.getByRole('button', { name: /Sortuj po: Konto/i }))

    const cells = screen.getAllByText(/^Opis /)
    expect(cells.at(0)?.textContent).toBe('Opis a')
    expect(cells.at(1)?.textContent).toBe('Opis b')
  })

  it('sorts by account name alphabetically', async () => {
    await nextUiUnitStory('Wallet transactions sorting by account column orders rows alphabetically', {
      severity: 'normal',
      tags: ['wallet', 'transactions', 'sorting', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/transactions', () =>
        pageWithRows([
          { id: 'z', date: '2024-01-01T00:00:00', accountName: 'Żabka', category: null, status: null },
          { id: 'a', date: '2024-01-02T00:00:00', accountName: 'Alior', category: null, status: null },
          { id: 'm', date: '2024-01-03T00:00:00', accountName: 'mBank', category: null, status: null },
        ]),
      ),
    )

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)
    await waitFor(() => screen.getByText('Opis a'))

    fireEvent.click(screen.getByRole('button', { name: /Sortuj po: Konto/i }))

    const cells = screen.getAllByText(/^Opis /)
    expect(cells.at(0)?.textContent).toBe('Opis a')
    expect(cells.at(1)?.textContent).toBe('Opis m')
    expect(cells.at(2)?.textContent).toBe('Opis z')
  })
})
