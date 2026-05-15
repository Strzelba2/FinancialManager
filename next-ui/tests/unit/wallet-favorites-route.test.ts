import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import { createFavoriteList } from '@/lib/api/wallet'
import { POST } from '@/app/api/wallet/favorites/route'

import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  createFavoriteList: vi.fn(),
  listFavoriteLists: vi.fn(),
}))

describe('wallet favorites route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns duplicate-list conflict status and message to the UI route caller', async () => {
    await nextUiUnitStory('Wallet favorites route returns duplicate-list conflict message', {
      severity: 'critical',
      tags: ['wallet', 'favorites', 'api-route', 'validation'],
    })
    const message = 'Favorite list with this name already exists for this user.'
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createFavoriteList).mockResolvedValue({
      ok: false,
      error: message,
      status: 409,
    })

    const response = await POST(new NextRequest('http://localhost/api/wallet/favorites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: '  My watchlist  ', description: null }),
    }))

    expect(response.status).toBe(409)
    await expect(response.json()).resolves.toEqual({ error: message })
    expect(createFavoriteList).toHaveBeenCalledWith('user-1', {
      name: 'My watchlist',
      description: null,
    })
  })
})
