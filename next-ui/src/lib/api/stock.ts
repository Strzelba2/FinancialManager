import { logger } from '@/lib/logger'
import type { EquityReport, ReportPeriod } from '@/features/reports/types/equity'

const BASE = process.env.STOCK_API_URL ?? ''
const WARSAW_TZ = 'Europe/Warsaw'

type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string }
type RequestResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number }

function extractErrorMessage(status: number, body: string): string {
  if (status === 404) return 'Nie znaleziono danych'
  try {
    const json = JSON.parse(body) as Record<string, unknown>
    if (typeof json.detail === 'string') return json.detail
    if (Array.isArray(json.detail) && json.detail.length > 0) {
      const first = json.detail[0] as Record<string, unknown>
      if (typeof first.msg === 'string') return first.msg
    }
    if (typeof json.error === 'string') return json.error
  } catch {
    // ignore parse error
  }
  return `Błąd serwera (${status})`
}

async function requestWithMeta<T>(path: string, init?: RequestInit): Promise<RequestResult<T>> {
  try {
    const headers = new Headers(init?.headers)
    if (!headers.has('Accept')) headers.set('Accept', 'application/json')

    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers,
      cache: 'no-store',
    })

    if (!res.ok) {
      const text = await res.text()
      logger.warn({ path, status: res.status, body: text }, 'stock API error')
      return { ok: false, error: extractErrorMessage(res.status, text), status: res.status }
    }

    const data = await res.json() as T
    return { ok: true, data, status: res.status }
  } catch (err) {
    logger.error({ err, path }, 'stock API request failed')
    return { ok: false, error: 'Nie można połączyć się z serwisem giełdowym', status: 503 }
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  const result = await requestWithMeta<T>(path, init)
  if (result.ok) {
    return { ok: true, data: result.data }
  }

  return { ok: false, error: result.error }
}

export async function getMarkets(options?: { onlyWithInstruments?: boolean }): Promise<ApiResult<Array<{ mic: string; name: string }>>> {
  const qs = new URLSearchParams()
  if (options?.onlyWithInstruments) qs.set('only_with_instruments', 'true')
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return request<Array<{ mic: string; name: string }>>(`/stock/markets${suffix}`)
}

export async function getInstruments(mic: string): Promise<ApiResult<Array<{ symbol: string; shortname: string }>>> {
  const qs = new URLSearchParams({ mic })
  return request<Array<{ symbol: string; shortname: string }>>(`/stock/instruments/options?${qs.toString()}`)
}

export type CreateMarketPayload = {
  mic: string
  name: string
  country: string
  timezone: string
  active: boolean
  currency: 'PLN' | 'USD' | 'EUR' | 'GBP' | 'CHF'
}

export type CreateInstrumentPayload = {
  market_mic: string
  symbol: string
  shortname: string
  name?: string | null
  type: string
  status: string
  currency: 'PLN' | 'USD' | 'EUR' | 'GBP' | 'CHF'
  isin?: string | null
  historical_source?: string | null
  quote_source?: string | null
}

export type CreatedMarket = CreateMarketPayload

export type CreatedInstrument = CreateInstrumentPayload & {
  market_id: string
  mic: string
}

export async function createMarket(payload: CreateMarketPayload): Promise<RequestResult<CreatedMarket>> {
  return requestWithMeta<CreatedMarket>('/stock/markets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function createInstrument(payload: CreateInstrumentPayload): Promise<RequestResult<CreatedInstrument>> {
  return requestWithMeta<CreatedInstrument>('/stock/instruments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// GET /stock/quotes/latest/bulk?mic=... — full quotes (price, change, volume, last_trade_at)
// Mirrors StockClient.get_all_quotes(mic) — returns a dict { symbol: payload }.
export type BulkQuote = {
  last_price?: string | number | null
  change_pct?: string | number | null
  volume?: number | null
  last_trade_at?: string | null
  last_price_fmt?: string | null
  change_pct_fmt?: string | null
  last_trade_date_fmt?: string | null
  last_trade_time_fmt?: string | null
  name?: string | null
  currency?: string | null
}

const amountFormatter = new Intl.NumberFormat('pl-PL', {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
})

const dateFormatter = new Intl.DateTimeFormat('pl-PL', {
  timeZone: WARSAW_TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

const timeFormatter = new Intl.DateTimeFormat('pl-PL', {
  timeZone: WARSAW_TZ,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function toFiniteNumber(value: string | number | null | undefined): number | null {
  if (value == null) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function formatAmount(value: number): string {
  return amountFormatter.format(value)
}

function formatChangePct(value: number): string {
  const abs = formatAmount(Math.abs(value)).replace(/\s/g, '')
  return value >= 0 ? `+${abs}%` : `−${abs}%`
}

function parseStockDateTime(value: string | null | undefined): Date | null {
  if (!value) return null

  const raw = value.trim()
  if (!raw) return null

  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`
  const parsed = new Date(normalized)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function normalizeBulkQuote(quote: BulkQuote): BulkQuote {
  const lastPrice = toFiniteNumber(quote.last_price)
  const changePct = toFiniteNumber(quote.change_pct)
  const tradeAt = parseStockDateTime(quote.last_trade_at)

  return {
    ...quote,
    last_price_fmt: quote.last_price_fmt ?? (lastPrice != null ? formatAmount(lastPrice) : null),
    change_pct_fmt: quote.change_pct_fmt ?? (changePct != null ? formatChangePct(changePct) : null),
    last_trade_date_fmt: quote.last_trade_date_fmt ?? (tradeAt ? dateFormatter.format(tradeAt) : null),
    last_trade_time_fmt: quote.last_trade_time_fmt ?? (tradeAt ? timeFormatter.format(tradeAt) : null),
  }
}

function normalizeBulkQuotes(quotes: Record<string, BulkQuote>): Record<string, BulkQuote> {
  return Object.fromEntries(
    Object.entries(quotes).map(([symbol, quote]) => [symbol, normalizeBulkQuote(quote)]),
  )
}

export async function getQuotesBulkResult(mic: string): Promise<RequestResult<Record<string, BulkQuote>>> {
  const qs = new URLSearchParams({ mic })
  const result = await requestWithMeta<Record<string, BulkQuote>>(`/stock/quotes/latest/bulk?${qs.toString()}`)
  if (!result.ok) return result

  return {
    ...result,
    data: normalizeBulkQuotes(result.data),
  }
}

export async function getQuotesBulk(mic: string): Promise<Record<string, BulkQuote>> {
  const result = await getQuotesBulkResult(mic)
  if (!result.ok) {
    logger.warn({ mic, status: result.status, error: result.error }, 'getQuotesBulk: API error')
    return {}
  }

  return result.data
}

export type QuoteRow = {
  symbol: string
  name: string | null
  lastPrice: number
  changePct: number
  volume: number
  lastPriceFmt: string
  changePctFmt: string
  lastTradeDateFmt: string | null
  lastTradeTimeFmt: string | null
  currency: string | null
}

export function processQuotes(raw: Record<string, BulkQuote>): QuoteRow[] {
  return Object.entries(raw).map(([symbol, q]) => ({
    symbol,
    name: q.name ?? null,
    lastPrice: q.last_price != null ? Number(q.last_price) : 0,
    changePct: q.change_pct != null ? Number(q.change_pct) : 0,
    volume: q.volume ?? 0,
    lastPriceFmt: q.last_price_fmt ?? '—',
    changePctFmt: q.change_pct_fmt ?? '—',
    lastTradeDateFmt: q.last_trade_date_fmt ?? null,
    lastTradeTimeFmt: q.last_trade_time_fmt ?? null,
    currency: q.currency ?? null,
  }))
}

export type QuoteBySymbol = {
  symbol: string
  price: string | number
  currency: string
  change_pct: string | number
}

type QuoteBySymbolResponse = QuoteBySymbol[] | { quotes?: QuoteBySymbol[] }

export type CeleryStatus = {
  enabled: boolean
  online: boolean
  workers: string[]
  detail: string
}

export type ManualIngestStart = {
  ok: boolean
  detail?: string
  job_id?: string
}

export type ManualIngestStatus = {
  state: 'idle' | 'running' | 'done' | 'error'
  detail?: string
  started_at?: string
  processed?: string | number
  quote_source_processed?: string | number
  quote_source_failed?: string | number
  quote_source_errors?: Array<{ symbol?: string; mic?: string; detail?: string }>
}

export type EquityReportApiResponse = {
  asset_class: 'equity'
  report: EquityReport
  available_periods: ReportPeriod[]
}

export type EquityReportResult = {
  assetClass: 'equity'
  report: EquityReport
  availablePeriods: ReportPeriod[]
}

export async function getCeleryStatus(): Promise<RequestResult<CeleryStatus>> {
  return requestWithMeta<CeleryStatus>('/stock/celery/status')
}

export async function startManualIngest(): Promise<RequestResult<ManualIngestStart>> {
  return requestWithMeta<ManualIngestStart>('/stock/ingest/start_manual', {
    method: 'POST',
  })
}

export async function getManualIngestStatus(): Promise<RequestResult<ManualIngestStatus>> {
  return requestWithMeta<ManualIngestStatus>('/stock/ingest/status')
}

export type CandleDay = {
  date_quote: string   // "YYYY-MM-DD"
  open: number
  high: number
  low: number
  close: number
  volume: number | null
}

export type SyncCandlesPayload = {
  date_from?: string | null
  date_to?: string | null
  return_all?: boolean
  overlap_days?: number
  include_items?: boolean
}

type StockSyncMeta = {
  symbol: string
  name: string
  instrument_id: string
  requested_url: string
  fetched_rows: number
  upserted_rows: number
  sync_start?: string | null
  sync_end?: string | null
}

type StockSyncResponse = {
  sync: StockSyncMeta
  items_included: boolean
  returned_count: number
  items?: CandleDay[] | null
}

export type SyncCandlesResult = {
  symbol: string
  name: string
  fetched_rows: number
  upserted_rows: number
  returned_count: number
  items: CandleDay[]
}

export type ImportCandlesPayload = SyncCandlesPayload & {
  filename?: string | null
  content_b64: string
}

function normalizeSyncCandlesResult(raw: StockSyncResponse): SyncCandlesResult {
  return {
    symbol: raw.sync.symbol,
    name: raw.sync.name,
    fetched_rows: raw.sync.fetched_rows,
    upserted_rows: raw.sync.upserted_rows,
    returned_count: raw.returned_count,
    items: raw.items ?? [],
  }
}

export async function syncDailyCandles(
  symbol: string,
  payload: SyncCandlesPayload,
): Promise<RequestResult<SyncCandlesResult>> {
  const result = await requestWithMeta<StockSyncResponse>(
    `/stock/instruments/${encodeURIComponent(symbol)}/candles/daily/sync`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )

  if (!result.ok) return result

  return {
    ...result,
    data: normalizeSyncCandlesResult(result.data),
  }
}

export async function importDailyCandlesCsv(
  symbol: string,
  payload: ImportCandlesPayload,
): Promise<RequestResult<SyncCandlesResult>> {
  const result = await requestWithMeta<StockSyncResponse>(
    `/stock/instruments/${encodeURIComponent(symbol)}/candles/daily/import_csv`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )

  if (!result.ok) return result

  return {
    ...result,
    data: normalizeSyncCandlesResult(result.data),
  }
}

function normalizeEquityReportResult(raw: EquityReportApiResponse): EquityReportResult {
  return {
    assetClass: raw.asset_class,
    report: raw.report,
    availablePeriods: raw.available_periods,
  }
}

export async function getEquityReport(
  mic: string,
  symbol: string,
  period?: string | null,
): Promise<RequestResult<EquityReportResult>> {
  const qs = new URLSearchParams()
  if (period?.trim()) qs.set('period', period.trim().toUpperCase())
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const result = await requestWithMeta<EquityReportApiResponse>(
    `/stock/reports/${encodeURIComponent(mic)}/${encodeURIComponent(symbol)}${suffix}`,
  )

  if (!result.ok) return result

  return {
    ...result,
    data: normalizeEquityReportResult(result.data),
  }
}

export async function getQuotesBySymbols(symbols: string[]): Promise<Record<string, QuoteBySymbol>> {
  if (!symbols.length) return {}
  try {
    const res = await fetch(`${BASE}/stock/quotes/latest/symbols`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ symbols }),
      cache: 'no-store',
    })
    if (!res.ok) {
      logger.warn({ status: res.status }, 'getQuotesBySymbols: API error')
      return {}
    }
    const data = await res.json() as QuoteBySymbolResponse
    const quotes = Array.isArray(data) ? data : (data.quotes ?? [])
    const out: Record<string, QuoteBySymbol> = {}
    for (const q of quotes) {
      out[q.symbol] = q
    }
    return out
  } catch (err) {
    logger.error({ err }, 'getQuotesBySymbols: request failed')
    return {}
  }
}
