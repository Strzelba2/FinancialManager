import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import { CashDialog, type CashRow } from '@/features/wallet/components/CashDialog'
import { nextUiUnitStory } from '../allure'

const routerRefresh = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: routerRefresh }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const safe: CashRow = {
  id: 'cash-1',
  walletId: 'wallet-1',
  walletName: 'Portfel rodzinny',
  name: 'Sejf',
  amount: '1500.00',
  currency: 'PLN',
  note: '',
  valueFmt: '1 500 PLN',
}

function renderCash(cashHoldings: CashRow[] = [safe]) {
  return render(
    <CashDialog
      open
      onOpenChange={vi.fn()}
      totalFmt="11 500 PLN"
      accountsFmt="10 000 PLN"
      physicalFmt="1 500 PLN"
      accountsCount={2}
      cashHoldings={cashHoldings}
      wallets={[{ id: 'wallet-1', name: 'Portfel rodzinny' }]}
      viewCurrency="PLN"
    />,
  )
}

describe('CashDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })

  it('shows the cash split between accounts and physical cash', async () => {
    await nextUiUnitStory('Wallet cash dialog shows accounts and physical cash totals', {
      severity: 'normal',
      tags: ['wallet', 'cash', 'money', 'next-ui'],
    })

    renderCash()

    expect(screen.getByText('Szczegóły gotówki')).toBeInTheDocument()
    expect(screen.getByText('11 500 PLN')).toBeInTheDocument()
    expect(screen.getByText('10 000 PLN')).toBeInTheDocument()
    expect(screen.getAllByText('1 500 PLN').length).toBeGreaterThan(0)
    expect(screen.getByDisplayValue('Sejf')).toBeInTheDocument()
  })

  it('shows the empty state when there is no physical cash', async () => {
    await nextUiUnitStory('Wallet cash dialog shows the empty state', {
      severity: 'minor',
      tags: ['wallet', 'cash', 'empty-state', 'next-ui'],
    })

    renderCash([])

    expect(screen.getByText('Brak gotówki fizycznej w portfelu')).toBeInTheDocument()
  })

  it('adds physical cash with a normalized decimal amount and selected currency', async () => {
    await nextUiUnitStory('Wallet cash dialog creates a physical cash position', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'money', 'form-validation', 'next-ui'],
    })
    const requests: unknown[] = []
    server.use(
      http.post('*/api/wallet/cash-holdings', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ success: true })
      }),
    )

    renderCash([])

    fireEvent.click(screen.getByRole('button', { name: /Dodaj/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj' }))
    expect(screen.getByText('Podaj nazwę pozycji')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Nazwa *'), { target: { value: '  Portfel  ' } })
    fireEvent.change(screen.getByLabelText('Kwota *'), { target: { value: '1 250,50' } })
    fireEvent.change(screen.getByLabelText('Notatka'), { target: { value: 'na wakacje' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj' }))

    await waitFor(() => {
      expect(requests).toEqual([{
        wallet_id: 'wallet-1',
        name: 'Portfel',
        amount: '1250.50',
        currency: 'PLN',
        note: 'na wakacje',
      }])
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Gotówka została dodana'))
    expect(routerRefresh).toHaveBeenCalled()
  })

  it('rejects a negative amount before calling the API', async () => {
    await nextUiUnitStory('Wallet cash dialog rejects negative amounts', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'money', 'validation', 'next-ui'],
    })
    const createMock = vi.fn()
    server.use(
      http.post('*/api/wallet/cash-holdings', async ({ request }) => {
        createMock(await request.json())
        return HttpResponse.json({ success: true })
      }),
    )

    renderCash([])

    fireEvent.click(screen.getByRole('button', { name: /Dodaj/i }))
    fireEvent.change(screen.getByLabelText('Nazwa *'), { target: { value: 'Portfel' } })
    fireEvent.change(screen.getByLabelText('Kwota *'), { target: { value: '-20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj' }))

    expect(screen.getByText('Podaj kwotę większą lub równą 0')).toBeInTheDocument()
    expect(createMock).not.toHaveBeenCalled()
  })

  it('saves an edited amount for an existing position', async () => {
    await nextUiUnitStory('Wallet cash dialog updates a physical cash position', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'money', 'api-contract', 'next-ui'],
    })
    const requests: unknown[] = []
    server.use(
      http.put('*/api/wallet/cash-holdings/cash-1', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ success: true })
      }),
    )

    renderCash()

    expect(screen.queryByRole('button', { name: 'Zapisz zmiany' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Kwota'), { target: { value: '1499,99' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

    await waitFor(() => {
      expect(requests).toEqual([{ name: 'Sejf', amount: '1499.99', currency: 'PLN', note: '' }])
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Gotówka zaktualizowana'))
  })

  it('shows the backend error on the row when saving fails', async () => {
    await nextUiUnitStory('Wallet cash dialog shows update errors on the row', {
      severity: 'normal',
      tags: ['wallet', 'cash', 'error-state', 'next-ui'],
    })
    server.use(
      http.put('*/api/wallet/cash-holdings/cash-1', () => HttpResponse.json({ error: 'Cash holding not found' }, { status: 400 })),
    )

    renderCash()

    fireEvent.change(screen.getByLabelText('Kwota'), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

    expect(await screen.findByText('Cash holding not found')).toBeInTheDocument()
    expect(routerRefresh).not.toHaveBeenCalled()
  })

  it('deletes a position only after confirmation', async () => {
    await nextUiUnitStory('Wallet cash dialog deletes a position after confirmation', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'delete', 'next-ui'],
    })
    const deleteMock = vi.fn()
    server.use(
      http.delete('*/api/wallet/cash-holdings/cash-1', () => {
        deleteMock()
        return HttpResponse.json({ success: true })
      }),
    )

    renderCash()

    fireEvent.click(screen.getByRole('button', { name: 'Usuń pozycję' }))
    expect(screen.getByText('Czy na pewno usunąć?')).toBeInTheDocument()
    expect(deleteMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź usunięcie' }))

    await waitFor(() => expect(deleteMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Pozycja gotówki usunięta'))
    expect(routerRefresh).toHaveBeenCalled()
  })
})
