import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { toast } from 'sonner'

import { TransactionsDialog } from '@/features/wallet/components/TransactionsDialog'
import { nextUiUnitStory } from '../allure'

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: vi.fn(),
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

function parsedRows(count: number) {
  return Array.from({ length: count }, (_, index) => {
    const rowNumber = index + 1
    const amount = rowNumber === 39 ? '-143630.00' : rowNumber === 45 ? '-45.00' : `-${rowNumber}.00`
    const date = new Date(Date.UTC(2026, 2, rowNumber, 10, 0, 0))

    return {
      date: date.toISOString(),
      amount,
      description: `Kontrahent ${rowNumber} Transakcja testowa ${rowNumber}`,
      amount_after: `${1000 - rowNumber}.00`,
    }
  })
}

const server = setupServer()

describe('TransactionsDialog import preview', () => {
  beforeAll(() => {
    server.listen({ onUnhandledRequest: 'error' })
  })

  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
  })

  afterAll(() => {
    server.close()
  })

  it('renders every parsed transaction row in the Next UI import preview', async () => {
    await nextUiUnitStory('Wallet transaction import preview renders more than forty parsed rows', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'next-ui'],
    })

    const rows = parsedRows(45)
    server.use(
      http.get('*/api/wallet/import/parsers', () => (
        HttpResponse.json([
          {
            name: 'IngBank CSV',
            kind: 'CSV',
            accept: '.csv',
            upload_label: 'Wybierz plik CSV',
            supports_brokerage_events: false,
          },
        ])
      )),
      http.post('*/api/wallet/import/parse', () => HttpResponse.json({ rows })),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={vi.fn()}
        accounts={[
          {
            id: 'account-1',
            name: 'Konto osobiste',
            walletName: 'Portfel',
            currency: 'PLN',
            available: '1000.00',
          },
        ]}
        brokerageAccounts={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Ten format obsługuje import transakcji gotówkowych.')

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput!, {
      target: {
        files: [new File(['Data księgowania;Kwota transakcji (waluta rachunku)\n'], 'transactions_ing.csv', { type: 'text/csv' })],
      },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))

    const preview = await screen.findByText('Podgląd transakcji')
    const table = preview.closest('div')?.parentElement?.querySelector('table')
    expect(table).not.toBeNull()

    await waitFor(() => {
      expect(within(table!).getAllByRole('row')).toHaveLength(46)
    })
    expect(screen.getByText('45 wierszy')).toBeInTheDocument()
    expect(screen.getByText('-143630.00')).toBeInTheDocument()
    expect(screen.getByText('Kontrahent 45 Transakcja testowa 45')).toBeInTheDocument()
    expect(screen.getByText('-45.00')).toBeInTheDocument()
  })

  it('keeps the selected file when bank format changes before parsing', async () => {
    await nextUiUnitStory('Wallet transaction import keeps selected file after parser change', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'next-ui'],
    })

    const rows = parsedRows(1)
    const parseRequests: FormData[] = []
    server.use(
      http.get('*/api/wallet/import/parsers', () => (
        HttpResponse.json([
          {
            name: 'mBank CSV',
            kind: 'CSV',
            accept: '.csv',
            upload_label: 'Wybierz plik CSV',
            supports_brokerage_events: false,
          },
          {
            name: 'IngBank CSV',
            kind: 'CSV',
            accept: '.csv',
            upload_label: 'Wybierz plik CSV',
            supports_brokerage_events: false,
          },
        ])
      )),
      http.post('*/api/wallet/import/parse', async ({ request }) => {
        parseRequests.push(await request.formData())
        return HttpResponse.json({ rows })
      }),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={vi.fn()}
        accounts={[
          {
            id: 'account-1',
            name: 'Konto osobiste',
            walletName: 'Portfel',
            currency: 'PLN',
            available: '1000.00',
          },
        ]}
        brokerageAccounts={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Ten format obsługuje import transakcji gotówkowych.')

    const file = new File(['Data księgowania;Kwota transakcji (waluta rachunku)\n'], 'transactions_ing.csv', {
      type: 'text/csv',
    })
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput!, { target: { files: [file] } })

    fireEvent.click(screen.getAllByRole('combobox')[0]!)
    fireEvent.click(await screen.findByRole('option', { name: 'IngBank CSV · CSV' }))
    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))

    await screen.findByText('Podgląd transakcji')

    expect(parseRequests).toHaveLength(1)
    expect(parseRequests[0]?.get('parser_name')).toBe('IngBank CSV')
    await expect((parseRequests[0]?.get('file') as File).text()).resolves.toContain('Data księgowania')
    expect(screen.queryByText('Wybierz plik do importu')).not.toBeInTheDocument()
  })

  it('imports parsed rows, shows a success toast, and closes the dialog', async () => {
    await nextUiUnitStory('Wallet import dialog closes and shows toast after successful import', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'next-ui'],
    })

    const onOpenChange = vi.fn()
    server.use(
      http.get('*/api/wallet/import/parsers', () =>
        HttpResponse.json([
          { name: 'IngBank CSV', kind: 'CSV', accept: '.csv', upload_label: 'Wybierz plik CSV', supports_brokerage_events: false },
        ]),
      ),
      http.post('*/api/wallet/import/parse', () =>
        HttpResponse.json({
          rows: [{ date: '2026-05-10T10:00:00.000Z', amount: '-45.67', description: 'Zakup testowy', amount_after: '954.33' }],
        }),
      ),
      http.post('*/api/wallet/transactions', () =>
        HttpResponse.json({ success: true, summary: { created: 1 } }),
      ),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={onOpenChange}
        accounts={[{ id: 'account-1', name: 'Konto', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Ten format obsługuje import transakcji gotówkowych.')

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(['Data księgowania\n'], 'test.csv', { type: 'text/csv' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))
    await screen.findByText('Podgląd transakcji')

    fireEvent.click(screen.getByRole('button', { name: 'Importuj' }))

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Zaimportowano 1 transakcji')
    })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('shows an error message when the import request fails', async () => {
    await nextUiUnitStory('Wallet import dialog shows error message on failed import request', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'next-ui'],
    })

    const onOpenChange = vi.fn()
    server.use(
      http.get('*/api/wallet/import/parsers', () =>
        HttpResponse.json([
          { name: 'IngBank CSV', kind: 'CSV', accept: '.csv', upload_label: 'Wybierz plik CSV', supports_brokerage_events: false },
        ]),
      ),
      http.post('*/api/wallet/import/parse', () =>
        HttpResponse.json({
          rows: [{ date: '2026-05-10T10:00:00.000Z', amount: '-45.67', description: 'Zakup testowy', amount_after: '954.33' }],
        }),
      ),
      http.post('*/api/wallet/transactions', () =>
        HttpResponse.json({ error: 'Nie udało się zaimportować transakcji' }, { status: 422 }),
      ),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={onOpenChange}
        accounts={[{ id: 'account-1', name: 'Konto', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Ten format obsługuje import transakcji gotówkowych.')

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(['Data księgowania\n'], 'test.csv', { type: 'text/csv' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))
    await screen.findByText('Podgląd transakcji')

    fireEvent.click(screen.getByRole('button', { name: 'Importuj' }))

    await waitFor(() => {
      expect(screen.getByText('Nie udało się zaimportować transakcji')).toBeInTheDocument()
    })
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  it('sets the file input accept attribute to .pdf when a PDF parser is selected', async () => {
    await nextUiUnitStory('Wallet import dialog exposes PDF file input when a PDF parser is available', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/import/parsers', () =>
        HttpResponse.json([
          { name: 'Velo Bank PDF', kind: 'PDF', accept: '.pdf', upload_label: 'Wybierz plik PDF', supports_brokerage_events: false },
        ]),
      ),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={vi.fn()}
        accounts={[{ id: 'account-1', name: 'Konto', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Ten format obsługuje import transakcji gotówkowych.')

    // Wait for the parser metadata to propagate to the file input accept attribute
    await waitFor(() => {
      const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
      expect(fileInput?.accept).toBe('.pdf')
    })
  })

  it('shows import unavailable when the parsers API returns an error', async () => {
    await nextUiUnitStory('Wallet import dialog shows unavailable state when parsers API is down', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'next-ui'],
    })

    server.use(
      http.get('*/api/wallet/import/parsers', () => new HttpResponse(null, { status: 502 })),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={vi.fn()}
        accounts={[{ id: 'account-1', name: 'Konto', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Import niedostępny')
  })
})
