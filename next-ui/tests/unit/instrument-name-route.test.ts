import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import { synchronizeInstrumentName } from '@/lib/api/wallet'
import { PUT } from '@/app/api/wallet/instruments/[symbol]/name/route'
import { nextUiUnitStory } from '../allure'


vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  synchronizeInstrumentName: vi.fn(),
}))


function request(body: unknown) {
  return new NextRequest('http://localhost/api/wallet/instruments/PKO/name', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}


function context(symbol = 'PKO') {
  return { params: Promise.resolve({ symbol }) }
}


describe('instrument name synchronization route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('rejects anonymous callers', async () => {
    await nextUiUnitStory('Instrument name route requires an authenticated session', {
      severity: 'blocker',
      tags: ['next-ui', 'wallet', 'instruments', 'auth', 'security'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('')

    const response = await PUT(request({ mic: 'XWAR', name: 'PKO BP SA' }), context())

    expect(response.status).toBe(401)
    expect(synchronizeInstrumentName).not.toHaveBeenCalled()
  })

  it('validates symbol, MIC and display name', async () => {
    await nextUiUnitStory('Instrument name route rejects malformed synchronization payloads', {
      severity: 'normal',
      tags: ['next-ui', 'wallet', 'instruments', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const invalidMic = await PUT(request({ mic: 'WAR', name: 'PKO BP SA' }), context())
    const invalidName = await PUT(request({ mic: 'XWAR', name: ' ' }), context())
    const invalidSymbol = await PUT(request({ mic: 'XWAR', name: 'PKO BP SA' }), context('X'.repeat(13)))

    expect(invalidMic.status).toBe(422)
    expect(invalidName.status).toBe(422)
    expect(invalidSymbol.status).toBe(422)
    expect(synchronizeInstrumentName).not.toHaveBeenCalled()
  })

  it('forwards normalized identifiers and returns the wallet response', async () => {
    await nextUiUnitStory('Instrument name route forwards canonical synchronization data', {
      severity: 'critical',
      tags: ['next-ui', 'wallet', 'stock', 'instruments', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(synchronizeInstrumentName).mockResolvedValue({
      ok: true,
      status: 200,
      data: { symbol: 'PKO', mic: 'XWAR', name: 'PKO BP SA', created: true },
    })

    const response = await PUT(request({ mic: 'xwar', name: '  PKO BP SA  ' }), context('pko'))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      symbol: 'PKO',
      mic: 'XWAR',
      name: 'PKO BP SA',
      created: true,
    })
    expect(synchronizeInstrumentName).toHaveBeenCalledWith(
      'user-1',
      'PKO',
      { mic: 'XWAR', name: 'PKO BP SA' },
    )
  })

  it('preserves controlled backend status and error text', async () => {
    await nextUiUnitStory('Instrument name route preserves synchronization conflict responses', {
      severity: 'critical',
      tags: ['next-ui', 'wallet', 'stock', 'instruments', 'api-contract'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(synchronizeInstrumentName).mockResolvedValue({
      ok: false,
      status: 409,
      error: 'Instrument shortname changed concurrently.',
    })

    const response = await PUT(request({ mic: 'XWAR', name: 'PKO BP SA' }), context())

    expect(response.status).toBe(409)
    await expect(response.json()).resolves.toEqual({
      error: 'Instrument shortname changed concurrently.',
    })
  })
})
