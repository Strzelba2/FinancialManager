import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import {
  batchUpdateTransactions,
  createTransactions,
  deleteTransaction,
  listTransactions,
} from '@/lib/api/wallet'
import { GET, PATCH, POST } from '@/app/api/wallet/transactions/route'
import { DELETE } from '@/app/api/wallet/transactions/[id]/route'

import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  createTransactions: vi.fn(),
  listTransactions: vi.fn(),
  batchUpdateTransactions: vi.fn(),
  deleteTransaction: vi.fn(),
}))

function jsonRequest(url: string, body: unknown, method = 'POST') {
  return new NextRequest(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('wallet transactions route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('rejects anonymous transaction route calls', async () => {
    await nextUiUnitStory('Wallet transactions route rejects anonymous callers', {
      severity: 'blocker',
      tags: ['wallet', 'transactions', 'api-route', 'auth', 'security'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('')

    const response = await POST(jsonRequest('http://localhost/api/wallet/transactions', {
      account_id: '11111111-1111-4111-8111-111111111111',
      transactions: [],
    }))

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ error: 'Not authenticated' })
    expect(createTransactions).not.toHaveBeenCalled()
  })

  it('keeps create payloads focused on financial transaction fields', async () => {
    await nextUiUnitStory('Wallet transactions route excludes edit-only category and status fields from create payloads', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createTransactions).mockResolvedValue({
      ok: true,
      data: { created: 1 },
      status: 201,
    })

    const payload = {
      account_id: '11111111-1111-4111-8111-111111111111',
      transactions: [
        {
          date: '2026-05-01T09:00:00.000Z',
          amount: '100.00',
          description: 'Salary',
          amount_after: '100.00',
          category: 'OTHER',
          status: 'INCOME',
          capital_gain_kind: null,
        },
      ],
    }
    const expectedPayload = {
      account_id: payload.account_id,
      transactions: [
        {
          date: '2026-05-01T09:00:00.000Z',
          amount: '100.00',
          description: 'Salary',
          amount_after: '100.00',
          capital_gain_kind: null,
        },
      ],
    }

    const response = await POST(jsonRequest('http://localhost/api/wallet/transactions', payload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ success: true, summary: { created: 1 } })
    expect(createTransactions).toHaveBeenCalledWith('user-1', expectedPayload)
  })

  it('maps create validation errors before calling wallet service', async () => {
    await nextUiUnitStory('Wallet transactions route validates create payloads', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-route', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const response = await POST(jsonRequest('http://localhost/api/wallet/transactions', {
      account_id: 'not-a-uuid',
      transactions: [],
    }))

    expect(response.status).toBe(422)
    expect(createTransactions).not.toHaveBeenCalled()
  })

  it('forwards list filters to the wallet service', async () => {
    await nextUiUnitStory('Wallet transactions route forwards list filters', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-route', 'filters'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(listTransactions).mockResolvedValue({
      ok: true,
      data: { items: [], total: 0, page: 2, size: 20, sum_by_ccy: {} },
      status: 200,
    })

    const response = await GET(new NextRequest(
      'http://localhost/api/wallet/transactions?page=2&size=20&account_id=acc-1&account_id=acc-2&category=FOOD&status=EXPENSE&date_from=2026-05-01&date_to=2026-05-31&q=grocery',
    ))

    expect(response.status).toBe(200)
    expect(listTransactions).toHaveBeenCalledWith('user-1', {
      page: 2,
      size: 20,
      account_id: ['acc-1', 'acc-2'],
      category: ['FOOD'],
      status: ['EXPENSE'],
      date_from: '2026-05-01',
      date_to: '2026-05-31',
      q: 'grocery',
    })
  })

  it('preserves category/status updates and null clearing in batch patch payloads', async () => {
    await nextUiUnitStory('Wallet transactions route preserves category and status batch updates', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(batchUpdateTransactions).mockResolvedValue({
      ok: true,
      data: { updated: 2, failed: [] },
      status: 200,
    })

    const payload = {
      items: [
        {
          id: '11111111-1111-4111-8111-111111111111',
          description: 'Updated',
          category: 'FOOD',
          status: 'EXPENSE',
        },
        {
          id: '22222222-2222-4222-8222-222222222222',
          category: null,
          status: null,
        },
      ],
    }
    const response = await PATCH(jsonRequest('http://localhost/api/wallet/transactions', payload, 'PATCH'))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ updated: 2, failed: [] })
    expect(batchUpdateTransactions).toHaveBeenCalledWith('user-1', payload.items)
  })

  it('rejects financial balance-chain changes in batch patch payloads', async () => {
    await nextUiUnitStory('Wallet transactions route rejects financial fields in classification patches', {
      severity: 'blocker',
      tags: ['wallet', 'transactions', 'api-route', 'financial-data', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const response = await PATCH(jsonRequest('http://localhost/api/wallet/transactions', {
      items: [
        {
          id: '11111111-1111-4111-8111-111111111111',
          amount: '-100.00',
          balance_before: '0.00',
          balance_after: '-100.00',
        },
      ],
    }, 'PATCH'))

    expect(response.status).toBe(422)
    expect(batchUpdateTransactions).not.toHaveBeenCalled()
  })

  it('propagates backend error status and message when list transactions fails', async () => {
    await nextUiUnitStory('Wallet transactions route propagates backend error on list failure', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-route', 'error-state'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(listTransactions).mockResolvedValue({
      ok: false,
      status: 502,
      error: 'Upstream service unavailable',
    })

    const response = await GET(new NextRequest('http://localhost/api/wallet/transactions'))

    expect(response.status).toBe(502)
    await expect(response.json()).resolves.toEqual({ error: 'Upstream service unavailable' })
    expect(listTransactions).toHaveBeenCalledWith('user-1', expect.objectContaining({ page: 1, size: 40 }))
  })

  it('maps delete failures and successes for transaction rows', async () => {
    await nextUiUnitStory('Wallet transactions route maps delete result for transaction rows', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(deleteTransaction).mockResolvedValueOnce(false).mockResolvedValueOnce(true)

    const failed = await DELETE(
      new NextRequest('http://localhost/api/wallet/transactions/tx-1', { method: 'DELETE' }),
      { params: Promise.resolve({ id: 'tx-1' }) },
    )
    const deleted = await DELETE(
      new NextRequest('http://localhost/api/wallet/transactions/tx-2', { method: 'DELETE' }),
      { params: Promise.resolve({ id: 'tx-2' }) },
    )

    expect(failed.status).toBe(400)
    await expect(failed.json()).resolves.toEqual({ error: 'Nie udało się usunąć transakcji' })
    expect(deleted.status).toBe(200)
    await expect(deleted.json()).resolves.toEqual({ success: true })
    expect(deleteTransaction).toHaveBeenNthCalledWith(1, 'user-1', 'tx-1')
    expect(deleteTransaction).toHaveBeenNthCalledWith(2, 'user-1', 'tx-2')
  })
})
