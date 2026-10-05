import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import { createCashHolding, deleteCashHolding, updateCashHolding } from '@/lib/api/wallet'
import { POST as postCashHolding } from '@/app/api/wallet/cash-holdings/route'
import { DELETE as deleteCashHoldingRoute, PUT as putCashHolding } from '@/app/api/wallet/cash-holdings/[id]/route'
import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  createCashHolding: vi.fn(),
  updateCashHolding: vi.fn(),
  deleteCashHolding: vi.fn(),
}))

function jsonRequest(url: string, body: unknown, method = 'POST') {
  return new NextRequest(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function params(id: string) {
  return { params: Promise.resolve({ id }) }
}

const cashPayload = {
  wallet_id: '11111111-1111-4111-8111-111111111111',
  name: '  Sejf  ',
  amount: '1500.50',
  currency: 'GBP',
  note: '  koperta  ',
}

describe('wallet cash holdings route handlers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('validates and trims cash create payloads, accepting GBP', async () => {
    await nextUiUnitStory('Wallet cash route validates and trims create payloads', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'api-route', 'money'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createCashHolding).mockResolvedValue({ ok: true, data: { id: 'cash-1' }, status: 200 })

    const response = await postCashHolding(jsonRequest('http://localhost/api/wallet/cash-holdings', cashPayload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ success: true })
    expect(createCashHolding).toHaveBeenCalledWith('user-1', {
      ...cashPayload,
      name: 'Sejf',
      note: 'koperta',
    })
  })

  it.each([
    ['negative amount', { amount: '-10' }],
    ['comma decimal', { amount: '10,50' }],
    ['empty name', { name: '   ' }],
    ['unsupported currency', { currency: 'JPY' }],
  ])('rejects %s before calling wallet service', async (_label, override) => {
    await nextUiUnitStory('Wallet cash route rejects invalid create payloads', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'api-route', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const response = await postCashHolding(
      jsonRequest('http://localhost/api/wallet/cash-holdings', { ...cashPayload, ...override }),
    )

    expect(response.status).toBe(422)
    expect(createCashHolding).not.toHaveBeenCalled()
  })

  it('rejects unauthenticated requests', async () => {
    await nextUiUnitStory('Wallet cash route requires an authenticated wallet user', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'api-route', 'auth'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('')

    const response = await postCashHolding(jsonRequest('http://localhost/api/wallet/cash-holdings', cashPayload))

    expect(response.status).toBe(401)
    expect(createCashHolding).not.toHaveBeenCalled()
  })

  it('forwards a cash update with an empty note so the note can be cleared', async () => {
    await nextUiUnitStory('Wallet cash route forwards updates', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'api-route', 'money'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(updateCashHolding).mockResolvedValue({ ok: true, data: {}, status: 200 })

    const response = await putCashHolding(
      jsonRequest(
        'http://localhost/api/wallet/cash-holdings/cash-1',
        { name: 'Sejf', amount: '0', currency: 'CHF', note: '' },
        'PUT',
      ),
      params('cash-1'),
    )

    expect(response.status).toBe(200)
    expect(updateCashHolding).toHaveBeenCalledWith('user-1', 'cash-1', {
      name: 'Sejf',
      amount: '0',
      currency: 'CHF',
      note: '',
    })
  })

  it('maps backend update errors and delete failures to the dialog error contract', async () => {
    await nextUiUnitStory('Wallet cash route maps update and delete failures', {
      severity: 'critical',
      tags: ['wallet', 'cash', 'api-route', 'error-state'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(updateCashHolding).mockResolvedValue({ ok: false, error: 'Cash holding not found', status: 404 })
    vi.mocked(deleteCashHolding).mockResolvedValue(false)

    const updateResponse = await putCashHolding(
      jsonRequest(
        'http://localhost/api/wallet/cash-holdings/cash-1',
        { name: 'Sejf', amount: '10', currency: 'PLN', note: '' },
        'PUT',
      ),
      params('cash-1'),
    )
    const deleteResponse = await deleteCashHoldingRoute(
      new NextRequest('http://localhost/api/wallet/cash-holdings/cash-1', { method: 'DELETE' }),
      params('cash-1'),
    )

    expect(updateResponse.status).toBe(400)
    await expect(updateResponse.json()).resolves.toEqual({ error: 'Cash holding not found' })
    expect(deleteResponse.status).toBe(400)
    await expect(deleteResponse.json()).resolves.toEqual({ error: 'Nie udało się usunąć pozycji gotówki' })
  })
})
