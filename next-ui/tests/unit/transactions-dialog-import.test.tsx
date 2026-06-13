import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
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

const brokerageRows = [
  {
    trade_at: '2026-06-01T09:00:00.000Z',
    instrument_symbol: 'PKOBP',
    instrument_mic: 'XWAR',
    instrument_name: 'PKO BP SA',
    kind: 'BUY',
    quantity: '1.00',
    price: '10.00',
    currency: 'PLN',
    split_ratio: '0.00',
  },
]

describe('TransactionsDialog import preview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
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

  it('blocks BoSSA history import when preview contains an unresolved instrument', async () => {
    await nextUiUnitStory('BoSSA history import blocks rows requiring instrument review', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'bossa', 'import', 'next-ui'],
    })

    let importRequests = 0
    server.use(
      http.get('*/api/wallet/import/parsers', () => (
        HttpResponse.json([
          {
            name: 'BossaMakler CSV',
            kind: 'CSV',
            accept: '.csv',
            upload_label: 'Wybierz plik CSV',
            supports_brokerage_events: false,
            supports_brokerage_history: true,
          },
        ])
      )),
      http.post('*/api/wallet/import/parse', () => (
        HttpResponse.json({
          rows: [
            {
              row_number: 13,
              operation_type: 'NEEDS_REVIEW',
              trade_at: '2026-06-04T10:00:00.000Z',
              currency: 'USD',
              amount: '-12.34',
              amount_after: '0.00',
              description: 'Rozliczenie transakcji kupna WisdomTree Natural Gas',
              instrument_name: 'WisdomTree Natural Gas',
              review_reason: 'Nie znaleziono instrumentu WisdomTree Natural Gas (ISIN: IE00TEST0001), waluta USD.',
            },
          ],
        })
      )),
      http.post('*/api/wallet/brokerage/history/import', () => {
        importRequests += 1
        return HttpResponse.json({ error: 'should not import' }, { status: 500 })
      }),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={vi.fn()}
        accounts={[{ id: 'account-1', name: 'Konto', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[{ id: 'brokerage-1', name: 'Bossa IKE', walletName: 'Portfel' }]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Pełna historia maklerska')

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(['data;tytuł operacji\n'], 'bossa.csv', { type: 'text/csv' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))

    await screen.findByText('Podgląd historii BoSSA')
    expect(screen.getByText(/Row 13: WisdomTree Natural Gas/)).toBeInTheDocument()
    expect(screen.getAllByText(/IE00TEST0001/).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Importuj' })).toBeDisabled()
    expect(importRequests).toBe(0)
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

  it('shows brokerage import retry summary when duplicate rows are skipped', async () => {
    await nextUiUnitStory('Wallet brokerage import dialog reports created and duplicate skipped rows', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'import', 'next-ui', 'financial-data'],
    })

    const onOpenChange = vi.fn()
    server.use(
      http.get('*/api/wallet/import/parsers', () =>
        HttpResponse.json([
          {
            name: 'IngMakler CSV',
            kind: 'CSV',
            accept: '.csv',
            upload_label: 'Wybierz plik CSV',
            supports_brokerage_events: true,
          },
        ]),
      ),
      http.post('*/api/wallet/import/parse', () =>
        HttpResponse.json({ rows: brokerageRows }),
      ),
      http.post('*/api/wallet/brokerage/events/import', () =>
        HttpResponse.json({
          total: 13,
          created: 1,
          skipped_duplicates: 12,
          failed: 0,
          errors: [],
          rows: [
            { row: 1, status: 'skipped_duplicate', message: 'Brokerage event already exists.' },
            { row: 13, status: 'created', brokerage_event_id: 'event-13' },
          ],
        }),
      ),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={onOpenChange}
        accounts={[{ id: 'account-1', name: 'Konto', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[{ id: 'brokerage-1', name: 'ING Makler', walletName: 'Portfel' }]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Tryb importu *')
    fireEvent.click(screen.getAllByRole('combobox')[1]!)
    fireEvent.click(await screen.findByRole('option', { name: 'Import jako operacje maklerskie' }))

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(['Data transakcji;Instrument\n'], 'brokerage.csv', { type: 'text/csv' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))
    await screen.findByText('Podgląd operacji maklerskich')

    fireEvent.click(screen.getByRole('button', { name: 'Importuj' }))

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        'Import maklerski zakończony. Razem: 13, utworzono: 1, pominięto duplikatów: 12, błędów: 0',
      )
    })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('uses BoSSA full history mode and previews generated balance rows', async () => {
    await nextUiUnitStory('Wallet import dialog uses BoSSA full history mode with generated balances', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'bossa', 'import', 'next-ui', 'financial-data'],
    })

    let submittedMode: FormDataEntryValue | null = null
    server.use(
      http.get('*/api/wallet/import/parsers', () =>
        HttpResponse.json([
          {
            name: 'BossaMakler CSV',
            kind: 'CSV',
            accept: '.csv',
            upload_label: 'Wybierz plik CSV',
            supports_brokerage_events: true,
            supports_brokerage_history: true,
          },
        ]),
      ),
      http.post('*/api/wallet/import/parse', async ({ request }) => {
        const form = await request.formData()
        submittedMode = form.get('mode')
        return HttpResponse.json({
          rows: [
            {
              row_number: 2,
              operation_type: 'TRANSFER',
              trade_at: '2026-06-04T00:00:00.000Z',
              currency: 'USD',
              amount: '100.00',
              amount_after: '100.00',
              description: 'Przelew do DM BOŚ USD',
            },
          ],
        })
      }),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={vi.fn()}
        accounts={[{ id: 'account-1', name: 'Konto', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[{ id: 'brokerage-1', name: 'BoSSA IKE', walletName: 'Portfel' }]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Pełna historia maklerska')
    expect(screen.getByText('Rachunek maklerski dla operacji *')).toBeInTheDocument()

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(['data;kwota;waluta\n'], 'bossa.csv', { type: 'text/csv' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))

    await screen.findByText('Podgląd historii BoSSA')
    expect(screen.getAllByText(/100\.00 USD/)).not.toHaveLength(0)
    expect(screen.getByText('Przelew do DM BOŚ USD')).toBeInTheDocument()
    expect(submittedMode).toBe('brokerage_history')
  })

  it('shows enriched brokerage import errors with instrument and missing quantity context', async () => {
    await nextUiUnitStory('Wallet brokerage import dialog shows enriched failed row diagnostics', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'import', 'next-ui', 'financial-data'],
    })

    const onOpenChange = vi.fn()
    server.use(
      http.get('*/api/wallet/import/parsers', () =>
        HttpResponse.json([
          {
            name: 'IngMakler CSV',
            kind: 'CSV',
            accept: '.csv',
            upload_label: 'Wybierz plik CSV',
            supports_brokerage_events: true,
          },
        ]),
      ),
      http.post('*/api/wallet/import/parse', () =>
        HttpResponse.json({
          rows: [{
            ...brokerageRows[0]!,
            trade_at: '2021-12-23T15:13:53.000Z',
            instrument_symbol: 'GIGRO',
            instrument_name: 'GIGROUP SA',
            kind: 'SELL',
            quantity: '1269.00',
            price: '1.00',
          }],
        }),
      ),
      http.post('*/api/wallet/brokerage/events/import', () =>
        HttpResponse.json({
          total: 1,
          created: 0,
          skipped_duplicates: 0,
          failed: 1,
          errors: [],
          rows: [
            {
              row: 246,
              status: 'failed',
              message: 'Row 246: HTTP 400 - Cannot sell 1269.00 GIGRO on 2021-12-23; holding has 0, missing 1269.00.',
              instrument_symbol: 'GIGRO',
              instrument_name: 'GIGROUP SA',
              kind: 'SELL',
              trade_at: '2021-12-23T15:13:53.000Z',
              quantity: '1269.00',
              held_quantity: '0',
              missing_quantity: '1269.00',
              reason_code: 'holding_quantity_exceeded',
            },
          ],
        }),
      ),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={onOpenChange}
        accounts={[{ id: 'account-1', name: 'Konto', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[{ id: 'brokerage-1', name: 'ING Makler', walletName: 'Portfel' }]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Tryb importu *')
    fireEvent.click(screen.getAllByRole('combobox')[1]!)
    fireEvent.click(await screen.findByRole('option', { name: 'Import jako operacje maklerskie' }))

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(['Data transakcji;Instrument\n'], 'brokerage.csv', { type: 'text/csv' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))
    await screen.findByText('Podgląd operacji maklerskich')

    fireEvent.click(screen.getByRole('button', { name: 'Importuj' }))

    await screen.findByText(/Row 246: GIGRO, SELL 1269,00/)
    expect(screen.getByText(/posiadane 0,00, brakuje 1269,00/)).toBeInTheDocument()
    expect(screen.getByText(/Razem: 1, utworzono: 0, pominięto duplikatów: 0, błędów: 1/)).toBeInTheDocument()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
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

  it('imports a Saxo file in full mode creating cash transactions and brokerage events', async () => {
    await nextUiUnitStory('Wallet import dialog full mode imports cash and brokerage from one file', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'brokerage', 'saxo', 'import', 'next-ui', 'financial-data'],
    })

    const onOpenChange = vi.fn()
    const parseModes: string[] = []
    let txImport = 0
    let eventsImport = 0
    server.use(
      http.get('*/api/wallet/import/parsers', () =>
        HttpResponse.json([
          {
            name: 'SaxoMakler CSV',
            kind: 'CSV',
            accept: '.csv',
            upload_label: 'Wybierz plik CSV',
            supports_brokerage_events: true,
            supports_full_import: true,
          },
        ]),
      ),
      http.post('*/api/wallet/import/parse', async ({ request }) => {
        const form = await request.formData()
        const mode = String(form.get('mode'))
        parseModes.push(mode)
        if (mode === 'transactions') {
          return HttpResponse.json({
            rows: [{ date: '2026-01-20T10:00:00.000Z', amount: '4825.57', description: 'Sprzedaż Schaeffler', amount_after: '9161.25' }],
          })
        }
        return HttpResponse.json({ rows: brokerageRows })
      }),
      http.post('*/api/wallet/transactions', () => {
        txImport += 1
        return HttpResponse.json({ success: true, summary: { created: 1 } })
      }),
      http.post('*/api/wallet/brokerage/events/import', () => {
        eventsImport += 1
        return HttpResponse.json({
          total: 1,
          created: 1,
          skipped_duplicates: 0,
          failed: 0,
          errors: [],
          rows: [{ row: 1, status: 'created', brokerage_event_id: 'event-1' }],
        })
      }),
    )

    render(
      <TransactionsDialog
        open
        onOpenChange={onOpenChange}
        accounts={[{ id: 'account-1', name: 'Konto PLN', walletName: 'Portfel', currency: 'PLN', available: '1000.00' }]}
        brokerageAccounts={[{ id: 'brokerage-1', name: 'Saxo', walletName: 'Portfel' }]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Import CSV' }))
    await screen.findByText('Tryb importu *')
    fireEvent.click(screen.getAllByRole('combobox')[1]!)
    fireEvent.click(await screen.findByRole('option', { name: 'Pełny import (transakcje + operacje maklerskie)' }))

    expect(screen.getByText('Konto dla importowanych transakcji *')).toBeInTheDocument()
    expect(screen.getByText('Rachunek maklerski dla operacji *')).toBeInTheDocument()

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(['Data transakcji;Zdarzenie;Kwota;Saldo po operacji;Waluta\n'], 'saxo_pln.csv', { type: 'text/csv' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Przetwórz plik' }))

    await screen.findByText('Podgląd transakcji')
    await screen.findByText('Podgląd operacji maklerskich')
    expect(parseModes).toEqual(['transactions', 'brokerage_events'])

    fireEvent.click(screen.getByRole('button', { name: 'Importuj' }))

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        'Zaimportowano: 1 transakcji gotówkowych i 1 operacji maklerskich (pominięto 0, błędów 0)',
      )
    })
    expect(txImport).toBe(1)
    expect(eventsImport).toBe(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
