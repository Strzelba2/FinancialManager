import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import { QuotesPage } from '@/features/wallet/components/QuotesPage'
import { nextUiUnitStory } from '../allure'

const routerPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: routerPush,
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

describe('QuotesPage manual instruments', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })

  it('shows the PLNC quotes market fallback as PLN', async () => {
    await nextUiUnitStory('Stock quotes page exposes PLNC currency quotes in the market switcher', {
      severity: 'normal',
      tags: ['stock', 'quotes', 'currency', 'next-ui'],
    })

    server.use(
      http.get('*/api/stock/markets', () => HttpResponse.json({ error: 'markets unavailable' }, { status: 404 })),
    )

    render(<QuotesPage mic="XWAR" initialRows={[]} />)

    fireEvent.click(screen.getByRole('button', { name: 'PLN' }))

    expect(routerPush).toHaveBeenCalledWith('/stock/quotes/PLNC')
  })

  it('shows the GLIX quotes market fallback as global indexes', async () => {
    await nextUiUnitStory('Stock quotes page exposes GLIX global indexes in the market switcher', {
      severity: 'normal',
      tags: ['stock', 'quotes', 'indexes', 'next-ui'],
    })

    server.use(
      http.get('*/api/stock/markets', () => HttpResponse.json({ error: 'markets unavailable' }, { status: 404 })),
    )

    render(<QuotesPage mic="XWAR" initialRows={[]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Indeksy' }))

    expect(routerPush).toHaveBeenCalledWith('/stock/quotes/GLIX')
  })

  it('sends quote_source when adding a manual instrument with external URL', async () => {
    await nextUiUnitStory('Stock quotes page adds manual instrument with quote_source', {
      severity: 'critical',
      tags: ['stock', 'quote-source', 'next-ui'],
    })

    const instrumentRequests: unknown[] = []
    server.use(
      http.get('*/api/stock/markets', ({ request }) => {
        const url = new URL(request.url)
        if (url.searchParams.get('only_with_instruments') === 'true') {
          return HttpResponse.json([{ mic: 'XLON', name: 'London' }])
        }
        return HttpResponse.json([
          { mic: 'XWAR', name: 'Warsaw' },
          { mic: 'XLON', name: 'London' },
          { mic: 'XNAS', name: 'Nasdaq' },
        ])
      }),
      http.post('*/api/stock/instruments', async ({ request }) => {
        const body = await request.json()
        instrumentRequests.push(body)
        return HttpResponse.json(
          Object.assign({}, body as Record<string, unknown>, { market_id: 'market-1', mic: 'XLON' }),
          { status: 201 },
        )
      }),
      http.get('*/api/stock/quotes', () => (
        HttpResponse.json([
          {
            symbol: 'LNGA.UK',
            name: 'WisdomTree Natural Gas',
            lastPrice: 12.34,
            changePct: 1.23,
            volume: 1234,
            lastPriceFmt: '12,34',
            changePctFmt: '+1,23%',
            lastTradeDateFmt: '03.06.2026',
            lastTradeTimeFmt: '09:00',
          },
        ])
      )),
    )

    render(<QuotesPage mic="XLON" initialRows={[]} />)

    expect(await screen.findByRole('button', { name: 'London' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Instrument' }))
    const dialog = await screen.findByRole('dialog', { name: 'Dodaj instrument' })
    expect(within(dialog).getByRole('option', { name: 'XNAS · Nasdaq' })).toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('Symbol'), { target: { value: 'lnga.uk' } })
    fireEvent.change(within(dialog).getByLabelText('Skrót'), { target: { value: 'lnga.uk' } })
    fireEvent.change(within(dialog).getByLabelText('Nazwa'), { target: { value: 'WisdomTree Natural Gas' } })
    fireEvent.change(within(dialog).getByLabelText('Źródło notowań'), {
      target: { value: 'https://quotes.example.com/q/g/?s=lnga.uk' },
    })
    fireEvent.change(within(dialog).getByLabelText('Źródło historii'), {
      target: { value: 'https://quotes.example.com/q/d/l/?s=lnga.uk&i=d' },
    })

    fireEvent.click(within(dialog).getByRole('button', { name: 'Dodaj instrument' }))

    await waitFor(() => {
      expect(instrumentRequests).toHaveLength(1)
    })
    expect(instrumentRequests[0]).toEqual(expect.objectContaining({
      market_mic: 'XLON',
      symbol: 'LNGA.UK',
      shortname: 'LNGA.UK',
      historical_source: 'https://quotes.example.com/q/d/l/?s=lnga.uk&i=d',
      quote_source: 'https://quotes.example.com/q/g/?s=lnga.uk',
    }))
  })

  it('shows quote_source refresh counts after manual ingest polling completes', async () => {
    await nextUiUnitStory('Stock quotes page reports manual quote_source refresh counts', {
      severity: 'normal',
      tags: ['stock', 'quote-source', 'refresh', 'next-ui'],
    })

    vi.useFakeTimers()
    try {
      let statusCalls = 0
      server.use(
        http.get('*/api/stock/markets', () => HttpResponse.json([{ mic: 'XWAR', name: 'GPW' }])),
        http.post('*/api/stock/refresh', () => HttpResponse.json({ ok: true, mode: 'ingest' }, { status: 202 })),
        http.get('*/api/stock/refresh', () => {
          statusCalls += 1
          return HttpResponse.json(
            statusCalls === 1
              ? { state: 'running' }
              : { state: 'done', quote_source_processed: 2, quote_source_failed: 1 },
          )
        }),
        http.get('*/api/stock/quotes', () => (
          HttpResponse.json([
            {
              symbol: 'PKO',
              name: 'PKOBP',
              lastPrice: 55.12,
              changePct: 1.2,
              volume: 1000,
              lastPriceFmt: '55,12',
              changePctFmt: '+1,20%',
              lastTradeDateFmt: '03.06.2026',
              lastTradeTimeFmt: '09:00',
            },
          ])
        )),
      )

      render(<QuotesPage mic="XWAR" initialRows={[]} />)

      fireEvent.click(screen.getByRole('button', { name: 'Odśwież' }))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(screen.getAllByText(/Uruchomiono odświeżanie/).length).toBeGreaterThan(0)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000)
        await vi.advanceTimersByTimeAsync(2_000)
        await Promise.resolve()
      })
      expect(screen.getByText('PKO')).toBeInTheDocument()
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Ręczne: 2, błędów: 1.'))
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows manual quote_source error details when the refreshed market still has no quotes', async () => {
    await nextUiUnitStory('Stock quotes page surfaces manual quote_source parser errors', {
      severity: 'critical',
      tags: ['stock', 'quote-source', 'refresh', 'next-ui'],
    })

    vi.useFakeTimers()
    try {
      let statusCalls = 0
      server.use(
        http.get('*/api/stock/markets', () => HttpResponse.json([{ mic: 'XLON', name: 'London' }])),
        http.post('*/api/stock/refresh', () => HttpResponse.json({ ok: true, mode: 'ingest' }, { status: 202 })),
        http.get('*/api/stock/refresh', () => {
          statusCalls += 1
          return HttpResponse.json(
            statusCalls === 1
              ? { state: 'running' }
              : {
                state: 'done',
                quote_source_processed: 0,
                quote_source_failed: 1,
                quote_source_errors: [
                  {
                    symbol: 'LNGA.UK',
                    mic: 'XLON',
                    detail: 'Quote source page does not contain last price',
                  },
                ],
              },
          )
        }),
        http.get('*/api/stock/quotes', () => HttpResponse.json({ error: 'No quotes for MIC' }, { status: 404 })),
      )

      render(<QuotesPage mic="XLON" initialRows={[]} />)

      fireEvent.click(screen.getByRole('button', { name: 'Odśwież' }))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000)
        await vi.advanceTimersByTimeAsync(2_000)
        await Promise.resolve()
      })

      expect(screen.getAllByText(/Błędy ręcznych źródeł notowań: LNGA\.UK \(XLON\)/).length).toBeGreaterThan(0)
      expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('LNGA.UK (XLON)'))
    } finally {
      vi.useRealTimers()
    }
  })
})
