import { afterEach, describe, expect, it, vi } from 'vitest'

import { nextUiUnitStory } from '../allure'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('wallet API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
    delete process.env.WALLET_API_URL
  })

  it('creates a wallet with the internal user header', async () => {
    await nextUiUnitStory('Wallet API client creates wallets with user identity header', {
      severity: 'critical',
      tags: ['wallet', 'api-client', 'financial-data'],
    })
    const fetchMock = vi.fn(async () => jsonResponse({ id: 'wallet-1', name: 'Main' }))
    vi.stubGlobal('fetch', fetchMock)
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { createWallet } = await import('@/lib/api/wallet')

    const result = await createWallet('Main', 'user-1')

    expect(result).toEqual({ id: 'wallet-1', name: 'Main' })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://wallet:8001/wallet/create/wallet',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'Main' }),
        cache: 'no-store',
        headers: expect.objectContaining({
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-User-Id': 'user-1',
        }),
      }),
    )
  })

  it('extracts FastAPI validation messages from account creation errors', async () => {
    await nextUiUnitStory('Wallet API client extracts FastAPI validation error messages', {
      severity: 'critical',
      tags: ['wallet', 'api-client', 'validation'],
    })
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: [{ msg: 'Field required' }] }, 422)))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { createAccount } = await import('@/lib/api/wallet')

    const result = await createAccount('user-1', 'wallet-1', {
      name: '',
      account_type: 'CURRENT',
      currency: 'PLN',
      account_number: '',
      bank_id: 'bank-1',
      iban: '',
    })

    expect(result).toEqual({ ok: false, error: 'Field required', status: 422 })
  })

  it('preserves favorite-list duplicate conflict messages from wallet service', async () => {
    await nextUiUnitStory('Wallet API client preserves favorite-list duplicate conflicts', {
      severity: 'critical',
      tags: ['wallet', 'favorites', 'api-client', 'validation'],
    })
    const message = 'Favorite list with this name already exists for this user.'
    const fetchMock = vi.fn(async () => jsonResponse({ detail: message }, 409))
    vi.stubGlobal('fetch', fetchMock)
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { createFavoriteList } = await import('@/lib/api/wallet')

    const result = await createFavoriteList('user-1', {
      name: 'My watchlist',
      description: 'Tracked instruments',
    })

    expect(result).toEqual({ ok: false, error: message, status: 409 })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://wallet:8001/users/favorites/lists',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'My watchlist',
          description: 'Tracked instruments',
        }),
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-User-Id': 'user-1',
        }),
      }),
    )
  })

  it('returns safe defaults when wallet service is unavailable', async () => {
    await nextUiUnitStory('Wallet API client returns safe defaults on service outage', {
      severity: 'critical',
      tags: ['wallet', 'api-client', 'error-state'],
    })
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network down') }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { listFavoriteLists, deleteWallet } = await import('@/lib/api/wallet')

    await expect(listFavoriteLists('user-1')).resolves.toEqual([])
    await expect(deleteWallet('user-1', 'wallet-1')).resolves.toBe(false)
  })
})

describe('stock API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
    delete process.env.STOCK_API_URL
  })

  it('normalizes bulk quote display values returned from stock service', async () => {
    await nextUiUnitStory('Stock API client normalizes quote display values', {
      severity: 'normal',
      tags: ['stock', 'api-client', 'reports'],
    })
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      PKO: {
        name: 'PKO BP',
        last_price: '55.12',
        change_pct: '1.2',
        volume: 1000,
        last_trade_at: '2026-05-13T10:00:00',
      },
    })))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getQuotesBulkResult, processQuotes } = await import('@/lib/api/stock')

    const result = await getQuotesBulkResult('XWAR')

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error(result.error)
    expect(result.status).toBe(200)
    const quote = result.data.PKO
    expect(quote).toBeDefined()
    if (!quote) throw new Error('PKO quote was not returned')
    expect(quote.last_price_fmt).toBe('55,12')
    expect(quote.change_pct_fmt).toBe('+1,20%')
    expect(processQuotes(result.data)).toEqual([
      expect.objectContaining({
        symbol: 'PKO',
        name: 'PKO BP',
        lastPrice: 55.12,
        changePct: 1.2,
        volume: 1000,
      }),
    ])
  })

  it('maps quote-by-symbol responses and skips empty requests', async () => {
    await nextUiUnitStory('Stock API client maps quote-by-symbol responses', {
      severity: 'normal',
      tags: ['stock', 'api-client'],
    })
    const fetchMock = vi.fn(async () => jsonResponse({
      quotes: [
        { symbol: 'PKO', price: '55.12', currency: 'PLN', change_pct: '1.20' },
      ],
    }))
    vi.stubGlobal('fetch', fetchMock)
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getQuotesBySymbols } = await import('@/lib/api/stock')

    await expect(getQuotesBySymbols([])).resolves.toEqual({})
    await expect(getQuotesBySymbols(['PKO'])).resolves.toEqual({
      PKO: { symbol: 'PKO', price: '55.12', currency: 'PLN', change_pct: '1.20' },
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('returns empty quote maps on stock API failures', async () => {
    await nextUiUnitStory('Stock API client returns empty quote maps on failures', {
      severity: 'normal',
      tags: ['stock', 'api-client', 'error-state'],
    })
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'down' }, 503)))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getQuotesBulk, getQuotesBySymbols } = await import('@/lib/api/stock')

    await expect(getQuotesBulk('XWAR')).resolves.toEqual({})
    await expect(getQuotesBySymbols(['PKO'])).resolves.toEqual({})
  })
})
