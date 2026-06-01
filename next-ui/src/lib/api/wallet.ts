import { logger } from '@/lib/logger'
import type { WalletSyncResponse, WalletCreationResponse, AccountCreationResponse, UserNote, YearGoalOut, RecurringExpenseOut } from '@/lib/types/wallet'

const BASE = process.env.WALLET_API_URL ?? ''

export type ApiResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number }

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...extraHeaders,
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  try {
    const res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    })

    if (!res.ok) {
      const text = await res.text()
      logger.warn({ status: res.status, path, body: text }, 'wallet API error')
      // Try to extract a human-readable message from FastAPI/Pydantic error shape
      let error = `Błąd serwera (${res.status})`
      try {
        const json = JSON.parse(text) as Record<string, unknown>
        if (typeof json['detail'] === 'string') {
          error = json['detail']
        } else if (Array.isArray(json['detail'])) {
          const first = json['detail'][0] as Record<string, unknown> | undefined
          if (first && typeof first['msg'] === 'string') error = first['msg']
        }
      } catch { /* leave generic message */ }
      logger.warn({ path, status: res.status, parsedError: error }, 'wallet API error parsed')
      return { ok: false, error, status: res.status }
    }

    if (res.status === 204) {
      return { ok: true, data: undefined as T, status: res.status }
    }
    const data = await res.json() as T
    return { ok: true, data, status: res.status }
  } catch (err) {
    logger.error({ err, path }, 'wallet API request failed')
    return { ok: false, error: 'Nie można połączyć się z serwisem portfela', status: 503 }
  }
}

async function requestOrNull<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T | null> {
  const result = await request<T>(method, path, body, extraHeaders)
  return result.ok ? result.data : null
}

export async function createAccount(
  userId: string,
  walletId: string,
  payload: {
    name: string
    account_type: string
    currency: string
    account_number: string
    bank_id: string
    iban: string
  },
): Promise<ApiResult<AccountCreationResponse>> {
  return request<AccountCreationResponse>(`POST`, `/wallet/${walletId}/account/create`, payload, {
    'X-User-Id': userId,
  })
}

export async function deleteWallet(userId: string, walletId: string): Promise<boolean> {
  const result = await request<unknown>('DELETE', `/wallet/delete/${walletId}`, undefined, {
    'X-User-Id': userId,
  })
  return result.ok
}

export async function createWallet(
  name: string,
  userId: string,
): Promise<WalletCreationResponse | null> {
  return requestOrNull<WalletCreationResponse>('POST', '/wallet/create/wallet', { name }, {
    'X-User-Id': userId,
  })
}

export async function getMyNote(userId: string): Promise<ApiResult<UserNote | null>> {
  return request<UserNote | null>('GET', '/users/me/note', undefined, { 'X-User-Id': userId })
}

export async function upsertMyNote(
  userId: string,
  text: string,
): Promise<ApiResult<UserNote>> {
  return request<UserNote>('PUT', '/users/me/note', { text }, { 'X-User-Id': userId })
}

export async function createTransactions(
  userId: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('POST', '/wallet/transactions/create/rebalance', payload, { 'X-User-Id': userId })
}

export async function createBrokerageEvent(
  userId: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('POST', '/wallet/brokerage/event', payload, { 'X-User-Id': userId })
}

export async function importBrokerageEvents(
  userId: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<{ created: number; failed: number; errors: string[] }>> {
  return request<{ created: number; failed: number; errors: string[] }>(
    'POST',
    '/wallet/brokerage/events/import',
    payload,
    { 'X-User-Id': userId },
  )
}

export async function createDebt(
  userId: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('POST', '/wallet/debts/create', payload, { 'X-User-Id': userId })
}

export async function updateDebt(
  userId: string,
  id: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('PUT', `/wallet/debts/${id}`, payload, { 'X-User-Id': userId })
}

export async function deleteDebt(userId: string, id: string): Promise<boolean> {
  const result = await request<unknown>('DELETE', `/wallet/debts/${id}`, undefined, { 'X-User-Id': userId })
  return result.ok
}

export async function createRealEstate(
  userId: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('POST', '/wallet/real-estates/create', payload, { 'X-User-Id': userId })
}

export async function updateRealEstate(
  userId: string,
  id: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('PUT', `/wallet/real-estates/${id}`, payload, { 'X-User-Id': userId })
}

export async function deleteRealEstate(userId: string, id: string): Promise<boolean> {
  const result = await request<unknown>('DELETE', `/wallet/real-estates/${id}`, undefined, { 'X-User-Id': userId })
  return result.ok
}

export async function sellRealEstate(
  userId: string,
  id: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('PATCH', `/wallet/real-estates/${id}/sell`, payload, { 'X-User-Id': userId })
}

export async function createMetalHolding(
  userId: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('POST', '/wallet/metal-holdings/create', payload, { 'X-User-Id': userId })
}

export async function updateMetalHolding(
  userId: string,
  id: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('PUT', `/wallet/metal-holdings/${id}`, payload, { 'X-User-Id': userId })
}

export async function deleteMetalHolding(userId: string, id: string): Promise<boolean> {
  const result = await request<unknown>('DELETE', `/wallet/metal-holdings/${id}`, undefined, { 'X-User-Id': userId })
  return result.ok
}

export async function getLatestRealEstatePrice(params: {
  type: string
  country?: string | null
  city?: string | null
  currency: string
}): Promise<string | null> {
  const qs = new URLSearchParams({ type: params.type, currency: params.currency })
  if (params.country) qs.set('country', params.country)
  if (params.city) qs.set('city', params.city)
  try {
    const res = await fetch(`${BASE}/wallet/real-estate-prices/latest?${qs}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!res.ok) return null
    const data = await res.json() as { avg_price_per_m2?: string }
    return data.avg_price_per_m2 ?? null
  } catch {
    return null
  }
}

export async function createRealEstatePrice(
  userId: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('POST', '/wallet/real-estate-prices/create', payload, { 'X-User-Id': userId })
}

export async function sellMetalHolding(
  userId: string,
  id: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('PATCH', `/wallet/metal-holdings/${id}/sell`, payload, { 'X-User-Id': userId })
}

export type TransactionItemOut = {
  id: string
  amount: number
  description: string
  balance_before: number
  balance_after: number
  date_transaction: string
  account_id: string
  account_name: string
  category: string | null
  status: string | null
  ccy: string
}

export type TransactionPageOut = {
  items: TransactionItemOut[]
  total: number
  page: number
  size: number
  sum_by_ccy: Record<string, number>
}

export async function listTransactions(
  userId: string,
  params: {
    page?: number
    size?: number
    account_id?: string[]
    category?: string[]
    status?: string[]
    date_from?: string
    date_to?: string
    q?: string
  },
): Promise<ApiResult<TransactionPageOut>> {
  const qs = new URLSearchParams()
  if (params.page) qs.set('page', String(params.page))
  if (params.size) qs.set('size', String(params.size))
  if (params.account_id?.length) params.account_id.forEach((id) => qs.append('account_id', id))
  if (params.category?.length) params.category.forEach((c) => qs.append('category', c))
  if (params.status?.length) params.status.forEach((s) => qs.append('status', s))
  if (params.date_from) qs.set('date_from', params.date_from)
  if (params.date_to) qs.set('date_to', params.date_to)
  if (params.q) qs.set('q', params.q)
  return request<TransactionPageOut>('GET', `/wallet/transactions?${qs}`, undefined, { 'X-User-Id': userId })
}

export async function batchUpdateTransactions(
  userId: string,
  items: Array<{
    id: string
    description?: string
    category?: string | null
    status?: string | null
  }>,
): Promise<ApiResult<{ updated: number; failed: unknown[] }>> {
  return request<{ updated: number; failed: unknown[] }>(
    'PATCH',
    '/wallet/transactions/batch',
    { items },
    { 'X-User-Id': userId },
  )
}

export async function deleteTransaction(userId: string, id: string): Promise<boolean> {
  const result = await request<unknown>('DELETE', `/wallet/transactions/${id}`, undefined, { 'X-User-Id': userId })
  return result.ok
}

export type HoldingRowOut = {
  account_id: string
  account_name: string
  instrument_id: string
  instrument_symbol: string
  instrument_name: string
  instrument_currency: string
  quantity: string | number
  avg_cost: string | number
}

export async function listHoldings(
  userId: string,
  params: {
    q?: string
    brokerage_account_id?: string[]
  } = {},
): Promise<HoldingRowOut[]> {
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.brokerage_account_id?.length) {
    params.brokerage_account_id.forEach((id) => qs.append('brokerage_account_id', id))
  }
  const result = await request<HoldingRowOut[]>(
    'GET',
    `/users/${userId}/holdings${qs.toString() ? `?${qs}` : ''}`,
    undefined,
    { 'X-User-Id': userId },
  )
  return result.ok ? result.data : []
}

export async function listBrokerageAccounts(userId: string): Promise<{ id: string; name: string }[]> {
  const result = await request<{ id: string; name: string }[]>(
    'GET',
    '/wallet/brokerage/accounts',
    undefined,
    { 'X-User-Id': userId },
  )
  return result.ok ? result.data : []
}

export type ManagerHealth = {
  missing_quotes?: number
  stale_quotes?: boolean
  projection_mismatch?: boolean
  needs_review?: boolean
}

export type ManagerDepositAccount = {
  id: string
  name: string
  available: string | number
  ccy: string
  tx_per_month?: number
  snapshots?: Record<string, { available: string | number; ccy?: string } | null>
  health?: ManagerHealth
}

export type ManagerBrokeragePosition = {
  symbol?: string
  mic?: string | null
  currency?: string
  value?: string | number
  pnl_pct?: string | number
}

export type ManagerBrokerageCashAccount = {
  name?: string
  ccy?: string
  available?: string | number
}

export type ManagerBrokerageAccount = {
  id: string
  name: string
  ccy?: string
  sum_cash_accounts?: string | number
  positions_value?: string | number
  events_per_month?: number
  cash_accounts?: ManagerBrokerageCashAccount[]
  positions?: ManagerBrokeragePosition[]
  snapshots?: Record<string, { cash: string | number; stocks: string | number; ccy?: string } | null>
  health?: ManagerHealth
}

export type ManagerMetalItem = {
  id?: string
  name?: string | null
  metal?: string | null
  type?: string | null
  quantity?: string | number
  qty_unit?: string
  value?: string | number
  ccy?: string
}

export type ManagerMetals = {
  count?: number
  value?: string | number
  ccy?: string
  items?: ManagerMetalItem[]
  health?: ManagerHealth
}

export type ManagerRealEstateItem = {
  id?: string
  name?: string | null
  type?: string | null
  city?: string | null
  value?: string | number
  ccy?: string
}

export type ManagerRealEstate = {
  count?: number
  value?: string | number
  ccy?: string
  items?: ManagerRealEstateItem[]
  health?: ManagerHealth
}

export type WalletManagerNode = {
  id: string
  name: string
  deposit_accounts?: ManagerDepositAccount[]
  brokerage_accounts?: ManagerBrokerageAccount[]
  metals?: ManagerMetals | null
  real_estate?: ManagerRealEstate | null
  snapshots?: Record<string, {
    cash_deposit?: string | number
    cash_broker?: string | number
    stocks?: string | number
    metals?: string | number
    real_estate?: string | number
    ccy?: string
  } | null>
}

export async function getWalletManagerTree(
  userId: string,
  currencyRate: Record<string, string>,
  months = 2,
): Promise<WalletManagerNode[] | null> {
  const result = await request<WalletManagerNode[]>(
    'POST',
    '/wallet/manager/tree',
    { months, currency_rate: currencyRate },
    { 'X-User-Id': userId },
  )
  return result.ok ? result.data : null
}

export type FavoriteList = { id: string; name: string; description?: string | null }

export async function listFavoriteLists(userId: string): Promise<FavoriteList[]> {
  const result = await request<FavoriteList[]>('GET', '/users/favorites/lists', undefined, { 'X-User-Id': userId })
  return result.ok ? result.data : []
}

export async function createFavoriteList(
  userId: string,
  payload: { name: string; description?: string | null },
): Promise<ApiResult<FavoriteList>> {
  return request<FavoriteList>('POST', '/users/favorites/lists', payload, { 'X-User-Id': userId })
}

export async function deleteFavoriteList(userId: string, listId: string): Promise<boolean> {
  const result = await request<unknown>('DELETE', `/users/favorites/lists/${listId}`, undefined, { 'X-User-Id': userId })
  return result.ok
}

export type FavoriteItemWithAlert = {
  symbol: string
  name?: string | null
  mic?: string | null
  alert?: {
    id?: string
    below_price?: string | null
    above_price?: string | null
    enabled?: boolean
    one_shot?: boolean
    expires_at?: string | null
  } | null
}

export async function listFavoriteItemsWithAlerts(
  userId: string,
  listId: string,
): Promise<FavoriteItemWithAlert[]> {
  const result = await request<FavoriteItemWithAlert[]>(
    'GET',
    `/users/favorites/lists/${listId}/items-with-alerts`,
    undefined,
    { 'X-User-Id': userId },
  )
  return result.ok ? result.data : []
}

export async function addFavoriteItem(
  userId: string,
  listId: string,
  symbol: string,
  mic: string,
  name: string,
): Promise<boolean> {
  const result = await request<unknown>(
    'POST',
    `/users/favorites/lists/${listId}/items`,
    { symbol, mic, name },
    { 'X-User-Id': userId },
  )
  return result.ok
}

export async function removeFavoriteItem(
  userId: string,
  listId: string,
  symbol: string,
): Promise<boolean> {
  const result = await request<unknown>(
    'DELETE',
    `/users/favorites/lists/${listId}/items/${symbol}`,
    undefined,
    { 'X-User-Id': userId },
  )
  return result.ok
}

export type AlertPayload = {
  symbol: string
  below_price?: string | null
  above_price?: string | null
  enabled?: boolean
  one_shot?: boolean
  expires_at?: string | null
}

export type PriceAlertBySymbol = {
  id?: string
  symbol?: string | null
  below_price: string | null
  above_price: string | null
  enabled: boolean
  one_shot: boolean
  expires_at: string | null
}

export async function getAlertBySymbol(userId: string, symbol: string): Promise<ApiResult<PriceAlertBySymbol | null>> {
  return request<PriceAlertBySymbol | null>('GET', `/users/alerts/${encodeURIComponent(symbol)}`, undefined, { 'X-User-Id': userId })
}

export async function upsertAlert(userId: string, payload: AlertPayload): Promise<ApiResult<unknown>> {
  return request<unknown>('POST', '/users/alerts', payload, { 'X-User-Id': userId })
}

export async function deleteAlert(userId: string, symbol: string): Promise<boolean> {
  const result = await request<unknown>('DELETE', `/users/alerts/${symbol}`, undefined, { 'X-User-Id': userId })
  return result.ok
}

export type BrokerageEventRowOut = {
  id: string
  brokerage_account_id: string
  instrument_id: string
  brokerage_account_name: string
  instrument_symbol: string
  instrument_name: string | null
  kind: string
  quantity: string | number
  price: string | number
  currency: string
  split_ratio: string | number
  trade_at: string
}

export type BrokerageEventsPageOut = {
  items: BrokerageEventRowOut[]
  total: number
  page: number
  size: number
  sum_by_ccy: Record<string, number>
}

export async function listBrokerageEvents(
  userId: string,
  params: {
    page?: number
    size?: number
    brokerage_account_id?: string[]
    kind?: string[]
    currency?: string[]
    date_from?: string
    date_to?: string
    q?: string
  } = {},
): Promise<ApiResult<BrokerageEventsPageOut>> {
  const qs = new URLSearchParams()
  if (params.page) qs.set('page', String(params.page))
  if (params.size) qs.set('size', String(params.size))
  if (params.brokerage_account_id?.length) params.brokerage_account_id.forEach((id) => qs.append('brokerage_account_id', id))
  if (params.kind?.length) params.kind.forEach((k) => qs.append('kind', k))
  if (params.currency?.length) params.currency.forEach((c) => qs.append('currency', c))
  if (params.date_from) qs.set('date_from', params.date_from)
  if (params.date_to) qs.set('date_to', params.date_to)
  if (params.q) qs.set('q', params.q)
  return request<BrokerageEventsPageOut>(
    'GET',
    `/wallet/brokerage/events${qs.toString() ? `?${qs}` : ''}`,
    undefined,
    { 'X-User-Id': userId },
  )
}

export async function batchUpdateBrokerageEvents(
  userId: string,
  items: Array<{ id: string; kind?: string; quantity?: string; price?: string }>,
): Promise<ApiResult<unknown>> {
  return request<unknown>('PATCH', '/wallet/brokerage/events/batch', { items }, { 'X-User-Id': userId })
}

export async function deleteBrokerageEvent(userId: string, eventId: string): Promise<boolean> {
  const result = await request<unknown>(
    'DELETE',
    `/wallet/brokerage/events/${eventId}`,
    undefined,
    { 'X-User-Id': userId },
  )
  return result.ok
}

export async function syncUser(payload: {
  username: string
  first_name?: string
  email?: string
}): Promise<WalletSyncResponse | null> {
  return requestOrNull<WalletSyncResponse>('POST', '/wallet/sync/user', payload)
}

export async function listWalletGoals(
  userId: string,
  walletId: string,
): Promise<ApiResult<YearGoalOut[]>> {
  return request<YearGoalOut[]>('GET', `/wallet/${walletId}/goals/all`, undefined, {
    'X-User-Id': userId,
  })
}

export async function upsertWalletGoal(
  userId: string,
  payload: {
    wallet_id: string
    year: number
    rev_target_year: string
    exp_budget_year: string
    currency: string
  },
): Promise<ApiResult<YearGoalOut>> {
  return request<YearGoalOut>('POST', '/wallet/goals/upsert', payload, { 'X-User-Id': userId })
}

export async function deleteWalletGoal(userId: string, goalId: string): Promise<boolean> {
  const result = await request<unknown>('DELETE', `/wallet/goals/${goalId}`, undefined, {
    'X-User-Id': userId,
  })
  return result.ok
}

export async function listRecurringExpenses(
  userId: string,
  walletId: string,
): Promise<ApiResult<RecurringExpenseOut[]>> {
  return request<RecurringExpenseOut[]>(
    'GET',
    `/wallet/${walletId}/recurring-expenses`,
    undefined,
    { 'X-User-Id': userId },
  )
}

export async function createRecurringExpense(
  userId: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<RecurringExpenseOut>> {
  return request<RecurringExpenseOut>('POST', '/wallet/recurring-expenses/create', payload, {
    'X-User-Id': userId,
  })
}

export async function updateRecurringExpense(
  userId: string,
  id: string,
  payload: Record<string, unknown>,
): Promise<ApiResult<RecurringExpenseOut>> {
  return request<RecurringExpenseOut>('PUT', `/wallet/recurring-expenses/${id}`, payload, {
    'X-User-Id': userId,
  })
}

export async function deleteRecurringExpense(userId: string, id: string): Promise<boolean> {
  const result = await request<unknown>(
    'DELETE',
    `/wallet/recurring-expenses/${id}`,
    undefined,
    { 'X-User-Id': userId },
  )
  return result.ok
}
