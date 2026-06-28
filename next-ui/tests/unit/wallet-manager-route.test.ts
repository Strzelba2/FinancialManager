import { NextRequest } from 'next/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'

import { server } from '../msw-server'
import { nextUiUnitStory } from '../allure'

const resolveWalletUserIdMock = vi.hoisted(() => vi.fn())
const getFxRatesMock = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: resolveWalletUserIdMock,
}))

vi.mock('@/lib/api/nbp', () => ({
  getFxRates: getFxRatesMock,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

function jsonRequest(body: unknown = {}) {
  return new NextRequest('http://localhost/api/wallet/manager', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

async function loadPostRoute() {
  vi.resetModules()
  vi.stubEnv('WALLET_API_URL', 'http://wallet.test')
  const route = await import('@/app/api/wallet/manager/route')
  return route.POST
}

describe('wallet manager route', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-15T10:00:00Z'))
    server.resetHandlers()
    resolveWalletUserIdMock.mockReset()
    getFxRatesMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllEnvs()
  })

  it('requires authentication before creating a snapshot', async () => {
    await nextUiUnitStory('Wallet manager route rejects unauthenticated snapshot creation', {
      severity: 'critical',
      tags: ['wallet', 'wallet-manager', 'api-route', 'auth'],
    })
    const POST = await loadPostRoute()
    resolveWalletUserIdMock.mockResolvedValue('')

    const response = await POST(jsonRequest())

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ error: 'Unauthorized' })
    expect(getFxRatesMock).not.toHaveBeenCalled()
  })

  it('forwards month key and FX rates to the wallet monthly snapshot endpoint', async () => {
    await nextUiUnitStory('Wallet manager route forwards snapshot month and FX rates to wallet service', {
      severity: 'critical',
      tags: ['wallet', 'wallet-manager', 'snapshots', 'fx', 'api-route'],
    })
    const POST = await loadPostRoute()
    resolveWalletUserIdMock.mockResolvedValue('user-1')
    getFxRatesMock.mockResolvedValue({
      'USD/PLN': 4,
      'EUR/PLN': 4.5,
    })
    let capturedBody: unknown = null
    let capturedUserId: string | null = null
    server.use(
      http.post('http://wallet.test/wallet/snapshots/monthly', async ({ request }) => {
        capturedBody = await request.json()
        capturedUserId = request.headers.get('X-User-Id')
        return HttpResponse.json({ ok: true, month_key: '2026-06' })
      }),
    )

    const response = await POST(jsonRequest())

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ ok: true, month_key: '2026-06' })
    expect(capturedUserId).toBe('user-1')
    expect(capturedBody).toEqual({
      month_key: '2026-06',
      currency_rate: {
        'USD/PLN': '4',
        'EUR/PLN': '4.5',
      },
    })
  })

  it('returns a controlled error when the wallet service rejects snapshot creation', async () => {
    await nextUiUnitStory('Wallet manager route returns controlled wallet-service errors', {
      severity: 'critical',
      tags: ['wallet', 'wallet-manager', 'snapshots', 'api-route', 'error-state'],
    })
    const POST = await loadPostRoute()
    resolveWalletUserIdMock.mockResolvedValue('user-1')
    getFxRatesMock.mockResolvedValue({})
    server.use(
      http.post('http://wallet.test/wallet/snapshots/monthly', () => {
        return HttpResponse.text('service unavailable', { status: 503 })
      }),
    )

    const response = await POST(jsonRequest())

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({ error: 'Błąd serwera (503)' })
  })
})
