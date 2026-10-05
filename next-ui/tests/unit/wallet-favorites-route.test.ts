import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import { createFavoriteList, listFavoriteItemsWithAlerts, listFavoriteLists } from '@/lib/api/wallet'
import { GET, POST } from '@/app/api/wallet/favorites/route'

import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  createFavoriteList: vi.fn(),
  listFavoriteLists: vi.fn(),
  listFavoriteItemsWithAlerts: vi.fn(),
}))

describe('wallet favorites route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns whether a symbol belongs to any list without loading quote data', async () => {
    await nextUiUnitStory('Wallet favorites route returns report instrument favorite status', {
      severity: 'normal',
      tags: ['wallet', 'favorites', 'reports', 'api-route'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(listFavoriteLists).mockResolvedValue([
      { id: 'list-1', name: 'GPW', description: null },
      { id: 'list-2', name: 'Dywidendy', description: null },
    ])
    vi.mocked(listFavoriteItemsWithAlerts)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ symbol: 'PKO', name: 'PKO Bank Polski', mic: 'XWAR' }])

    const response = await GET(new NextRequest('http://localhost/api/wallet/favorites?symbol=pko'))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ isFavorite: true })
    expect(listFavoriteItemsWithAlerts).toHaveBeenNthCalledWith(1, 'user-1', 'list-1')
    expect(listFavoriteItemsWithAlerts).toHaveBeenNthCalledWith(2, 'user-1', 'list-2')
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
