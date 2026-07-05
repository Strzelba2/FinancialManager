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
  name?: string | null
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

export type StockServiceStatus = {
  available: boolean
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

export async function getStockServiceStatus(timeoutMs = 1500): Promise<StockServiceStatus> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(`${BASE}/healthz`, {
      cache: 'no-store',
      signal: controller.signal,
    })
    return { available: res.ok }
  } catch (err) {
    logger.warn({ err }, 'stock service health check failed')
    return { available: false }
  } finally {
    clearTimeout(timeout)
  }
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
  // Set by candle aggregation (weekly/monthly): the daily date range the
  // aggregated bucket covers. Absent for daily candles.
  period_start?: string
  period_end?: string
}

export type VolumeZoneEvidenceDirection = 'ACCUMULATION' | 'DISTRIBUTION' | 'NEUTRAL'
export type VolumeZoneBehavior =
  | 'DEMAND_ABSORPTION_PROXY'
  | 'SUPPLY_ABSORPTION_PROXY'
  | 'NEUTRAL_LIQUIDITY'
  | 'INSUFFICIENT_DIRECTIONAL_EVIDENCE'
  | 'BROAD_NEUTRAL_LIQUIDITY'
export type VolumeZoneStatus = 'ACTIVE' | 'CONFIRMED' | 'INVALIDATED' | 'DORMANT' | 'NEUTRAL'
export type VolumeZoneLifecycleStatus =
  | 'CANDIDATE'
  | 'ACTIVE'
  | 'CONFIRMED'
  | 'INVALIDATED'
  | 'CLOSED'
export type VolumeZoneMarketRole =
  | 'ACTIVE_DEMAND'
  | 'ACTIVE_SUPPLY'
  | 'FORMER_DEMAND_NOW_SUPPLY'
  | 'FORMER_SUPPLY_NOW_DEMAND'
  | 'HISTORICAL_SUPPORT'
  | 'HISTORICAL_RESISTANCE'
  | 'NEUTRAL_LIQUIDITY'
export type VolumeZonePriceRelation =
  | 'INSIDE_ZONE'
  | 'ABOVE_ZONE'
  | 'BELOW_ZONE'
  | 'APPROACHING_FROM_ABOVE'
  | 'APPROACHING_FROM_BELOW'
  | 'RETESTING_FROM_ABOVE'
  | 'RETESTING_FROM_BELOW'
  | 'BROKEN_UP'
  | 'BROKEN_DOWN'
export type VolumeZoneQualityGate = 'PASSED' | 'FAILED'
export type VolumeZoneSelectionReason =
  | 'INSIDE_ZONE'
  | 'WITHIN_ATR_DISTANCE'
  | 'RECENT_CONTACT'
  | 'INSIDE_AND_RECENT'
export type VolumeZoneDisplayRole =
  | 'ACTIVE'
  | 'NEAREST_DEMAND'
  | 'NEAREST_SUPPLY'
  | 'NEAREST_SUPPORT'
  | 'NEAREST_RESISTANCE'
  | 'STRONGEST_STRUCTURAL'
export type VolumeProfileMode = 'STRUCTURAL' | 'ACTIVE'
export type VolumeProfileWeighting = 'TIME_DECAY' | 'ACTIVITY_NORMALIZED'
export type VolumeZoneSourceProfile = 'STRUCTURAL' | 'ACTIVE' | 'BOTH'
export type DirectionalPhaseType = 'ACCUMULATION' | 'DISTRIBUTION'
export type DirectionalPhaseStatus = 'CANDIDATE' | 'ACTIVE' | 'CONFIRMED' | 'INVALIDATED' | 'CLOSED'

export type DirectionalPhase = {
  phase_id: string
  phase: DirectionalPhaseType
  estimated_start_at?: string | null
  base_end_at?: string | null
  candidate_at: string
  active_at: string | null
  ended_at: string
  confirmed_at?: string | null
  invalidated_at?: string | null
  price_low: number
  price_high: number
  center_price: number
  average_balance: number
  peak_balance: number
  cumulative_evidence: number
  session_count: number
  evidence_score: number
  status: DirectionalPhaseStatus
  confirmation_price: number | null
  invalidation_price: number | null
  linked_zone_ids: string[]
  setup_score?: number | null
  historical_outcome_score?: number | null
  subsequent_return_20?: number | null
  subsequent_return_60?: number | null
  maximum_favorable_excursion?: number | null
  maximum_adverse_excursion?: number | null
  expected_direction_return?: number | null
  opposite_move_penalty?: number | null
  outcome_lookahead_sessions?: number | null
  significance_score?: number | null
}
export type VolumeZoneState =
  | 'NEUTRAL'
  | 'ACCUMULATION_CANDIDATE'
  | 'ACCUMULATION_ACTIVE'
  | 'MARKUP'
  | 'FAILED_ACCUMULATION'
  | 'REACCUMULATION_CANDIDATE'
  | 'REACCUMULATION_ACTIVE'
  | 'DISTRIBUTION_CANDIDATE'
  | 'DISTRIBUTION_ACTIVE'
  | 'MARKDOWN'
  | 'FAILED_DISTRIBUTION'
  | 'REDISTRIBUTION_CANDIDATE'
  | 'REDISTRIBUTION_ACTIVE'
export type VolumeZonesMode = 'summary' | 'full' | 'backtest'

export type VolumeZoneEvidence = {
  code: string
  value: number | string
  direction: VolumeZoneEvidenceDirection
}

export type VolumeZoneEpisode = {
  episode_id: string
  zone_id: string
  estimated_start_date: string
  first_detected_at: string
  last_active_at: string
  direction_assigned_at: string | null
  confirmed_at: string | null
  invalidated_at: string | null
  effective_sessions: number
  session_count: number
  active_weeks: number
  allocated_volume: number
  weighted_volume: number
  activity_equivalent_sessions: number
  demand_absorption_evidence: number
  supply_absorption_evidence: number
  evidence_balance: number
  consistency: number
  direction_label: string
  evidence_score: number
  confidence: 'high' | 'medium' | 'low'
  status: VolumeZoneStatus
  confirmation_price: number | null
  invalidation_price: number | null
  evidence: VolumeZoneEvidence[]
}

export type VolumeZone = {
  zone_id: string
  price_low: number
  price_high: number
  center_price: number
  estimated_start_date: string
  first_detected_at: string
  last_active_at: string
  raw_volume: number
  weighted_volume: number
  activity_score: number
  activity_equivalent_sessions: number
  effective_sessions: number
  active_weeks: number
  dominant_session_share: number
  freshness_score: number
  status: VolumeZoneStatus
  behavior: VolumeZoneBehavior
  direction_label: string
  evidence_score: number
  evidence_balance: number
  consistency: number
  confirmation_price: number | null
  invalidation_price: number | null
  current_free_float_turnover: number | null
  current_free_float_turnover_is_estimate: boolean
  evidence: VolumeZoneEvidence[]
  episodes: VolumeZoneEpisode[]
  // Identity / lifecycle (additive; backend may omit on older payloads).
  detected_signature?: VolumeZoneBehavior | null
  episode_signature?: VolumeZoneBehavior | null
  directional_classification_allowed?: boolean
  lifecycle_status?: VolumeZoneLifecycleStatus | null
  raw_directional_score?: number | null
  quality_gate?: VolumeZoneQualityGate | null
  quality_fail_reasons?: string[]
  display_classification?: string | null
  display_priority?: number | null
  display_role?: VolumeZoneDisplayRole | null
  current_market_role?: VolumeZoneMarketRole | null
  source_profile?: VolumeZoneSourceProfile | null
  structural_strength?: number | null
  active_strength?: number | null
  current_relevance?: number | null
  top_session_dates?: string[]
}

export type VolumeProfileBin = {
  price_low: number
  price_high: number
  center_price: number
  raw_volume: number
  weighted_volume: number
  activity_score: number
  contributing_sessions?: number
}

export type VolumeProfileMetadata = {
  mode: VolumeProfileMode
  weighting: VolumeProfileWeighting
  half_life_sessions: number | null
  lookback_sessions: number | null
  bin_count: number
  bin_strategy: string
  relative_volume_window: number
  history_start: string | null
  history_end: string | null
}

export type VolumeZonesResponse = {
  symbol: string
  mic: string
  as_of: string
  calculation_version: string
  configuration_version: string
  data_quality: {
    ohlcv_interval: '1d'
    historical_free_float_available: boolean
    current_free_float_used: boolean
    current_free_float_pct: number | null
    current_free_float_as_of: string | null
    current_float_shares: number | null
    current_free_float_source: string | null
    confidence: 'high' | 'medium' | 'low'
    input_rows: number
    valid_rows: number
    excluded_rows: number
    duplicate_dates: string[]
    first_date: string | null
    last_date: string | null
    warnings: string[]
  }
  current_state: {
    state: VolumeZoneState
    evidence_score: number
    detected_at: string | null
    confirmation_price: number | null
    invalidation_price: number | null
    transition_reasons: string[]
    active_zone_id: string | null
    active_episode_id: string | null
    current_market_role?: VolumeZoneMarketRole | null
    price_relation?: VolumeZonePriceRelation | null
    selection_reason?: VolumeZoneSelectionReason | null
    distance_to_zone_percent?: number | null
    distance_to_zone_atr?: number | null
    sessions_since_last_contact?: number | null
    confirmation_hold_sessions?: number | null
    invalidation_hold_sessions?: number | null
  }
  active_zone: VolumeZone | null
  zones: VolumeZone[]
  profile: VolumeProfileBin[]
  structural_profile?: VolumeProfileBin[]
  structural_profile_metadata?: VolumeProfileMetadata | null
  active_profile_metadata?: VolumeProfileMetadata | null
  nearest_zone_above?: VolumeZone | null
  nearest_zone_below?: VolumeZone | null
  highlighted_zone_ids?: string[]
  directional_episodes?: DirectionalPhase[]
  resolved_directional_episodes?: DirectionalPhase[]
  major_directional_phases?: DirectionalPhase[]
  timeline: Array<{
    date: string
    state: VolumeZoneState
    evidence_score: number
    evidence_balance: number | null
    active_zone_id: string | null
    active_episode_id: string | null
    confirmation_price: number | null
    invalidation_price: number | null
    transition_reasons: string[]
  }>
  backtest: {
    evaluated_sessions: number
    detected_zones: number
    directional_zones: number
    neutral_zones: number
    candidate_states: number
    confirmed_states: number
    invalidated_states: number
    state_changes: number
    average_signal_delay_sessions: number | null
    benchmark_notes: string[]
  } | null
}

export type VolumeZonesOptions = {
  mode?: VolumeZonesMode
  dateFrom?: string | null
  dateTo?: string | null
  includeTimeline?: boolean
  maxZones?: number
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

export async function getVolumeZones(
  mic: string,
  symbol: string,
  options: VolumeZonesOptions = {},
): Promise<RequestResult<VolumeZonesResponse>> {
  const qs = new URLSearchParams()
  qs.set('mode', options.mode ?? 'summary')
  if (options.dateFrom) qs.set('date_from', options.dateFrom)
  if (options.dateTo) qs.set('date_to', options.dateTo)
  if (options.includeTimeline) qs.set('include_timeline', 'true')
  if (options.maxZones != null) qs.set('max_zones', String(options.maxZones))
  return requestWithMeta<VolumeZonesResponse>(
    `/stock/analysis/${encodeURIComponent(mic)}/${encodeURIComponent(symbol)}/volume-zones?${qs.toString()}`,
  )
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
