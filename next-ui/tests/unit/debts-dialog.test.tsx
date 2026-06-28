import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import { DebtsDialog, type DebtRow } from '@/features/wallet/components/DebtsDialog'
import { nextUiUnitStory } from '../allure'

const routerRefresh = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: routerRefresh }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const debt: DebtRow = {
  id: 'debt-1',
  walletId: 'wallet-1',
  walletName: 'Portfel rodzinny',
  name: 'Kredyt hipoteczny',
  lander: 'mBank',
  amount: '250000.00',
  currency: 'PLN',
  interestRatePct: '7.20',
  monthlyPayment: '2100.00',
  endDate: '2035-12-31T12:00:00.000Z',
  amountFmt: '250 000,00 PLN',
  monthlyFmt: '2 100,00 PLN',
}

function renderDebts(debts: DebtRow[] = [debt]) {
  return render(
    <DebtsDialog
      open
      onOpenChange={vi.fn()}
      totalFmt="250 000,00 PLN"
      subtitle="1 zobowiązanie"
      countFmt="1"
      avgRateFmt="7,20%"
      monthlyFmt="2 100,00 PLN"
      debts={debts}
      wallets={[{ id: 'wallet-1', name: 'Portfel rodzinny' }]}
      viewCurrency="PLN"
    />,
  )
}

function actionButtons(row: HTMLTableRowElement) {
  const cells = row.querySelectorAll('td')
  const actionCell = cells[cells.length - 1] as HTMLTableCellElement
  return within(actionCell).getAllByRole('button')
}

describe('DebtsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })

  it('saves edited debt amount and preserves the financial update payload', async () => {
    await nextUiUnitStory('Wallet debts dialog updates debt financial fields', {
      severity: 'critical',
      tags: ['wallet', 'debts', 'money', 'api-contract', 'next-ui'],
    })
    const requests: unknown[] = []
    server.use(
      http.put('*/api/wallet/debts/debt-1', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )

    renderDebts()

    fireEvent.change(screen.getByDisplayValue('250000.00'), {
      target: { value: '249500,50' },
    })
    const row = screen.getByDisplayValue('249500,50').closest('tr')
    expect(row).not.toBeNull()
    fireEvent.click(actionButtons(row as HTMLTableRowElement)[0]!)

    await waitFor(() => {
      expect(requests).toHaveLength(1)
      expect(requests[0]).toEqual(expect.objectContaining({
        name: 'Kredyt hipoteczny',
        lander: 'mBank',
        amount: '249500.50',
        currency: 'PLN',
        interest_rate_pct: '7.20',
        monthly_payment: '2100.00',
      }))
      expect((requests[0] as { end_date: string }).end_date).toMatch(/^2035-12-31T/)
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Zobowiązanie zaktualizowane'))
    expect(routerRefresh).toHaveBeenCalled()
  })

  it('keeps validation feedback on the edited row when required debt fields are cleared', async () => {
    await nextUiUnitStory('Wallet debts dialog validates required row fields before API calls', {
      severity: 'critical',
      tags: ['wallet', 'debts', 'validation', 'financial-data', 'next-ui'],
    })
    const updateMock = vi.fn()
    server.use(
      http.put('*/api/wallet/debts/debt-1', async ({ request }) => {
        updateMock(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )

    renderDebts()

    fireEvent.change(screen.getByDisplayValue('Kredyt hipoteczny'), {
      target: { value: '' },
    })
    const row = screen.getByDisplayValue('').closest('tr')
    expect(row).not.toBeNull()
    fireEvent.click(actionButtons(row as HTMLTableRowElement)[0]!)

    expect(screen.getByText('Podaj nazwę zobowiązania')).toBeInTheDocument()
    expect(updateMock).not.toHaveBeenCalled()
  })

  it('adds a new debt with normalized decimal fields and selected due date', async () => {
    await nextUiUnitStory('Wallet debts dialog creates a new debt with visible money inputs', {
      severity: 'critical',
      tags: ['wallet', 'debts', 'money', 'form-validation', 'next-ui'],
    })
    const requests: unknown[] = []
    server.use(
      http.post('*/api/wallet/debts', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )

    renderDebts([])

    fireEvent.click(screen.getByRole('button', { name: /Dodaj/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj' }))
    expect(screen.getByText('Podaj nazwę zobowiązania')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('np. Kredyt hipoteczny'), {
      target: { value: 'Pożyczka gotówkowa' },
    })
    fireEvent.change(screen.getByPlaceholderText('np. mBank'), {
      target: { value: 'Alior' },
    })
    fireEvent.change(screen.getByPlaceholderText('np. 250000'), {
      target: { value: '15000,99' },
    })
    fireEvent.change(screen.getByPlaceholderText('np. 7.2'), {
      target: { value: '9,25' },
    })
    fireEvent.change(screen.getByPlaceholderText('np. 2100'), {
      target: { value: '450,10' },
    })
    fireEvent.click(screen.getByText(/Wybierz datę/i))
    fireEvent.click(screen.getByRole('button', { name: /Teraz/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj' }))

    await waitFor(() => {
      expect(requests).toHaveLength(1)
      expect(requests[0]).toEqual(expect.objectContaining({
        wallet_id: 'wallet-1',
        name: 'Pożyczka gotówkowa',
        lander: 'Alior',
        amount: '15000.99',
        currency: 'PLN',
        interest_rate_pct: '9.25',
        monthly_payment: '450.10',
      }))
      expect((requests[0] as { end_date: string }).end_date).toMatch(/T/)
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Zobowiązanie zostało dodane'))
    expect(routerRefresh).toHaveBeenCalled()
  })
})
