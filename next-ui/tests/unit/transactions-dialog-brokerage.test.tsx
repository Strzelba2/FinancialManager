import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import { TransactionsDialog } from '@/features/wallet/components/TransactionsDialog'
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

describe('TransactionsDialog – brokerage form', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    server.resetHandlers()
  })
  it('sends a SPLIT brokerage event with split ratio and no cash amount fields', async () => {
    await nextUiUnitStory('Wallet brokerage form sends split event payload', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'split', 'next-ui'],
    })

    const requests: Request[] = []
    server.use(
      http.get('*/api/stock/markets', () => HttpResponse.json([{ mic: 'XWAR', name: 'GPW' }])),
      http.get('*/api/stock/instruments', () => HttpResponse.json([{ symbol: 'PKOBP', shortname: 'PKO BP SA' }])),
      http.post('*/api/wallet/brokerage/event', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ success: true })
      }),
    )

    const onOpenChange = vi.fn()
    render(
      <TransactionsDialog
        open
        onOpenChange={onOpenChange}
        accounts={[]}
        brokerageAccounts={[{ id: 'brokerage-1', name: 'ING Makler', walletName: 'Portfel' }]}
        initialTab="brokerage"
      />,
    )

    await screen.findByText('Rynek *')
    fireEvent.click(screen.getAllByRole('combobox')[1]!)
    fireEvent.click(await screen.findByRole('option', { name: 'XWAR · GPW' }))

    fireEvent.click(screen.getAllByRole('combobox')[2]!)
    fireEvent.click(await screen.findByRole('option', { name: 'PKOBP · PKO BP SA' }))

    fireEvent.click(screen.getAllByRole('combobox')[3]!)
    fireEvent.click(await screen.findByRole('option', { name: 'SPLIT' }))
    fireEvent.change(screen.getByPlaceholderText('2 lub 0.1'), { target: { value: '0,1' } })
    fireEvent.click(screen.getByText(/Wybierz datę/i))
    fireEvent.click(screen.getByRole('button', { name: /Teraz/i }))
    fireEvent.click(screen.getByRole('button', { name: /Dodaj operację/i }))

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Zdarzenie maklerskie zapisane')
    })
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(requests).toHaveLength(1)
    await expect(requests[0]?.json()).resolves.toEqual(expect.objectContaining({
      brokerage_account_id: 'brokerage-1',
      instrument_symbol: 'PKOBP',
      instrument_mic: 'XWAR',
      instrument_name: 'PKO BP SA',
      kind: 'SPLIT',
      quantity: '0',
      price: '0',
      currency: 'PLN',
      split_ratio: '0.1',
      note: null,
    }))
  })
})
