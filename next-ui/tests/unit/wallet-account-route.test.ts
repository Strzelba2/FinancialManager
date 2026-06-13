import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import { createAccount, deleteBrokerageAccount, ensureBrokerageCashLinks } from '@/lib/api/wallet'
import { POST as postCreateAccount } from '@/app/api/wallet/account/create/route'
import { POST as postEnsureCashLinks } from '@/app/api/wallet/brokerage/cash-links/ensure/route'
import { DELETE as deleteBrokerageAccountRoute } from '@/app/api/wallet/brokerage/accounts/[id]/route'
import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  createAccount: vi.fn(),
  deleteBrokerageAccount: vi.fn(),
  ensureBrokerageCashLinks: vi.fn(),
}))

function jsonRequest(url: string, body: unknown) {
  return new NextRequest(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function emptyRequest(url: string, method: string) {
  return new NextRequest(url, { method })
}

describe('wallet account route handlers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('preserves brokerage USD and EUR cash subaccounts on account creation', async () => {
    await nextUiUnitStory('Wallet account route preserves brokerage cash subaccounts', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'account-create', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createAccount).mockResolvedValue({
      ok: true,
      data: { id: 'account-1', name: 'Bossa IKE', account_type: 'BROKERAGE', currency: 'PLN' },
      status: 201,
    })

    const payload = {
      walletId: '11111111-1111-4111-8111-111111111111',
      name: 'Bossa IKE',
      account_type: 'BROKERAGE',
      currency: 'PLN',
      account_number: 'BOSSA-IKE-PLN',
      bank_id: '22222222-2222-4222-8222-222222222222',
      brokerage_cash_accounts: [
        { currency: 'USD', account_number: 'BOSSA-IKE-USD', name: 'Bossa IKE · USD' },
        { currency: 'EUR', account_number: 'BOSSA-IKE-EUR', name: 'Bossa IKE · EUR' },
      ],
    }

    const response = await postCreateAccount(jsonRequest('http://localhost/api/wallet/account/create', payload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ success: true, accountName: 'Bossa IKE' })
    const forwardedPayload = vi.mocked(createAccount).mock.calls[0]?.[2]
    expect(createAccount).toHaveBeenCalledWith('user-1', payload.walletId, {
      name: 'Bossa IKE',
      account_type: 'BROKERAGE',
      currency: 'PLN',
      account_number: 'BOSSA-IKE-PLN',
      bank_id: payload.bank_id,
      brokerage_cash_accounts: payload.brokerage_cash_accounts,
    })
    expect(forwardedPayload).not.toHaveProperty('iban')
  })

  it('forwards existing brokerage cash-link requests with account identifiers', async () => {
    await nextUiUnitStory('Wallet account route forwards brokerage cash-link requests', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'cash-links', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(ensureBrokerageCashLinks).mockResolvedValue({
      ok: true,
      data: [{ currency: 'USD', deposit_account_id: 'cash-1', created: true }],
      status: 200,
    })

    const payload = {
      brokerage_account_id: '33333333-3333-4333-8333-333333333333',
      cash_accounts: [
        { currency: 'USD', account_number: 'BOSSA-IKE-USD', name: 'Bossa IKE · USD' },
      ],
    }

    const response = await postEnsureCashLinks(jsonRequest('http://localhost/api/wallet/brokerage/cash-links/ensure', payload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual([{ currency: 'USD', deposit_account_id: 'cash-1', created: true }])
    expect(ensureBrokerageCashLinks).toHaveBeenCalledWith(
      'user-1',
      payload.brokerage_account_id,
      { cash_accounts: payload.cash_accounts },
    )
  })

  it('deletes brokerage accounts through an authenticated wallet route', async () => {
    await nextUiUnitStory('Wallet account route deletes brokerage accounts through wallet ownership checks', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'account-delete', 'api-route', 'ownership'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(deleteBrokerageAccount).mockResolvedValue(true)

    const response = await deleteBrokerageAccountRoute(
      emptyRequest('http://localhost/api/wallet/brokerage/accounts/33333333-3333-4333-8333-333333333333', 'DELETE'),
      { params: Promise.resolve({ id: '33333333-3333-4333-8333-333333333333' }) },
    )

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ ok: true })
    expect(deleteBrokerageAccount).toHaveBeenCalledWith('user-1', '33333333-3333-4333-8333-333333333333')
  })
})
