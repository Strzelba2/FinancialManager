import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import { CreateAccountDialog } from '@/features/wallet/components/CreateAccountDialog'
import { nextUiUnitStory } from '../allure'

const routerRefresh = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: routerRefresh }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

const wallets = [
  { id: 'wallet-1', name: 'FUNDUSZ Rodzinny' },
  { id: 'wallet-2', name: 'IKE' },
]

const banks = [
  { id: 'bank-ing', name: 'ING Bank Slaski', shortname: 'ING' },
  { id: 'bank-bossa', name: 'Dom Maklerski BOSSA', shortname: 'BOSSA' },
]

function renderDialog(props: Partial<Parameters<typeof CreateAccountDialog>[0]> = {}) {
  return render(
    <CreateAccountDialog
      open
      onOpenChange={vi.fn()}
      wallets={wallets}
      banks={banks}
      {...props}
    />,
  )
}

async function chooseOption(triggerIndex: number, name: RegExp | string) {
  fireEvent.click(screen.getAllByRole('combobox')[triggerIndex]!)
  fireEvent.click(await screen.findByRole('option', { name }))
}

describe('CreateAccountDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routerRefresh.mockClear()
    server.resetHandlers()
    Element.prototype.scrollIntoView = vi.fn()
  })
  it('validates required fields before sending an account create request', async () => {
    await nextUiUnitStory('Wallet account dialog validates required fields before submit', {
      severity: 'critical',
      tags: ['wallet', 'account', 'validation', 'next-ui'],
    })

    const requests: Request[] = []
    server.use(
      http.post('*/api/wallet/account/create', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ success: true, accountName: 'unused' })
      }),
    )

    renderDialog()

    fireEvent.click(screen.getByRole('button', { name: 'Dodaj konto' }))
    expect(screen.getByText('Podaj nazwę konta')).toBeInTheDocument()
    expect(requests).toHaveLength(0)

    fireEvent.change(screen.getByLabelText(/Nazwa konta/i), { target: { value: 'Makler BOSSA' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj konto' }))
    expect(screen.getByText('Podaj numer konta')).toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })

  it('creates a standard deposit account without brokerage cash subaccounts', async () => {
    await nextUiUnitStory('Wallet account dialog sends a standard deposit account payload', {
      severity: 'critical',
      tags: ['wallet', 'account', 'api-contract', 'next-ui'],
    })

    const requests: Request[] = []
    server.use(
      http.post('*/api/wallet/account/create', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ success: true, accountName: 'ROR ING' })
      }),
    )
    const onOpenChange = vi.fn()

    renderDialog({ onOpenChange })
    fireEvent.change(screen.getByLabelText(/Nazwa konta/i), { target: { value: 'ROR ING' } })
    fireEvent.change(screen.getByLabelText(/Numer konta/i), {
      target: { value: '12345678901234567890123456' },
    })
    await chooseOption(3, 'ING')

    fireEvent.click(screen.getByRole('button', { name: 'Dodaj konto' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    await expect(requests[0]?.json()).resolves.toEqual({
      walletId: 'wallet-1',
      name: 'ROR ING',
      account_type: 'CURRENT',
      currency: 'PLN',
      account_number: '12345678901234567890123456',
      bank_id: 'bank-ing',
    })
    expect(toast.success).toHaveBeenCalledWith('Konto „ROR ING" zostało dodane')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(routerRefresh).toHaveBeenCalled()
  })

  it('creates a brokerage account with optional USD and EUR cash subaccounts', async () => {
    await nextUiUnitStory('Wallet account dialog sends brokerage cash subaccounts during account creation', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'cash-subaccounts', 'api-contract', 'next-ui'],
    })

    const requests: Request[] = []
    server.use(
      http.post('*/api/wallet/account/create', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ success: true, accountName: 'BOSSA IKE' })
      }),
    )

    renderDialog()
    await chooseOption(0, 'Konto maklerskie')
    fireEvent.change(screen.getByLabelText(/Nazwa konta/i), { target: { value: 'BOSSA IKE' } })
    fireEvent.change(screen.getByLabelText(/Numer konta/i), {
      target: { value: 'BOSSA-IKE-PLN-ARTUR' },
    })
    await chooseOption(3, 'BOSSA')
    fireEvent.change(screen.getByLabelText(/Subkonto USD/i), {
      target: { value: 'BOSSA-IKE-USD-ARTUR' },
    })
    fireEvent.change(screen.getByLabelText(/Subkonto EUR/i), {
      target: { value: 'BOSSA-IKE-EUR-ARTUR' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Dodaj konto' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    await expect(requests[0]?.json()).resolves.toEqual({
      walletId: 'wallet-1',
      name: 'BOSSA IKE',
      account_type: 'BROKERAGE',
      currency: 'PLN',
      account_number: 'BOSSA-IKE-PLN-ARTUR',
      bank_id: 'bank-bossa',
      brokerage_cash_accounts: [
        {
          currency: 'USD',
          account_number: 'BOSSA-IKE-USD-ARTUR',
          name: 'BOSSA IKE · USD',
        },
        {
          currency: 'EUR',
          account_number: 'BOSSA-IKE-EUR-ARTUR',
          name: 'BOSSA IKE · EUR',
        },
      ],
    })
  })

  it('keeps the dialog open and displays backend validation errors', async () => {
    await nextUiUnitStory('Wallet account dialog shows backend create-account validation errors', {
      severity: 'critical',
      tags: ['wallet', 'account', 'error-state', 'api-contract', 'next-ui'],
    })

    server.use(
      http.post('*/api/wallet/account/create', () => (
        HttpResponse.json({ error: 'Value error, invalid IBAN' }, { status: 400 })
      )),
    )
    const onOpenChange = vi.fn()

    renderDialog({ onOpenChange })
    fireEvent.change(screen.getByLabelText(/Nazwa konta/i), { target: { value: 'Subkonto USD' } })
    fireEvent.change(screen.getByLabelText(/Numer konta/i), {
      target: { value: 'BOSSA-IKE-USD-ARTUR' },
    })
    await chooseOption(3, 'BOSSA')

    fireEvent.click(screen.getByRole('button', { name: 'Dodaj konto' }))

    expect(await screen.findByText('Value error, invalid IBAN')).toBeInTheDocument()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
    expect(routerRefresh).not.toHaveBeenCalled()
  })

  it('blocks submit when no wallet is available', async () => {
    await nextUiUnitStory('Wallet account dialog disables submit when no wallet exists', {
      severity: 'normal',
      tags: ['wallet', 'account', 'empty-state', 'next-ui'],
    })

    renderDialog({ wallets: [] })

    expect(screen.getByText('Najpierw dodaj portfel, a potem konto.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dodaj konto' })).toBeDisabled()
  })
})
