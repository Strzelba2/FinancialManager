import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import { nextUiUnitStory } from '../allure'

const server = setupServer()

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

afterEach(() => {
  server.resetHandlers()
})

afterAll(() => {
  server.close()
})

describe('wallet API client', () => {
  afterEach(() => {
    vi.resetModules()
    delete process.env.WALLET_API_URL
  })

  it('creates a wallet with the internal user header', async () => {
    await nextUiUnitStory('Wallet API client creates wallets with user identity header', {
      severity: 'critical',
      tags: ['wallet', 'api-client', 'financial-data'],
    })
    const requests: Request[] = []
    server.use(http.post('http://wallet:8001/wallet/create/wallet', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({ id: 'wallet-1', name: 'Main' })
    }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { createWallet } = await import('@/lib/api/wallet')

    const result = await createWallet('Main', 'user-1')

    expect(result).toEqual({ id: 'wallet-1', name: 'Main' })
    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    expect(requests[0]?.headers.get('Accept')).toBe('application/json')
    expect(requests[0]?.headers.get('Content-Type')).toBe('application/json')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
    await expect(requests[0]?.json()).resolves.toEqual({ name: 'Main' })
  })

  it('extracts FastAPI validation messages from account creation errors', async () => {
    await nextUiUnitStory('Wallet API client extracts FastAPI validation error messages', {
      severity: 'critical',
      tags: ['wallet', 'api-client', 'validation'],
    })
    server.use(http.post('http://wallet:8001/wallet/wallet-1/account/create', () => (
      HttpResponse.json({ detail: [{ msg: 'Field required' }] }, { status: 422 })
    )))
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
    const requests: Request[] = []
    server.use(http.post('http://wallet:8001/users/favorites/lists', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({ detail: message }, { status: 409 })
    }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { createFavoriteList } = await import('@/lib/api/wallet')

    const result = await createFavoriteList('user-1', {
      name: 'My watchlist',
      description: 'Tracked instruments',
    })

    expect(result).toEqual({ ok: false, error: message, status: 409 })
    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    expect(requests[0]?.headers.get('Content-Type')).toBe('application/json')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
    await expect(requests[0]?.json()).resolves.toEqual({
      name: 'My watchlist',
      description: 'Tracked instruments',
    })
  })

  it('creates transactions through the rebalance endpoint with the internal user header', async () => {
    await nextUiUnitStory('Wallet API client creates transactions without edit-only classification fields', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-client', 'financial-data'],
    })
    const payload = {
      account_id: '11111111-1111-4111-8111-111111111111',
      transactions: [
        {
          date: '2026-05-01T09:00:00.000Z',
          amount: '100.00',
          amount_after: '100.00',
          description: 'Salary',
        },
      ],
    }
    const requests: Request[] = []
    server.use(http.post('http://wallet:8001/wallet/transactions/create/rebalance', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({ created: 1, transaction_ids: ['tx-1'] }, { status: 201 })
    }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { createTransactions } = await import('@/lib/api/wallet')

    const result = await createTransactions('user-1', payload)

    expect(result).toEqual({
      ok: true,
      data: { created: 1, transaction_ids: ['tx-1'] },
      status: 201,
    })
    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    expect(requests[0]?.headers.get('Accept')).toBe('application/json')
    expect(requests[0]?.headers.get('Content-Type')).toBe('application/json')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
    await expect(requests[0]?.json()).resolves.toEqual(payload)
  })

  it('lists transactions with filters encoded for the wallet service', async () => {
    await nextUiUnitStory('Wallet API client lists transactions with filter query parameters', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-client', 'filters'],
    })
    const requests: Request[] = []
    server.use(http.get('http://wallet:8001/wallet/transactions', ({ request }) => {
      requests.push(request)
      return HttpResponse.json({ items: [], total: 0, page: 2, size: 20, sum_by_ccy: {} })
    }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { listTransactions } = await import('@/lib/api/wallet')

    const result = await listTransactions('user-1', {
      page: 2,
      size: 20,
      account_id: ['account-1', 'account-2'],
      category: ['FOOD'],
      status: ['EXPENSE'],
      date_from: '2026-05-01',
      date_to: '2026-05-31',
      q: 'grocery',
    })

    expect(result.ok).toBe(true)
    const url = requests[0]?.url ?? ''
    expect(url.startsWith('http://wallet:8001/wallet/transactions?')).toBe(true)
    expect(url).toContain('page=2')
    expect(url).toContain('size=20')
    expect(url).toContain('account_id=account-1')
    expect(url).toContain('account_id=account-2')
    expect(url).toContain('category=FOOD')
    expect(url).toContain('status=EXPENSE')
    expect(url).toContain('date_from=2026-05-01')
    expect(url).toContain('date_to=2026-05-31')
    expect(url).toContain('q=grocery')
    expect(requests[0]?.method).toBe('GET')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
  })

  it('batch updates and deletes transactions with user identity', async () => {
    await nextUiUnitStory('Wallet API client updates and deletes transactions with user identity', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'api-client', 'financial-data'],
    })
    const requests: Request[] = []
    server.use(
      http.patch('http://wallet:8001/wallet/transactions/batch', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ updated: 1, failed: [] })
      }),
      http.delete('http://wallet:8001/wallet/transactions/tx-1', ({ request }) => {
        requests.push(request)
        return HttpResponse.json({ ok: true })
      }),
    )
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { batchUpdateTransactions, deleteTransaction } = await import('@/lib/api/wallet')

    await expect(batchUpdateTransactions('user-1', [
      {
        id: 'tx-1',
        description: 'Updated',
        category: 'FOOD',
        status: 'EXPENSE',
      },
    ])).resolves.toEqual({ ok: true, data: { updated: 1, failed: [] }, status: 200 })
    await expect(deleteTransaction('user-1', 'tx-1')).resolves.toBe(true)

    expect(requests).toHaveLength(2)
    expect(requests[0]?.method).toBe('PATCH')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
    await expect(requests[0]?.json()).resolves.toEqual({
      items: [
        {
          id: 'tx-1',
          description: 'Updated',
          category: 'FOOD',
          status: 'EXPENSE',
        },
      ],
    })
    expect(requests[1]?.method).toBe('DELETE')
    expect(requests[1]?.headers.get('X-User-Id')).toBe('user-1')
  })

  it('returns safe defaults when wallet service is unavailable', async () => {
    await nextUiUnitStory('Wallet API client returns safe defaults on service outage', {
      severity: 'critical',
      tags: ['wallet', 'api-client', 'error-state'],
    })
    server.use(
      http.get('http://wallet:8001/users/favorites/lists', () => HttpResponse.error()),
      http.delete('http://wallet:8001/wallet/delete/wallet-1', () => HttpResponse.error()),
    )
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { listFavoriteLists, deleteWallet } = await import('@/lib/api/wallet')

    await expect(listFavoriteLists('user-1')).resolves.toEqual([])
    await expect(deleteWallet('user-1', 'wallet-1')).resolves.toBe(false)
  })
})

describe('stock API client', () => {
  afterEach(() => {
    vi.resetModules()
    delete process.env.STOCK_API_URL
  })

  it('normalizes bulk quote display values returned from stock service', async () => {
    await nextUiUnitStory('Stock API client normalizes quote display values', {
      severity: 'normal',
      tags: ['stock', 'api-client', 'reports'],
    })
    server.use(http.get('http://stock:8001/stock/quotes/latest/bulk', () => HttpResponse.json({
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
    const requests: Request[] = []
    server.use(http.post('http://stock:8001/stock/quotes/latest/symbols', ({ request }) => {
      requests.push(request)
      return HttpResponse.json({
        quotes: [
          { symbol: 'PKO', price: '55.12', currency: 'PLN', change_pct: '1.20' },
        ],
      })
    }))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getQuotesBySymbols } = await import('@/lib/api/stock')

    await expect(getQuotesBySymbols([])).resolves.toEqual({})
    await expect(getQuotesBySymbols(['PKO'])).resolves.toEqual({
      PKO: { symbol: 'PKO', price: '55.12', currency: 'PLN', change_pct: '1.20' },
    })
    expect(requests).toHaveLength(1)
  })

  it('returns empty quote maps on stock API failures', async () => {
    await nextUiUnitStory('Stock API client returns empty quote maps on failures', {
      severity: 'normal',
      tags: ['stock', 'api-client', 'error-state'],
    })
    server.use(
      http.get('http://stock:8001/stock/quotes/latest/bulk', () => (
        HttpResponse.json({ detail: 'down' }, { status: 503 })
      )),
      http.post('http://stock:8001/stock/quotes/latest/symbols', () => (
        HttpResponse.json({ detail: 'down' }, { status: 503 })
      )),
    )
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getQuotesBulk, getQuotesBySymbols } = await import('@/lib/api/stock')

    await expect(getQuotesBulk('XWAR')).resolves.toEqual({})
    await expect(getQuotesBySymbols(['PKO'])).resolves.toEqual({})
  })
})
