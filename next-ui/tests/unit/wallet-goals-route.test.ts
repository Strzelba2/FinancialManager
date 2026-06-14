import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import { upsertWalletGoal } from '@/lib/api/wallet'
import { POST } from '@/app/api/wallet/goals/route'
import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  upsertWalletGoal: vi.fn(),
}))

function jsonRequest(body: unknown) {
  return new NextRequest('http://localhost/api/wallet/goals', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('wallet goals route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('forwards annual goals with the separate capital gain target', async () => {
    await nextUiUnitStory('Wallet goals route forwards capital gain targets to the wallet service', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'api-route', 'financial-data'],
    })
    const goal = {
      id: 'goal-1',
      wallet_id: '11111111-1111-4111-8111-111111111111',
      year: 2026,
      rev_target_year: '200000.00',
      exp_budget_year: '90000.00',
      capital_gain_target_year: '60000.00',
      currency: 'PLN' as const,
    }
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(upsertWalletGoal).mockResolvedValue({
      ok: true,
      data: goal,
      status: 200,
    })

    const response = await POST(jsonRequest({
      wallet_id: goal.wallet_id,
      year: goal.year,
      rev_target_year: ' 200000.00 ',
      exp_budget_year: ' 90000.00 ',
      capital_gain_target_year: ' 60000.00 ',
      currency: goal.currency,
    }))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual(goal)
    expect(upsertWalletGoal).toHaveBeenCalledWith('user-1', {
      wallet_id: goal.wallet_id,
      year: 2026,
      rev_target_year: '200000.00',
      exp_budget_year: '90000.00',
      capital_gain_target_year: '60000.00',
      currency: 'PLN',
    })
  })

  it('defaults a missing capital gain target to zero for backward-compatible callers', async () => {
    await nextUiUnitStory('Wallet goals route defaults missing capital gain targets to zero', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'api-route', 'compatibility'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(upsertWalletGoal).mockResolvedValue({
      ok: true,
      data: {
        id: 'goal-2',
        wallet_id: '11111111-1111-4111-8111-111111111111',
        year: 2026,
        rev_target_year: '200000.00',
        exp_budget_year: '90000.00',
        capital_gain_target_year: '0.00',
        currency: 'PLN',
      },
      status: 200,
    })

    const response = await POST(jsonRequest({
      wallet_id: '11111111-1111-4111-8111-111111111111',
      year: 2026,
      rev_target_year: '200000.00',
      exp_budget_year: '90000.00',
      currency: 'PLN',
    }))

    expect(response.status).toBe(200)
    expect(upsertWalletGoal).toHaveBeenCalledWith('user-1', expect.objectContaining({
      capital_gain_target_year: '0.00',
    }))
  })

  it('requires authentication before sending goals to the wallet service', async () => {
    await nextUiUnitStory('Wallet goals route rejects unauthenticated goal writes', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'api-route', 'auth'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('')

    const response = await POST(jsonRequest({
      wallet_id: '11111111-1111-4111-8111-111111111111',
      year: 2026,
      rev_target_year: '200000.00',
      exp_budget_year: '90000.00',
      capital_gain_target_year: '60000.00',
      currency: 'PLN',
    }))

    expect(response.status).toBe(401)
    expect(upsertWalletGoal).not.toHaveBeenCalled()
  })
})
