import { afterEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'

import { nextUiUnitStory } from '../allure'
afterEach(() => {
  server.resetHandlers()
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

  it('synchronizes instrument names with the internal user header', async () => {
    await nextUiUnitStory('Wallet API client synchronizes canonical instrument display names', {
      severity: 'critical',
      tags: ['wallet', 'stock', 'instruments', 'api-client', 'financial-data'],
    })
    const requests: Request[] = []
    server.use(http.put('http://wallet:8001/wallet/instruments/PKO/name', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({ symbol: 'PKO', mic: 'XWAR', name: 'PKO BP SA', created: true })
    }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { synchronizeInstrumentName } = await import('@/lib/api/wallet')

    const result = await synchronizeInstrumentName(
      'user-1',
      'PKO',
      { mic: 'XWAR', name: 'PKO BP SA' },
    )

    expect(result).toEqual({
      ok: true,
      status: 200,
      data: { symbol: 'PKO', mic: 'XWAR', name: 'PKO BP SA', created: true },
    })
    expect(requests[0]?.method).toBe('PUT')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
    await expect(requests[0]?.json()).resolves.toEqual({ mic: 'XWAR', name: 'PKO BP SA' })
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
      sort_by: 'category',
      sort_dir: 'asc',
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
    expect(url).toContain('sort_by=category')
    expect(url).toContain('sort_dir=asc')
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

  it('imports brokerage events and preserves duplicate skip summary fields', async () => {
    await nextUiUnitStory('Wallet API client preserves brokerage import duplicate skip summary', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'import', 'api-client', 'financial-data'],
    })
    const payload = {
      brokerage_account_id: '11111111-1111-4111-8111-111111111111',
      events: [
        {
          trade_at: '2026-06-01T09:00:00.000Z',
          instrument_symbol: 'PKOBP',
          instrument_mic: 'XWAR',
          instrument_name: 'PKO BP SA',
          kind: 'BUY',
          quantity: '1.00',
          price: '10.00',
          currency: 'PLN',
          split_ratio: '0.00',
        },
      ],
    }
    const responsePayload = {
      total: 2,
      created: 1,
      cash_transactions_created: 0,
      skipped_duplicates: 1,
      needs_review: 0,
      failed: 0,
      errors: [],
      rows: [
        { row: 1, status: 'skipped_duplicate', message: 'Brokerage event already exists.' },
        { row: 2, status: 'created', brokerage_event_id: 'event-2' },
      ],
    }
    const requests: Request[] = []
    server.use(http.post('http://wallet:8001/wallet/brokerage/events/import', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json(responsePayload)
    }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { importBrokerageEvents } = await import('@/lib/api/wallet')

    const result = await importBrokerageEvents('user-1', payload)

    expect(result).toEqual({ ok: true, data: responsePayload, status: 200 })
    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
    await expect(requests[0]?.json()).resolves.toEqual(payload)
  })

  it('deletes brokerage accounts with the internal user header', async () => {
    await nextUiUnitStory('Wallet API client deletes brokerage accounts with user identity header', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-client', 'ownership'],
    })
    const requests: Request[] = []
    server.use(http.delete('http://wallet:8001/wallet/brokerage/brokerage-1', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({ ok: true })
    }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { deleteBrokerageAccount } = await import('@/lib/api/wallet')

    const ok = await deleteBrokerageAccount('user-1', 'brokerage-1')

    expect(ok).toBe(true)
    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('DELETE')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
  })

  it('imports brokerage history and ensures cash links with the internal user header', async () => {
    await nextUiUnitStory('Wallet API client forwards brokerage history and cash-link requests with user identity', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-client', 'cash-links', 'financial-data'],
    })
    const historyPayload = {
      brokerage_account_id: 'brokerage-1',
      rows: [
        {
          row_number: 1,
          operation_type: 'TRANSFER',
          trade_at: '2026-06-04T10:00:00.000Z',
          currency: 'PLN',
          amount: '100.00',
          amount_after: '100.00',
          description: 'Wpłata',
        },
      ],
    }
    const cashPayload = {
      cash_accounts: [
        { currency: 'USD', account_number: 'BOSSA-USD', name: 'USD cash' },
      ],
    }
    const requests: Request[] = []
    server.use(
      http.post('http://wallet:8001/wallet/brokerage/history/import', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ total: 1, created: 1, failed: 0, rows: [] })
      }),
      http.post('http://wallet:8001/wallet/brokerage/brokerage-1/cash-links/ensure', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json([{ currency: 'USD', deposit_account_id: 'deposit-1', created: true }])
      }),
    )
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { importBrokerageHistory, ensureBrokerageCashLinks } = await import('@/lib/api/wallet')

    await expect(importBrokerageHistory('user-1', historyPayload)).resolves.toEqual({
      ok: true,
      data: { total: 1, created: 1, failed: 0, rows: [] },
      status: 200,
    })
    await expect(ensureBrokerageCashLinks('user-1', 'brokerage-1', cashPayload)).resolves.toEqual({
      ok: true,
      data: [{ currency: 'USD', deposit_account_id: 'deposit-1', created: true }],
      status: 200,
    })
    expect(requests.map((request) => request.method)).toEqual(['POST', 'POST'])
    expect(requests.map((request) => request.headers.get('X-User-Id'))).toEqual(['user-1', 'user-1'])
    await expect(requests[0]?.json()).resolves.toEqual(historyPayload)
    await expect(requests[1]?.json()).resolves.toEqual(cashPayload)
  })

  it('upserts annual goals with a separate capital gain target', async () => {
    await nextUiUnitStory('Wallet API client sends annual capital gain targets separately from income goals', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'api-client', 'financial-data'],
    })
    const payload = {
      wallet_id: '11111111-1111-4111-8111-111111111111',
      year: 2026,
      rev_target_year: '200000.00',
      exp_budget_year: '90000.00',
      capital_gain_target_year: '60000.00',
      currency: 'PLN',
    }
    const responsePayload = {
      id: 'goal-1',
      ...payload,
      created_at: '2026-06-13T08:00:00Z',
      updated_at: '2026-06-13T08:00:00Z',
    }
    const requests: Request[] = []
    server.use(http.post('http://wallet:8001/wallet/goals/upsert', async ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json(responsePayload)
    }))
    process.env.WALLET_API_URL = 'http://wallet:8001'
    const { upsertWalletGoal } = await import('@/lib/api/wallet')

    await expect(upsertWalletGoal('user-1', payload)).resolves.toEqual({
      ok: true,
      data: responsePayload,
      status: 200,
    })

    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    expect(requests[0]?.headers.get('Content-Type')).toBe('application/json')
    expect(requests[0]?.headers.get('X-User-Id')).toBe('user-1')
    await expect(requests[0]?.json()).resolves.toEqual(payload)
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
    expect(quote.last_price_fmt).toBe('55,120')
    expect(quote.change_pct_fmt).toBe('+1,200%')
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
      return HttpResponse.json([
        { symbol: 'PKO', name: 'PKO BP', price: '55.12', currency: 'PLN', change_pct: '1.20' },
      ])
    }))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getQuotesBySymbols } = await import('@/lib/api/stock')

    await expect(getQuotesBySymbols([])).resolves.toEqual({})
    await expect(getQuotesBySymbols(['PKO'])).resolves.toEqual({
      PKO: { symbol: 'PKO', name: 'PKO BP', price: '55.12', currency: 'PLN', change_pct: '1.20' },
    })
    expect(requests).toHaveLength(1)
  })

  it('sends quote_source when creating a manual stock instrument', async () => {
    await nextUiUnitStory('Stock API client sends quote_source for manual instruments', {
      severity: 'critical',
      tags: ['stock', 'quote-source', 'api-client'],
    })
    const requests: Request[] = []
    server.use(http.post('http://stock:8001/stock/instruments', ({ request }) => {
      requests.push(request.clone())
      return HttpResponse.json({
        market_id: 'market-1',
        mic: 'XLON',
        market_mic: 'XLON',
        symbol: 'LNGA.UK',
        shortname: 'LNGA.UK',
        name: 'WisdomTree Natural Gas',
        type: 'ETF',
        status: 'ACTIVE',
        currency: 'USD',
        quote_source: 'https://quotes.example.com/q/?s=lnga.uk',
      }, { status: 201 })
    }))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { createInstrument } = await import('@/lib/api/stock')

    const result = await createInstrument({
      market_mic: 'XLON',
      symbol: 'LNGA.UK',
      shortname: 'LNGA.UK',
      name: 'WisdomTree Natural Gas',
      type: 'ETF',
      status: 'ACTIVE',
      currency: 'USD',
      isin: null,
      historical_source: null,
      quote_source: 'https://quotes.example.com/q/?s=lnga.uk',
    })

    expect(result.ok).toBe(true)
    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    await expect(requests[0]?.json()).resolves.toEqual(expect.objectContaining({
      market_mic: 'XLON',
      symbol: 'LNGA.UK',
      quote_source: 'https://quotes.example.com/q/?s=lnga.uk',
    }))
  })

  it('requests only markets with instruments for quote navigation', async () => {
    await nextUiUnitStory('Stock API client requests markets with instruments filter', {
      severity: 'normal',
      tags: ['stock', 'markets', 'api-client'],
    })
    const urls: string[] = []
    server.use(http.get('http://stock:8001/stock/markets', ({ request }) => {
      urls.push(request.url)
      return HttpResponse.json([{ mic: 'XLON', name: 'London' }])
    }))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getMarkets } = await import('@/lib/api/stock')

    const result = await getMarkets({ onlyWithInstruments: true })

    expect(result.ok).toBe(true)
    expect(urls).toHaveLength(1)
    expect(new URL(urls[0]!).searchParams.get('only_with_instruments')).toBe('true')
  })

  it('reports stock service health from the health endpoint', async () => {
    await nextUiUnitStory('Stock API client exposes stock service health for quote outage notices', {
      severity: 'critical',
      tags: ['stock', 'health', 'api-client', 'error-state'],
    })
    const urls: string[] = []
    server.use(http.get('http://stock:8001/healthz', ({ request }) => {
      urls.push(request.url)
      return HttpResponse.json({ ok: true })
    }))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getStockServiceStatus } = await import('@/lib/api/stock')

    await expect(getStockServiceStatus()).resolves.toEqual({ available: true })

    expect(urls).toEqual(['http://stock:8001/healthz'])
  })

  it('marks stock service unavailable when the health check cannot be reached', async () => {
    await nextUiUnitStory('Stock API client marks quote service unavailable on health-check failure', {
      severity: 'critical',
      tags: ['stock', 'health', 'api-client', 'error-state'],
    })
    server.use(http.get('http://stock:8001/healthz', () => HttpResponse.error()))
    process.env.STOCK_API_URL = 'http://stock:8001'
    const { getStockServiceStatus } = await import('@/lib/api/stock')

    await expect(getStockServiceStatus()).resolves.toEqual({ available: false })
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

describe('NBP FX rates', () => {
  const NBP_URL = 'https://api.nbp.pl/api/exchangerates/tables/A'

  afterEach(() => {
    vi.resetModules()
  })

  function tableA(rates: { code: string; mid: number }[]) {
    return [{ table: 'A', no: '001/A/NBP/2026', effectiveDate: '2026-06-10', rates }]
  }

  it('derives CHF and GBP cross rates against PLN/USD/EUR from NBP table A', async () => {
    await nextUiUnitStory('NBP client derives CHF and GBP cross rates for the view currencies', {
      severity: 'critical',
      tags: ['nbp', 'fx', 'money', 'financial-data'],
    })
    server.use(http.get(NBP_URL, () => HttpResponse.json(tableA([
      { code: 'USD', mid: 4.0 },
      { code: 'EUR', mid: 4.4 },
      { code: 'CHF', mid: 4.5 },
      { code: 'GBP', mid: 5.2 },
    ]))))
    const { getFxRates, convertCurrency } = await import('@/lib/api/nbp')

    const rates = await getFxRates()
    expect(rates).not.toBeNull()
    if (!rates) throw new Error('expected FX rates')

    // Forward source -> view currency rates must be present and correct.
    expect(rates['CHF/PLN']).toBe(4.5)
    expect(rates['CHF/USD']).toBe(1.125) // 4.5 / 4.0
    expect(rates['CHF/EUR']).toBe(1.0227) // 4.5 / 4.4, rounded to 4dp
    expect(rates['GBP/PLN']).toBe(5.2)
    expect(rates['GBP/USD']).toBe(1.3) // 5.2 / 4.0
    expect(rates['GBP/EUR']).toBe(1.1818) // 5.2 / 4.4, rounded to 4dp

    // Existing pairs remain unchanged.
    expect(rates['USD/PLN']).toBe(4.0)
    expect(rates['EUR/PLN']).toBe(4.4)

    // CHF/GBP amounts convert to each view currency (direct lookup).
    expect(convertCurrency(100, 'CHF', 'PLN', rates)).toBe(450)
    expect(convertCurrency(100, 'CHF', 'USD', rates)).toBe(112.5)
    expect(convertCurrency(100, 'CHF', 'EUR', rates)).toBe(102.27)
    expect(convertCurrency(100, 'GBP', 'PLN', rates)).toBe(520)
  })

  it('keeps CHF/GBP rates at zero (no conversion) when NBP omits them', async () => {
    await nextUiUnitStory('NBP client falls back to no conversion when CHF/GBP are missing', {
      severity: 'normal',
      tags: ['nbp', 'fx', 'money', 'error-state'],
    })
    server.use(http.get(NBP_URL, () => HttpResponse.json(tableA([
      { code: 'USD', mid: 4.0 },
      { code: 'EUR', mid: 4.4 },
    ]))))
    const { getFxRates, convertCurrency } = await import('@/lib/api/nbp')

    const rates = await getFxRates()
    expect(rates).not.toBeNull()
    if (!rates) throw new Error('expected FX rates')

    expect(rates['CHF/PLN']).toBe(0)
    expect(rates['GBP/USD']).toBe(0)
    // Missing rate -> amount returned unconverted (pre-existing behaviour).
    expect(convertCurrency(100, 'CHF', 'PLN', rates)).toBe(100)
  })
})
