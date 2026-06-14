import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'

import { GoalsDialog, type GoalWalletOpt } from '@/features/wallet/components/GoalsDialog'
import { server } from '../msw-server'
import { nextUiUnitStory } from '../allure'

const refreshMock = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: refreshMock }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

const WALLET: GoalWalletOpt = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'FUNDUSZ Rodzinny',
}

describe('GoalsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    refreshMock.mockClear()
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('saves a new annual goal with the capital gain target as a separate field', async () => {
    await nextUiUnitStory('Wallet goals dialog saves capital gain target separately from revenue target', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'money', 'financial-data', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(http.post('*/api/wallet/goals', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({
        id: 'goal-1',
        wallet_id: WALLET.id,
        year: 2026,
        rev_target_year: '200000.00',
        exp_budget_year: '90000.00',
        capital_gain_target_year: '60000.00',
        currency: 'PLN',
      })
    }))

    render(
      <GoalsDialog
        open
        onOpenChange={vi.fn()}
        initialGoals={[]}
        wallets={[WALLET]}
        viewCurrency="PLN"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Dodaj/i }))
    await screen.findByText('Dodaj / zaktualizuj cel')
    fireEvent.change(screen.getByPlaceholderText('np. 120000'), { target: { value: '200000' } })
    fireEvent.change(screen.getByPlaceholderText('np. 80000'), { target: { value: '90000' } })
    fireEvent.change(screen.getByPlaceholderText('np. 24000'), { target: { value: '60000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => {
      expect(requests).toHaveLength(1)
    })
    await expect(requests[0]?.json()).resolves.toEqual({
      wallet_id: WALLET.id,
      year: new Date().getFullYear(),
      rev_target_year: '200000.00',
      exp_budget_year: '90000.00',
      capital_gain_target_year: '60000.00',
      currency: 'PLN',
    })
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Cel został zapisany')
      expect(refreshMock).toHaveBeenCalled()
    })
  })

  it('blocks negative capital gain targets before calling the API', async () => {
    await nextUiUnitStory('Wallet goals dialog rejects negative capital gain targets before API submission', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'validation', 'financial-data', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(http.post('*/api/wallet/goals', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({ ok: true })
    }))

    render(
      <GoalsDialog
        open
        onOpenChange={vi.fn()}
        initialGoals={[]}
        wallets={[WALLET]}
        viewCurrency="PLN"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Dodaj/i }))
    await screen.findByText('Dodaj / zaktualizuj cel')
    fireEvent.change(screen.getByPlaceholderText('np. 120000'), { target: { value: '200000' } })
    fireEvent.change(screen.getByPlaceholderText('np. 80000'), { target: { value: '90000' } })
    fireEvent.change(screen.getByPlaceholderText('np. 24000'), { target: { value: '-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByText('Cel zysku kapitałowego musi być liczbą ≥ 0')).toBeInTheDocument()
    expect(requests).toHaveLength(0)
    expect(refreshMock).not.toHaveBeenCalled()
  })

  it('validates edited annual goal capital gain targets before updating an existing row', async () => {
    await nextUiUnitStory('Wallet goals dialog validates edited capital gain targets on existing annual goals', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'validation', 'financial-data', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(http.post('*/api/wallet/goals', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({ ok: true })
    }))

    render(
      <GoalsDialog
        open
        onOpenChange={vi.fn()}
        initialGoals={[
          {
            id: 'goal-1',
            wallet_id: WALLET.id,
            year: 2026,
            rev_target_year: '200000.00',
            exp_budget_year: '90000.00',
            capital_gain_target_year: '5000.00',
            currency: 'PLN',
          },
        ]}
        wallets={[WALLET]}
        viewCurrency="PLN"
      />,
    )

    const row = screen.getByText(WALLET.name).closest('tr')
    expect(row).not.toBeNull()
    const scope = within(row!)
    fireEvent.change(scope.getByDisplayValue('5000.00'), { target: { value: '-1' } })
    fireEvent.click(scope.getAllByRole('button')[0]!)

    expect(await screen.findByText('Cel zysku kapitałowego musi być ≥ 0')).toBeInTheDocument()
    expect(requests).toHaveLength(0)
    expect(refreshMock).not.toHaveBeenCalled()
  })

  it('updates an existing annual goal with the edited capital gain target', async () => {
    await nextUiUnitStory('Wallet goals dialog submits edited capital gain targets for existing annual goals', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'money', 'financial-data', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(http.post('*/api/wallet/goals', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({ ok: true })
    }))

    render(
      <GoalsDialog
        open
        onOpenChange={vi.fn()}
        initialGoals={[
          {
            id: 'goal-1',
            wallet_id: WALLET.id,
            year: 2026,
            rev_target_year: '200000.00',
            exp_budget_year: '90000.00',
            capital_gain_target_year: '5000.00',
            currency: 'PLN',
          },
        ]}
        wallets={[WALLET]}
        viewCurrency="PLN"
      />,
    )

    const row = screen.getByText(WALLET.name).closest('tr')
    expect(row).not.toBeNull()
    const scope = within(row!)
    fireEvent.change(scope.getByDisplayValue('5000.00'), { target: { value: '60000' } })
    fireEvent.click(scope.getAllByRole('button')[0]!)

    await waitFor(() => {
      expect(requests).toHaveLength(1)
    })
    await expect(requests[0]?.json()).resolves.toEqual({
      wallet_id: WALLET.id,
      year: 2026,
      rev_target_year: '200000.00',
      exp_budget_year: '90000.00',
      capital_gain_target_year: '60000.00',
      currency: 'PLN',
    })
    expect(refreshMock).toHaveBeenCalled()
  })
})
