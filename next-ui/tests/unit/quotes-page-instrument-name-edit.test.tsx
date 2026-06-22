import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'

import { QuotesPage } from '@/features/wallet/components/QuotesPage'
import { server } from '../msw-server'
import { nextUiUnitStory } from '../allure'


vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))


const ROW = {
  symbol: 'PKO',
  name: 'PKO',
  lastPrice: 55.12,
  changePct: 1.2,
  volume: 1000,
  lastPriceFmt: '55,12',
  changePctFmt: '+1,20%',
  lastTradeDateFmt: '22.06.2026',
  lastTradeTimeFmt: '10:00',
  currency: 'PLN',
}


function marketsHandler() {
  return http.get('*/api/stock/markets', () => HttpResponse.json([{ mic: 'XWAR', name: 'GPW' }]))
}


function nameButton() {
  return screen.getByRole('button', { name: /Nazwa instrumentu PKO:/ })
}


describe('QuotesPage instrument name editing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
    server.use(marketsHandler())
  })

  it('opens on double-click and saves a committed Enter edit', async () => {
    await nextUiUnitStory('Quote instrument names require double-click and explicit row save', {
      severity: 'critical',
      tags: ['next-ui', 'stock', 'wallet', 'instruments', 'financial-data'],
    })
    const requests: unknown[] = []
    server.use(
      http.put('*/api/wallet/instruments/PKO/name', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ symbol: 'PKO', mic: 'XWAR', name: 'PKO BP SA', created: true })
      }),
    )
    render(<QuotesPage mic="XWAR" initialRows={[ROW]} />)

    fireEvent.click(nameButton())
    expect(screen.queryByRole('textbox', { name: 'Edytuj nazwę instrumentu PKO' })).not.toBeInTheDocument()

    fireEvent.doubleClick(nameButton())
    const input = screen.getByRole('textbox', { name: 'Edytuj nazwę instrumentu PKO' })
    expect(input).toHaveValue('PKO')
    fireEvent.change(input, { target: { value: 'Pko bp sa' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    const save = await screen.findByRole('button', { name: 'Zapisz nazwę instrumentu PKO' })
    fireEvent.click(save)

    await waitFor(() => expect(requests).toEqual([{ mic: 'XWAR', name: 'Pko bp sa' }]))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Nazwa instrumentu została zapisana'))
    expect(nameButton()).toHaveTextContent('PKO BP SA')
    expect(screen.queryByRole('button', { name: 'Zapisz nazwę instrumentu PKO' })).not.toBeInTheDocument()
  })

  it('supports Escape and ignores unchanged blur commits', async () => {
    await nextUiUnitStory('Quote instrument name editing cancels cleanly and avoids false dirty state', {
      severity: 'normal',
      tags: ['next-ui', 'stock', 'instruments', 'keyboard'],
    })
    render(<QuotesPage mic="XWAR" initialRows={[ROW]} />)

    fireEvent.doubleClick(nameButton())
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edytuj nazwę instrumentu PKO' }), { key: 'Escape' })
    expect(screen.queryByRole('button', { name: 'Zapisz nazwę instrumentu PKO' })).not.toBeInTheDocument()

    fireEvent.doubleClick(nameButton())
    fireEvent.blur(screen.getByRole('textbox', { name: 'Edytuj nazwę instrumentu PKO' }))
    expect(screen.queryByRole('button', { name: 'Zapisz nazwę instrumentu PKO' })).not.toBeInTheDocument()
  })

  it('keeps the dirty value and save action after a backend conflict', async () => {
    await nextUiUnitStory('Quote instrument name conflicts preserve the user edit for retry', {
      severity: 'critical',
      tags: ['next-ui', 'stock', 'wallet', 'instruments', 'api-contract'],
    })
    server.use(
      http.put('*/api/wallet/instruments/PKO/name', () => (
        HttpResponse.json({ error: 'Instrument shortname changed concurrently.' }, { status: 409 })
      )),
    )
    render(<QuotesPage mic="XWAR" initialRows={[ROW]} />)

    fireEvent.doubleClick(nameButton())
    const input = screen.getByRole('textbox', { name: 'Edytuj nazwę instrumentu PKO' })
    fireEvent.change(input, { target: { value: 'PKO BP SA' } })
    fireEvent.blur(input)
    fireEvent.click(await screen.findByRole('button', { name: 'Zapisz nazwę instrumentu PKO' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Instrument shortname changed concurrently.'))
    expect(nameButton()).toHaveTextContent('PKO BP SA')
    expect(screen.getByRole('button', { name: 'Zapisz nazwę instrumentu PKO' })).toBeInTheDocument()
  })

  it('does not overwrite an unsaved name during quote refresh', async () => {
    await nextUiUnitStory('Quote refresh preserves unsaved instrument display names', {
      severity: 'critical',
      tags: ['next-ui', 'stock', 'wallet', 'instruments', 'refresh'],
    })
    server.use(
      http.post('*/api/stock/refresh', () => HttpResponse.json({ ok: true, mode: 'reload' })),
      http.get('*/api/stock/quotes', () => HttpResponse.json([ROW])),
    )
    render(<QuotesPage mic="XWAR" initialRows={[ROW]} />)

    fireEvent.doubleClick(nameButton())
    const input = screen.getByRole('textbox', { name: 'Edytuj nazwę instrumentu PKO' })
    fireEvent.change(input, { target: { value: 'PKO BP SA' } })
    fireEvent.blur(input)
    fireEvent.click(screen.getByRole('button', { name: 'Odśwież' }))

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Notowania zostały pobrane'))
    expect(nameButton()).toHaveTextContent('PKO BP SA')
    expect(screen.getByRole('button', { name: 'Zapisz nazwę instrumentu PKO' })).toBeInTheDocument()
  })
})
