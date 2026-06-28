import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import { InvestmentsDialog } from '@/features/wallet/components/InvestmentsDialog'
import { nextUiUnitStory } from '../allure'

const routerRefresh = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: routerRefresh }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

function renderDialog() {
  return render(
    <InvestmentsDialog
      open
      onOpenChange={vi.fn()}
      totalFmt="750 000,00 PLN"
      brokerageFmt="100 000,00 PLN"
      estatesFmt="600 000,00 PLN"
      metalsFmt="50 000,00 PLN"
      viewCurrency="PLN"
      wallets={[
        {
          id: 'wallet-1',
          name: 'Portfel rodzinny',
          accounts: [{ id: 'account-1', name: 'ROR PLN' }],
        },
      ]}
      realEstates={[
        {
          id: 'estate-1',
          walletId: 'wallet-1',
          name: 'Mieszkanie Warszawa',
          area_m2: '64.50',
          valueFmt: '600 000,00 PLN',
          purchaseCurrency: 'PLN',
        },
      ]}
      metals={[
        {
          id: 'metal-1',
          walletId: 'wallet-1',
          metal: 'GOLD',
          grams: '31.100000',
          valueFmt: '50 000,00 PLN',
        },
      ]}
    />,
  )
}

describe('InvestmentsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })

  it('updates a real estate display name and refreshes wallet data after success', async () => {
    await nextUiUnitStory('Wallet investments dialog updates real estate names', {
      severity: 'critical',
      tags: ['wallet', 'investments', 'real-estate', 'api-contract', 'next-ui'],
    })
    const requests: unknown[] = []
    server.use(
      http.put('*/api/wallet/real-estates/estate-1', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )

    renderDialog()

    const input = screen.getByDisplayValue('Mieszkanie Warszawa')
    fireEvent.change(input, { target: { value: 'Mieszkanie Mokotow' } })
    const row = screen.getByDisplayValue('Mieszkanie Mokotow').closest('tr')
    expect(row).not.toBeNull()
    fireEvent.click(within(row as HTMLTableRowElement).getAllByRole('button')[0]!)

    await waitFor(() => expect(requests).toEqual([{ name: 'Mieszkanie Mokotow' }]))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Zaktualizowano'))
    expect(routerRefresh).toHaveBeenCalled()
  })

  it('keeps a row-level error when real estate deletion is rejected', async () => {
    await nextUiUnitStory('Wallet investments dialog keeps row-level errors for rejected deletions', {
      severity: 'critical',
      tags: ['wallet', 'investments', 'real-estate', 'error-state', 'next-ui'],
    })
    server.use(
      http.delete('*/api/wallet/real-estates/estate-1', () =>
        HttpResponse.json({ error: 'Nieruchomość ma powiązaną sprzedaż' }, { status: 409 }),
      ),
    )

    renderDialog()

    const row = screen.getByDisplayValue('Mieszkanie Warszawa').closest('tr')
    expect(row).not.toBeNull()
    fireEvent.click(within(row as HTMLTableRowElement).getAllByRole('button')[0]!)
    fireEvent.click(within(row as HTMLTableRowElement).getAllByRole('button')[0]!)

    expect(await screen.findByText('Nieruchomość ma powiązaną sprzedaż')).toBeInTheDocument()
    expect(routerRefresh).not.toHaveBeenCalled()
  })

  it('sells part of a metal holding with an explicit cash account and transaction flag', async () => {
    await nextUiUnitStory('Wallet investments dialog submits metal sale financial state', {
      severity: 'critical',
      tags: ['wallet', 'investments', 'metals', 'money', 'api-contract', 'next-ui'],
    })
    const requests: unknown[] = []
    server.use(
      http.post('*/api/wallet/metal-holdings/metal-1/sell', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )

    renderDialog()

    const metalRow = screen.getByText('GOLD').closest('tr')
    expect(metalRow).not.toBeNull()
    fireEvent.click(within(metalRow as HTMLTableRowElement).getAllByRole('button')[1]!)
    fireEvent.change(screen.getByPlaceholderText('np. 10.0'), {
      target: { value: '10,5' },
    })
    fireEvent.change(screen.getByPlaceholderText('np. 3500'), {
      target: { value: '17000,25' },
    })
    fireEvent.click(screen.getByRole('checkbox', { name: /Utwórz transakcję bankową/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Sprzedaj' }))

    await waitFor(() => {
      expect(requests).toEqual([{
        deposit_account_id: 'account-1',
        grams_sold: '10.5',
        proceeds_amount: '17000.25',
        proceeds_currency: 'PLN',
        occurred_at: null,
        create_transaction: false,
      }])
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Metal sprzedany'))
    expect(routerRefresh).toHaveBeenCalled()
  })
})
