import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'

import { BrokerageEventsPage } from '@/features/wallet/components/BrokerageEventsPage'
import type { EventRow, EventsPageResult, FxRates } from '@/lib/api/brokerageEvents'
import { nextUiUnitStory } from '../allure'

vi.mock('@/features/wallet/components/TransactionsDialog', () => ({
  TransactionsDialog: ({ open }: { open: boolean }) => (
    open ? <div role="dialog" aria-label="Dodaj operację maklerską" /> : null
  ),
}))

const fxRates: FxRates = {
  'USD/PLN': 4,
  'PLN/USD': 0.25,
  'EUR/PLN': 4.5,
  'PLN/EUR': 0.2222,
  'USD/EUR': 0.8889,
  'EUR/USD': 1.125,
  'CHF/PLN': 4.7,
  'CHF/USD': 1.175,
  'CHF/EUR': 1.0444,
  'GBP/PLN': 5.2,
  'GBP/USD': 1.3,
  'GBP/EUR': 1.1556,
}

function eventRow(overrides: Partial<EventRow> = {}): EventRow {
  return {
    id: 'event-1',
    tradeAt: '01.06.2026, 10:00',
    accountId: 'brokerage-1',
    accountName: 'ING Makler',
    symbol: 'PKO',
    instrumentName: 'PKO Bank Polski',
    kind: 'BUY',
    quantity: 10,
    priceNative: 20,
    priceView: 20,
    currency: 'PLN',
    notionalView: 200,
    notionalFmt: '200,00 PLN',
    splitRatio: 0,
    note: null,
    ...overrides,
  }
}

function pageResult(rows: EventRow[] = [eventRow()], overrides: Partial<EventsPageResult> = {}): EventsPageResult {
  return {
    rows,
    total: rows.length,
    page: 1,
    pageNotional: rows.reduce((sum, row) => sum + row.notionalView, 0),
    allNotional: rows.reduce((sum, row) => sum + row.notionalView, 0),
    viewCcy: 'PLN',
    fxRates,
    ...overrides,
  }
}

function renderEvents(initialData: EventsPageResult = pageResult()) {
  return render(
    <BrokerageEventsPage
      brokerageAccounts={[{ id: 'brokerage-1', name: 'ING Makler', walletName: 'Portfel' }]}
      initialData={initialData}
    />,
  )
}

describe('BrokerageEventsPage', () => {
  beforeEach(() => {
    server.resetHandlers()
  })

  it('edits event quantity inline and sends a batch patch before reloading rows', async () => {
    await nextUiUnitStory('Wallet brokerage events page persists inline quantity corrections', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'events', 'holdings', 'api-contract', 'next-ui'],
    })
    const patches: unknown[] = []
    const reloads: URL[] = []
    server.use(
      http.patch('*/api/wallet/events', async ({ request }) => {
        patches.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
      http.get('*/api/wallet/events', ({ request }) => {
        reloads.push(new URL(request.url))
        return HttpResponse.json(pageResult([eventRow({ quantity: 12, notionalView: 240, notionalFmt: '240,00 PLN' })]))
      }),
    )

    renderEvents()

    fireEvent.click(screen.getByText('10,0000'))
    fireEvent.change(screen.getByDisplayValue('10'), { target: { value: '12' } })
    fireEvent.keyDown(screen.getByDisplayValue('12'), { key: 'Enter', code: 'Enter' })
    fireEvent.click(screen.getByRole('button', { name: /Zapisz \(1\)/i }))

    await waitFor(() => {
      expect(patches).toEqual([{ items: [{ id: 'event-1', quantity: '12' }] }])
    })
    await waitFor(() => expect(reloads).toHaveLength(1))
    expect(await screen.findByText('Zapisano zmiany')).toBeInTheDocument()
  })

  it('requests filtered event pages for account, kind, currency and date presets', async () => {
    await nextUiUnitStory('Wallet brokerage events page maps filters to event query parameters', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'events', 'filters', 'api-contract', 'next-ui'],
    })
    const urls: URL[] = []
    server.use(
      http.get('*/api/wallet/events', ({ request }) => {
        urls.push(new URL(request.url))
        return HttpResponse.json(pageResult())
      }),
    )

    renderEvents()

    fireEvent.click(screen.getByRole('button', { name: 'ING Makler' }))
    await waitFor(() => expect(urls.at(-1)?.searchParams.get('account_id')).toBe('brokerage-1'))

    fireEvent.click(screen.getByRole('button', { name: /Wszystkie typy/i }))
    fireEvent.click(await screen.findByRole('button', { name: /Kupno/i }))
    await waitFor(() => expect(urls.at(-1)?.searchParams.get('kind')).toBe('BUY'))

    fireEvent.click(screen.getByRole('button', { name: 'USD' }))
    await waitFor(() => expect(urls.at(-1)?.searchParams.get('view_ccy')).toBe('USD'))

    fireEvent.click(screen.getByRole('button', { name: '1M' }))
    await waitFor(() => {
      expect(urls.at(-1)?.searchParams.get('date_from')).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(urls.at(-1)?.searchParams.get('date_to')).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    })
  })

  it('deletes a brokerage event only after confirmation and reloads the page', async () => {
    await nextUiUnitStory('Wallet brokerage events page confirms destructive event deletion', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'events', 'delete', 'financial-data', 'next-ui'],
    })
    const deletes: string[] = []
    const reloads: string[] = []
    server.use(
      http.delete('*/api/wallet/events/event-1', ({ request }) => {
        deletes.push(request.url)
        return HttpResponse.json({ ok: true })
      }),
      http.get('*/api/wallet/events', ({ request }) => {
        reloads.push(request.url)
        return HttpResponse.json(pageResult([]))
      }),
    )

    renderEvents()

    const eventRowEl = screen.getByText('PKO').closest('tr')
    expect(eventRowEl).not.toBeNull()
    fireEvent.click(eventRowEl!.querySelector('button[title="Usuń operację"]') as HTMLButtonElement)
    expect(screen.getByText('Usunąć operację?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Usuń' }))

    await waitFor(() => expect(deletes).toHaveLength(1))
    await waitFor(() => expect(reloads).toHaveLength(1))
    expect(await screen.findByText('Usunięto operację')).toBeInTheDocument()
  })
})
