'use client'

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { toast } from 'sonner'
import {
  BarChart2, TrendingUp, RefreshCw, Search, X, ChevronDown,
  CandlestickChart, LineChart, MousePointer2, Minus, Layers,
  Undo2, Save, Trash2, Upload, Check, Crosshair, Maximize2, Minimize2, Info,
} from 'lucide-react'
import type { CandleDay, SyncCandlesResult, VolumeZonesResponse } from '@/lib/api/stock'
import { DateTimePicker } from '@/components/ui/date-time-picker'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  buildDateIndexResolver,
  buildDirectionalEpisodeBoxSeries,
  buildDirectionalEpisodeOutcomeSeries,
  buildEvidenceBalanceSeries,
  buildVolumeZoneMarkArea,
  buildVolumeZoneMarkLine,
  buildZoneLevelMarkLine,
  buildZoneHoverSeries,
  buildPhaseHoverSeries,
  buildVolumeZoneProfileSeries,
  evidenceLabel,
  behaviorLabel,
  lifecycleLabel,
  marketRoleLabel,
  priceRelationLabel,
  qualityFailLabel,
  stateLabel,
  VOLUME_PROFILE_MODE_LABELS,
  type PhaseVisibility,
  type VolumeProfileToggle,
  type ZoneVisibility,
  type VolumeZoneChartOptions,
} from './volume-zones'

// ── Constants ──────────────────────────────────────────────────────────────────

const MIC_LABELS: Record<string, string> = { XWAR: 'GPW', XNCO: 'NewConnect', STCM: 'RAW', PLNC: 'PLN' }
const DEFAULT_MARKETS = [
  { mic: 'XWAR', name: 'GPW' },
  { mic: 'XNCO', name: 'NewConnect' },
  { mic: 'STCM', name: 'RAW' },
  { mic: 'PLNC', name: 'PLN' },
]
const CHART_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6',
  '#ef4444', '#06b6d4', '#f97316', '#84cc16',
]
const SMA_PERIODS = [7, 20, 50, 100, 200] as const

// ── Types ──────────────────────────────────────────────────────────────────────

type ChartType = 'candlestick' | 'line'
type Layout = 'separate' | 'combined'
type DateRange = '1M' | '3M' | '1Y' | 'ALL' | 'CUSTOM'
type AggInterval = 'D' | 'W' | 'M'
type DrawMode = 'cursor' | 'hline' | 'vline' | 'trend' | 'channel'
type LineScaleMode = 'price' | 'percent' | 'index100' | 'rangePercent'
type LineScaleDomain = { base: number | null; min: number | null; max: number | null }
type MarketOption = { mic: string; name: string }
type SelectedSeries = { key: string; mic: string; symbol: string; shortname?: string | null }

type AnnoStyle = { color: string; width: number }
type XAnchor = { date: string; offset?: number }
type XCoord = number | XAnchor
type Anno =
  | { id: string; type: 'trend';   x1: XCoord; y1: number; x2: XCoord; y2: number; style: AnnoStyle }
  | { id: string; type: 'hline';   y: number;  style: AnnoStyle }
  | { id: string; type: 'vline';   x: XCoord;  style: AnnoStyle }
  | { id: string; type: 'channel'; x1: XCoord; y1: number; x2: XCoord; y2: number; dy: number; style: AnnoStyle }

type XBucket = { label: string; start: number; end: number }
type XScaleContext = {
  rawDates: string[]
  buckets: XBucket[]
  dateToIndex: Map<string, number>
}
type GridRect = { x: number; y: number; width: number; height: number }
type ChartModel = {
  getComponent(name: string, index: number): { coordinateSystem: { getRect(): GridRect } }
}
type ChartLike = {
  convertFromPixel(finder: Record<string, number>, value: [number, number]): unknown
  convertToPixel(finder: Record<string, number>, value: [number, number]): unknown
  getDom?: () => HTMLElement | null
  getModel(): ChartModel
  getOption?: () => unknown
  getZr?: () => ZrLike | null
  on(eventName: string, handler: () => void): void
  setOption(option: unknown, opts?: unknown): void
}
type ZrPointerEvent = {
  event?: { offsetX: number; offsetY: number; button?: number }
  offsetX?: number
  offsetY?: number
  button?: number
}
type ZrLike = {
  on(eventName: string, handler: (event: ZrPointerEvent) => void): void
}

type EngineState = {
  chart: ChartLike
  xScale: XScaleContext
  annos: Anno[]
  selectedId: string | null
  mode: DrawMode | null
  stage: number
  start: { x: XAnchor; y: number } | null
  base: { x1: XAnchor; y1: number; x2: XAnchor; y2: number } | null
  dyPreview: number | null
  cursorPx: [number, number] | null
  drag: { id: string; part: string; startData: [number, number]; startRawX: number | null; startAnno: Record<string, unknown> } | null
  _raf: number | null
  crosshairOn: boolean
  _origTooltip: unknown
  _origAxisPointer: unknown
}

type Instrument = { symbol: string; shortname: string }
type SeriesData = { result: SyncCandlesResult; candles: CandleDay[]; selection: SelectedSeries; label: string }

function normalizeMic(value: string): string {
  return value.trim().toUpperCase()
}

function normalizeSymbol(value: string): string {
  return value.trim().toUpperCase()
}

function seriesKey(mic: string, symbol: string): string {
  return `${normalizeMic(mic)}:${normalizeSymbol(symbol)}`
}

function marketName(mic: string, markets: MarketOption[]): string {
  const normalizedMic = normalizeMic(mic)
  return MIC_LABELS[normalizedMic] ?? markets.find((market) => market.mic === normalizedMic)?.name ?? normalizedMic
}

function seriesLabel(selection: SelectedSeries, markets: MarketOption[]): string {
  return `${selection.symbol} · ${marketName(selection.mic, markets)}`
}

// ── Utilities ──────────────────────────────────────────────────────────────────

let _annoId = 0
function nextAnnoId(): string { return `a${Date.now().toString(36)}_${++_annoId}` }

function deepClone<T>(x: T): T {
  try { return JSON.parse(JSON.stringify(x)) as T } catch { return x }
}

function sma(data: number[], period: number): (number | null)[] {
  return data.map((_, i) => {
    if (i < period - 1) return null
    return data.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period
  })
}

function bollingerBands(closes: number[], period = 20, k = 2) {
  const mid = sma(closes, period)
  return mid.map((m, i) => {
    if (m === null || i < period - 1) return { upper: null, mid: null, lower: null }
    const slice = closes.slice(i - period + 1, i + 1)
    const std = Math.sqrt(slice.reduce((a, c) => a + (c - m) ** 2, 0) / period)
    return { upper: m + k * std, mid: m, lower: m - k * std }
  })
}

function emaSeries(values: number[], period: number): number[] {
  if (!values.length) return []
  const k = 2.0 / (period + 1.0)
  const r: number[] = [values[0]!]
  for (let i = 1; i < values.length; i++) r.push((values[i]! - r[i - 1]!) * k + r[i - 1]!)
  return r
}

function rsiSeries(values: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = new Array(period).fill(null)
  if (values.length <= period) return out
  let avgGain = 0, avgLoss = 0
  for (let i = 1; i <= period; i++) {
    const d = values[i]! - values[i - 1]!
    if (d > 0) avgGain += d; else avgLoss -= d
  }
  avgGain /= period; avgLoss /= period
  const calc = () => avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  out.push(calc())
  for (let i = period + 1; i < values.length; i++) {
    const d = values[i]! - values[i - 1]!
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period
    out.push(calc())
  }
  return out
}

type MacdResult = { macdLine: (number | null)[]; signalLine: (number | null)[]; histogram: (number | null)[] }

function macdSeries(values: number[], fast = 12, slow = 26, signal = 9): MacdResult {
  const nullArr = (): (number | null)[] => new Array(values.length).fill(null)
  if (values.length < slow) return { macdLine: nullArr(), signalLine: nullArr(), histogram: nullArr() }
  const fastEma = emaSeries(values, fast)
  const slowEma = emaSeries(values, slow)
  const rawMacd = fastEma.map((f, i) => f - slowEma[i]!)
  const rawSignal = emaSeries(rawMacd, signal)
  const mask = slow - 1
  const macdLine   = rawMacd.map((v, i) => i < mask ? null : v)
  const signalLine = rawSignal.map((v, i) => i < mask ? null : v)
  const histogram  = macdLine.map((m, i) => { const s = signalLine[i]; return m == null || s == null ? null : m - s })
  return { macdLine, signalLine, histogram }
}

function aggregateCandles(candles: CandleDay[], interval: AggInterval): CandleDay[] {
  if (interval === 'D') return candles
  const groups = new Map<string, CandleDay[]>()
  for (const c of candles) {
    let key: string
    if (interval === 'W') {
      key = weekBucketKey(c.date_quote)
    } else {
      key = monthBucketKey(c.date_quote)
    }
    const arr = groups.get(key)
    if (arr) arr.push(c)
    else groups.set(key, [c])
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, g]) => ({
    date_quote: key,
    open: g[0]!.open,
    high: Math.max(...g.map((c) => c.high)),
    low: Math.min(...g.map((c) => c.low)),
    close: g[g.length - 1]!.close,
    volume: g.some((c) => c.volume != null) ? g.reduce((s, c) => s + (c.volume ?? 0), 0) : null,
    period_start: g[0]!.date_quote,
    period_end: g[g.length - 1]!.date_quote,
  }))
}

function getDateRange(range: DateRange): { from: string | null; to: string | null } {
  if (range === 'ALL' || range === 'CUSTOM') return { from: null, to: null }
  const today = new Date()
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  const days = range === '1M' ? 30 : range === '3M' ? 90 : 365
  const from = new Date(today)
  from.setDate(today.getDate() - days)
  return { from: fmt(from), to: fmt(today) }
}

function parseCsv(text: string): CandleDay[] | null {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)

  if (lines.length === 0) return null

  const sample = lines.slice(0, 5).join('\n')
  const delimiter = sample.split(';').length > sample.split(',').length ? ';' : ','
  const candles: CandleDay[] = []
  const parseNumber = (raw: string): number | null => {
    const normalized = raw.trim().replace(/^"|"$/g, '').replace(/\s/g, '').replace(',', '.')
    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  }

  for (const line of lines) {
    const parts = line.split(delimiter).map((s) => s.trim().replace(/^"|"$/g, ''))
    if (parts.length < 5) continue
    const [dateRaw, openS, highS, lowS, closeS, volS] = parts
    if (!dateRaw || !openS || !highS || !lowS || !closeS) continue
    const date = dateRaw.slice(0, 10)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue
    const open = parseNumber(openS)
    const high = parseNumber(highS)
    const low = parseNumber(lowS)
    const close = parseNumber(closeS)
    if (open === null || high === null || low === null || close === null) continue
    const volume = volS ? parseNumber(volS) : null
    candles.push({
      date_quote: date,
      open,
      high,
      low,
      close,
      volume: volume === null ? null : Math.trunc(volume),
    })
  }
  return candles.length > 0 ? candles.sort((a, b) => a.date_quote.localeCompare(b.date_quote)) : null
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function weekBucketKey(date: string): string {
  const d = new Date(date + 'T00:00:00Z')
  const dow = d.getUTCDay()
  const diff = dow === 0 ? -6 : 1 - dow
  const mon = new Date(d)
  mon.setUTCDate(d.getUTCDate() + diff)
  return mon.toISOString().slice(0, 10)
}

function monthBucketKey(date: string): string {
  return date.slice(0, 7)
}

function intervalBucketKey(date: string, interval: AggInterval): string {
  if (interval === 'D') return date
  return interval === 'W' ? weekBucketKey(date) : monthBucketKey(date)
}

function buildXScaleContext(rawDates: string[], interval: AggInterval): XScaleContext {
  const dates = [...new Set(rawDates)].sort()
  const dateToIndex = new Map(dates.map((date, index) => [date, index]))

  if (interval === 'D') {
    return {
      rawDates: dates,
      dateToIndex,
      buckets: dates.map((label, index) => ({ label, start: index, end: index })),
    }
  }

  const buckets: XBucket[] = []
  for (const date of dates) {
    const index = dateToIndex.get(date)
    if (index == null) continue
    const label = intervalBucketKey(date, interval)
    const last = buckets[buckets.length - 1]
    if (last && last.label === label) last.end = index
    else buckets.push({ label, start: index, end: index })
  }

  return { rawDates: dates, buckets, dateToIndex }
}

function isXAnchor(value: XCoord): value is XAnchor {
  return typeof value === 'object' && value !== null && 'date' in value && typeof value.date === 'string'
}

function rawPosFromAnchor(anchor: XAnchor, ctx: XScaleContext): number | null {
  const index = ctx.dateToIndex.get(anchor.date)
  if (index == null) return null
  const offset = typeof anchor.offset === 'number' ? clamp(anchor.offset, -0.5, 0.5) : 0
  return clamp(index + offset, -0.5, ctx.rawDates.length - 0.5)
}

function rawPosFromCurrentX(x: number, ctx: XScaleContext): number | null {
  if (!ctx.buckets.length) return null
  const bucketIndex = clamp(Math.floor(x + 0.5), 0, ctx.buckets.length - 1)
  const bucket = ctx.buckets[bucketIndex]
  if (!bucket) return null
  const count = bucket.end - bucket.start + 1
  if (count <= 0) return null
  const local = clamp(x - (bucketIndex - 0.5), 0, 1)
  return clamp((bucket.start - 0.5) + local * count, -0.5, ctx.rawDates.length - 0.5)
}

function rawPosFromXCoord(x: XCoord, ctx: XScaleContext): number | null {
  return isXAnchor(x) ? rawPosFromAnchor(x, ctx) : rawPosFromCurrentX(x, ctx)
}

function anchorFromRawPos(rawPos: number, ctx: XScaleContext): XAnchor | null {
  if (!ctx.rawDates.length) return null
  const bounded = clamp(rawPos, -0.5, ctx.rawDates.length - 0.5)
  const index = clamp(Math.round(bounded), 0, ctx.rawDates.length - 1)
  const date = ctx.rawDates[index]
  if (!date) return null
  const offset = clamp(bounded - index, -0.5, 0.5)
  return Math.abs(offset) < 1e-6 ? { date } : { date, offset: Number(offset.toFixed(4)) }
}

function anchorFromCurrentX(x: number, ctx: XScaleContext): XAnchor | null {
  const rawPos = rawPosFromCurrentX(x, ctx)
  return rawPos == null ? null : anchorFromRawPos(rawPos, ctx)
}

function currentXFromRawPos(rawPos: number, ctx: XScaleContext): number | null {
  if (!ctx.buckets.length) return null
  const bounded = clamp(rawPos, -0.5, ctx.rawDates.length - 0.5)
  for (const [bucketIndex, bucket] of ctx.buckets.entries()) {
    const left = bucket.start - 0.5
    const right = bucket.end + 0.5
    if (bounded < left || bounded > right) continue
    const count = bucket.end - bucket.start + 1
    if (count <= 0) return null
    return (bucketIndex - 0.5) + ((bounded - left) / count)
  }
  const lastIndex = ctx.buckets.length - 1
  return lastIndex >= 0 ? lastIndex : null
}

function resolveXCoord(x: XCoord, ctx: XScaleContext): number | null {
  const rawPos = rawPosFromXCoord(x, ctx)
  return rawPos == null ? null : currentXFromRawPos(rawPos, ctx)
}

function normalizePersistedAnnotations(annos: Anno[], rawDates: string[], sourceInterval: AggInterval): Anno[] {
  const sourceScale = buildXScaleContext(rawDates, sourceInterval)
  const normalizeX = (x: XCoord): XCoord => {
    if (isXAnchor(x)) return x
    return anchorFromCurrentX(x, sourceScale) ?? x
  }

  return annos.map((anno) => {
    if (anno.type === 'trend') {
      return { ...anno, x1: normalizeX(anno.x1), x2: normalizeX(anno.x2) }
    }
    if (anno.type === 'vline') {
      return { ...anno, x: normalizeX(anno.x) }
    }
    if (anno.type === 'channel') {
      return { ...anno, x1: normalizeX(anno.x1), x2: normalizeX(anno.x2) }
    }
    return anno
  })
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        reject(new Error('Nie udało się zakodować pliku'))
        return
      }

      const commaIdx = result.indexOf(',')
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result)
    }
    reader.onerror = () => reject(reader.error ?? new Error('Nie udało się odczytać pliku'))
    reader.readAsDataURL(file)
  })
}

type PersistedChartState = {
  v: 1
  ts: number
  draw: Anno[]
  indicators: string[]
  interval: AggInterval
}

function legacyAnnotationsKey(sym: string): string {
  return `chart_annos_${sym}`
}

function chartStateKey(sym: string): string {
  return `chart_state_${sym}`
}

function saveChartState(sym: string, state: Omit<PersistedChartState, 'v' | 'ts'>) {
  try {
    const payload: PersistedChartState = {
      v: 1,
      ts: Date.now(),
      draw: state.draw,
      indicators: state.indicators,
      interval: state.interval,
    }
    localStorage.setItem(chartStateKey(sym), JSON.stringify(payload))
    localStorage.setItem(legacyAnnotationsKey(sym), JSON.stringify(state.draw))
  } catch { /* noop */ }
}

function loadLegacyAnnotations(sym: string): Anno[] {
  try {
    const s = localStorage.getItem(legacyAnnotationsKey(sym))
    return s ? (JSON.parse(s) as Anno[]) : []
  } catch {
    return []
  }
}

function loadChartState(sym: string): Omit<PersistedChartState, 'v' | 'ts'> {
  const fallback = {
    draw: loadLegacyAnnotations(sym),
    indicators: [],
    interval: 'D' as AggInterval,
  }

  try {
    const raw = localStorage.getItem(chartStateKey(sym))
    if (!raw) return fallback

    const parsed = JSON.parse(raw) as Partial<PersistedChartState>
    const draw = Array.isArray(parsed.draw) ? parsed.draw : fallback.draw
    const indicators = Array.isArray(parsed.indicators)
      ? parsed.indicators.filter((value): value is string => typeof value === 'string')
      : []
    const interval = parsed.interval === 'D' || parsed.interval === 'W' || parsed.interval === 'M'
      ? parsed.interval
      : 'D'

    return { draw, indicators, interval }
  } catch {
    return fallback
  }
}

// ── ECharts option builders (no drawings — rendered via graphic layer) ─────────

const AXIS_LABEL_STYLE = { color: 'rgba(255,255,255,0.35)', fontSize: 10 }
const SPLIT_LINE_STYLE = { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
const VOL_LABEL_FMT = (v: number) => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v)

function formatLineRawValue(value: number): string {
  const abs = Math.abs(value)
  if (abs > 0 && abs < 10) return value.toFixed(4)
  if (abs >= 1000) return value.toLocaleString('pl-PL', { maximumFractionDigits: 0 })
  return value.toFixed(2)
}

function formatLineValue(value: number, scaleMode: LineScaleMode): string {
  if (scaleMode === 'percent' || scaleMode === 'rangePercent') return `${value.toFixed(2)}%`
  if (scaleMode === 'index100') return value.toFixed(2)
  return value.toFixed(2)
}

function firstFiniteNonZero(values: (number | null)[]): number | null {
  const first = values.find((value) => value != null && Number.isFinite(value) && value !== 0)
  return first ?? null
}

function lineScaleDomain(values: (number | null)[]): LineScaleDomain {
  const finite = values.filter((value): value is number => value != null && Number.isFinite(value))
  return {
    base: firstFiniteNonZero(values),
    min: finite.length > 0 ? Math.min(...finite) : null,
    max: finite.length > 0 ? Math.max(...finite) : null,
  }
}

function fillInteriorGaps(values: (number | null)[]): (number | null)[] {
  const firstIdx = values.findIndex((value) => value != null && Number.isFinite(value))
  if (firstIdx === -1) return values
  let lastIdx = values.length - 1
  while (lastIdx >= 0 && (values[lastIdx] == null || !Number.isFinite(values[lastIdx]))) lastIdx -= 1

  let lastValue: number | null = null
  return values.map((value, index) => {
    if (index < firstIdx || index > lastIdx) return null
    if (value != null && Number.isFinite(value)) {
      lastValue = value
      return value
    }
    return lastValue
  })
}

function scaleLineValue(value: number | null, domain: LineScaleDomain, scaleMode: LineScaleMode): number | null {
  if (value == null || !Number.isFinite(value)) return null
  if (scaleMode === 'price') return value
  if (scaleMode === 'rangePercent') {
    if (domain.min == null || domain.max == null || !Number.isFinite(domain.min) || !Number.isFinite(domain.max)) return null
    if (domain.max === domain.min) return 50
    return ((value - domain.min) / (domain.max - domain.min)) * 100
  }
  const base = domain.base
  if (base == null || !Number.isFinite(base) || base === 0) return null
  if (scaleMode === 'percent') return ((value / base) - 1) * 100
  return (value / base) * 100
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function tooltipFormatter(params: any[]): string {
  if (!params?.length) return ''
  const date = params[0]?.axisValue ?? ''
  let html = `<div style="font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:4px">${date}</div>`
  for (const p of params) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if ((p as any).componentType === 'markLine') continue
    const v = p.value
    let display: string | null = null

    if (p.seriesType === 'candlestick' && Array.isArray(v)) {
      // Użyj p.encode żeby uzyskać prawidłowy indeks każdego pola — v[0..3] zależy od wersji ECharts
      const enc = (p.encode ?? {}) as Record<string, number[]>
      const idx = (key: string, fallback: number) => (enc[key]?.[0] ?? fallback)
      const get = (key: string, fallback: number): number => Number(v[idx(key, fallback)])
      const dot = `<span style="width:8px;height:8px;border-radius:50%;background:${String(p.color ?? '#999')};flex-shrink:0"></span>`
      const row = (label: string, val: number) =>
        `<div style="display:flex;align-items:center;gap:6px;margin-top:2px">${dot}<span style="color:rgba(255,255,255,0.6);min-width:80px">${label}</span><span style="color:#e2e8f0;font-weight:500">${Number.isFinite(val) ? val.toFixed(2) : '—'}</span></div>`
      html += row('Open',    get('open',    1))
            + row('Close',   get('close',   2))
            + row('Lowest',  get('lowest',  3))
            + row('Highest', get('highest', 4))
      continue
    } else if (p.seriesType === 'bar') {
      const n = Number(v)
      if (Number.isFinite(n) && n !== 0) display = p.seriesName === 'MACD Hist' ? n.toFixed(4) : VOL_LABEL_FMT(n)
    } else {
      // line / scatter etc.
      if (v == null) continue
      const data = (p.data ?? {}) as { value?: unknown; raw?: unknown; scaleMode?: unknown }
      const n = typeof v === 'number' ? v : Number(data.value)
      if (Number.isFinite(n)) {
        const scaleMode = data.scaleMode === 'percent' || data.scaleMode === 'rangePercent' || data.scaleMode === 'index100' || data.scaleMode === 'price'
          ? data.scaleMode
          : 'price'
        display = formatLineValue(n, scaleMode)
        const raw = Number(data.raw)
        if (scaleMode !== 'price' && Number.isFinite(raw)) {
          display += ` · ${formatLineRawValue(raw)}`
        }
      }
    }

    if (!display) continue
    html += `<div style="display:flex;align-items:center;gap:6px;margin-top:2px">
      <span style="width:8px;height:8px;border-radius:50%;background:${String(p.color ?? '#999')};flex-shrink:0"></span>
      <span style="color:rgba(255,255,255,0.6);min-width:80px">${String(p.seriesName)}</span>
      <span style="color:#e2e8f0;font-weight:500">${display}</span>
    </div>`
  }
  return html
}

const TOOLTIP_STYLE = {
  trigger: 'axis', axisPointer: { type: 'cross' },
  backgroundColor: 'rgba(15,23,42,0.9)', borderColor: 'rgba(255,255,255,0.1)',
  textStyle: { color: '#e2e8f0', fontSize: 12 },
  formatter: tooltipFormatter,
}

// Item-trigger tooltip used when the crosshair is OFF: overlay series (zones,
// phases, profile) show their own descriptions; series without a formatter
// (candles) show nothing. No cross axis pointer.
const ITEM_TOOLTIP_STYLE = {
  trigger: 'item', confine: true,
  backgroundColor: 'rgba(15,23,42,0.9)', borderColor: 'rgba(255,255,255,0.1)',
  textStyle: { color: '#e2e8f0', fontSize: 12 },
  formatter: () => '',
}
type GridLayout = {
  grids: object[]
  xAxisCount: number
  rsiGridIndex:  number | null
  macdGridIndex: number | null
  evidenceGridIndex: number | null
  volGridIndex:  number | null
  rsiYIndex:     number | null
  macdYIndex:    number | null
  evidenceYIndex: number | null
  volYIndex:     number | null
}

function buildGridLayout(showRsi: boolean, showMacd: boolean, showVolume: boolean, showEvidence = false): GridLayout {
  const H = { rsi: 17, macd: 17, evidence: 14, volume: 15 } as const
  const GAP = 2
  const subPanels = ([showRsi && 'rsi', showMacd && 'macd', showEvidence && 'evidence', showVolume && 'volume'] as const).filter(Boolean) as string[]
  const totalSubH = subPanels.reduce((a, p) => a + H[p as keyof typeof H], 0)
  const priceH = Math.max(30, 87 - totalSubH - subPanels.length * GAP)

  const grids: object[] = []
  const LEFT = 60, RIGHT = 16
  grids.push(subPanels.length === 0
    ? { left: LEFT, right: RIGHT, top: 40, bottom: 60 }
    : { left: LEFT, right: RIGHT, top: 40, height: `${priceH}%` })

  let topPct = 5 + priceH + GAP
  let gridIdx = 1
  let yIdx = 1

  let rsiGridIndex:  number | null = null, rsiYIndex:  number | null = null
  let macdGridIndex: number | null = null, macdYIndex: number | null = null
  let evidenceGridIndex: number | null = null, evidenceYIndex: number | null = null
  let volGridIndex:  number | null = null, volYIndex:  number | null = null

  if (showRsi) {
    rsiGridIndex = gridIdx++; rsiYIndex = yIdx++
    grids.push({ left: LEFT, right: RIGHT, top: `${Math.round(topPct)}%`, height: `${H.rsi}%` })
    topPct += H.rsi + GAP
  }
  if (showMacd) {
    macdGridIndex = gridIdx++; macdYIndex = yIdx++
    grids.push({ left: LEFT, right: RIGHT, top: `${Math.round(topPct)}%`, height: `${H.macd}%` })
    topPct += H.macd + GAP
  }
  if (showEvidence) {
    evidenceGridIndex = gridIdx++; evidenceYIndex = yIdx++
    grids.push({ left: LEFT, right: RIGHT, top: `${Math.round(topPct)}%`, height: `${H.evidence}%` })
    topPct += H.evidence + GAP
  }
  if (showVolume) {
    volGridIndex = gridIdx++; volYIndex = yIdx++
    grids.push({ left: LEFT, right: RIGHT, top: `${Math.round(topPct)}%`, height: `${H.volume}%` })
  }

  return { grids, xAxisCount: gridIdx, rsiGridIndex, rsiYIndex, macdGridIndex, macdYIndex, evidenceGridIndex, evidenceYIndex, volGridIndex, volYIndex }
}

const dataZoomOpt = (xAxisCount: number) => {
  const idx = Array.from({ length: xAxisCount }, (_, i) => i)
  return [
    { type: 'inside', xAxisIndex: idx, start: 60, end: 100 },
    { type: 'slider', xAxisIndex: idx, height: 20, bottom: 4, borderColor: 'rgba(255,255,255,0.1)', fillerColor: 'rgba(59,130,246,0.15)', handleStyle: { color: '#3b82f6' }, textStyle: { color: 'rgba(255,255,255,0.35)', fontSize: 9 } },
  ]
}

function buildCandlestickOption(
  symbol: string,
  candles: CandleDay[],
  showVolume: boolean,
  indicators: Set<string>,
  volumeZones: VolumeZonesResponse | null = null,
  volumeZoneOptions: VolumeZoneChartOptions = { showZones: false, showProfile: false, profileOpacity: 0.14 },
  crosshairOn = true,
): object {
  // Crosshair ON -> axis tooltip (cross + price). OFF -> item tooltips so the
  // overlay descriptions appear and overlays become hoverable; no cross.
  const interactiveOverlays = !crosshairOn
  const xs     = candles.map((c) => c.date_quote)
  const closes = candles.map((c) => Number(c.close))

  const showRsi  = indicators.has('rsi')
  const showMacd = indicators.has('macd')
  const showEvidence = Boolean(volumeZones?.timeline.length && volumeZoneOptions.showZones)
  const layout   = buildGridLayout(showRsi, showMacd, showVolume, showEvidence)
  const { rsiGridIndex, rsiYIndex, macdGridIndex, macdYIndex, evidenceGridIndex, evidenceYIndex, volGridIndex, volYIndex } = layout

  const xAxis: object[] = layout.grids.map((_, gi) => ({
    type: 'category', gridIndex: gi, data: xs, boundaryGap: true,
    axisLabel: gi === layout.grids.length - 1 ? { ...AXIS_LABEL_STYLE, hideOverlap: true } : { show: false },
    axisPointer: { label: { show: gi === layout.grids.length - 1 } },
  }))
  // Hidden x-axis on the price grid for the volume profile. It is NOT listed in
  // the dataZoom, so the profile stays pinned to the right edge and never gets
  // filtered out when the visible window excludes the latest candle.
  const profileXAxisIndex = xAxis.length
  xAxis.push({
    type: 'category', gridIndex: 0, data: xs, boundaryGap: true,
    show: false, axisLabel: { show: false }, axisTick: { show: false },
    axisLine: { show: false }, axisPointer: { show: false },
  })

  const yAxis: object[] = [
    { gridIndex: 0, scale: true, splitLine: SPLIT_LINE_STYLE, axisLabel: AXIS_LABEL_STYLE },
  ]
  if (rsiGridIndex !== null)  yAxis.push({ gridIndex: rsiGridIndex,  min: 0, max: 100, splitNumber: 2, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9 }, splitLine: SPLIT_LINE_STYLE })
  if (macdGridIndex !== null) yAxis.push({ gridIndex: macdGridIndex, scale: true,      splitNumber: 2, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9 }, splitLine: SPLIT_LINE_STYLE })
  if (evidenceGridIndex !== null) {
    const tl = volumeZones?.timeline ?? []
    const evidenceName = tl.length
      ? `Bilans dowodów — ${tl[0]!.date}–${tl[tl.length - 1]!.date}`
      : 'Bilans dowodów'
    yAxis.push({ gridIndex: evidenceGridIndex, min: -1, max: 1, splitNumber: 2, name: evidenceName, nameLocation: 'start', nameGap: 2, nameTextStyle: { color: 'rgba(255,255,255,0.35)', fontSize: 9, align: 'left' }, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9 }, splitLine: SPLIT_LINE_STYLE })
  }
  if (volGridIndex  !== null) yAxis.push({ gridIndex: volGridIndex,  splitNumber: 2, scale: true, splitLine: SPLIT_LINE_STYLE, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9, formatter: VOL_LABEL_FMT } })

  const zoneDateResolver = buildDateIndexResolver(candles)
  const volumeZoneMarkArea = buildVolumeZoneMarkArea(volumeZones, volumeZoneOptions, zoneDateResolver, candles.length - 1)
  const volumeZoneMarkLine = buildVolumeZoneMarkLine(volumeZones)

  const series: Record<string, unknown>[] = [
    {
      name: symbol, type: 'candlestick',
      xAxisIndex: 0, yAxisIndex: 0,
      z: 5,
      data: candles.map((c) => [c.open, c.close, c.low, c.high]),
      itemStyle: { color: '#10b981', color0: '#ef4444', borderColor: '#10b981', borderColor0: '#ef4444' },
      ...(volumeZoneMarkArea ? { markArea: volumeZoneMarkArea } : {}),
      ...(volumeZoneMarkLine ? { markLine: volumeZoneMarkLine } : {}),
    },
  ]

  for (const p of SMA_PERIODS) {
    if (!indicators.has(`sma-${p}`)) continue
    series.push({ name: `SMA ${p}`, type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: sma(closes, p), smooth: true, showSymbol: false, lineStyle: { width: 1.5, opacity: 0.9 } })
  }
  if (indicators.has('bb')) {
    const bb = bollingerBands(closes)
    series.push(
      { name: 'BB Upper', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: bb.map((b) => b.upper), showSymbol: false, lineStyle: { width: 1, opacity: 0.6 }, color: '#f59e0b' },
      { name: 'BB Mid',   type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: bb.map((b) => b.mid),   showSymbol: false, lineStyle: { width: 1, type: 'dashed', opacity: 0.5 }, color: '#f59e0b' },
      { name: 'BB Lower', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: bb.map((b) => b.lower), showSymbol: false, lineStyle: { width: 1, opacity: 0.6 }, color: '#f59e0b' },
    )
  }

  if (showRsi && rsiGridIndex !== null && rsiYIndex !== null) {
    series.push({
      name: 'RSI (14)', type: 'line',
      xAxisIndex: rsiGridIndex, yAxisIndex: rsiYIndex,
      data: rsiSeries(closes, 14),
      showSymbol: false,
      lineStyle: { width: 1.5, color: '#a78bfa' }, color: '#a78bfa',
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.18)', width: 1 },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        label: { show: true, formatter: (p: any) => String((p as { value: number }).value), color: 'rgba(255,255,255,0.25)', fontSize: 9 },
        data: [{ yAxis: 70 }, { yAxis: 30 }],
      },
    })
  }

  if (showMacd && macdGridIndex !== null && macdYIndex !== null) {
    const { macdLine, signalLine, histogram } = macdSeries(closes)
    series.push(
      {
        name: 'MACD Hist', type: 'bar',
        xAxisIndex: macdGridIndex, yAxisIndex: macdYIndex,
        data: histogram,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        itemStyle: { color: (params: any) => { const v = (params as { value: number | null }).value; return v != null && v >= 0 ? 'rgba(16,185,129,0.7)' : 'rgba(239,68,68,0.7)' } },
      },
      { name: 'MACD',   type: 'line', xAxisIndex: macdGridIndex, yAxisIndex: macdYIndex, data: macdLine,   showSymbol: false, lineStyle: { width: 1.2, color: '#3b82f6' }, color: '#3b82f6' },
      { name: 'Signal', type: 'line', xAxisIndex: macdGridIndex, yAxisIndex: macdYIndex, data: signalLine, showSymbol: false, lineStyle: { width: 1.2, color: '#f97316' }, color: '#f97316' },
    )
  }

  if (showVolume && volGridIndex !== null && volYIndex !== null) {
    series.push({ name: 'Volume', type: 'bar', xAxisIndex: volGridIndex, yAxisIndex: volYIndex, data: candles.map((c) => c.volume ?? 0), itemStyle: { color: 'rgba(99,102,241,0.4)' } })
  }
  const profileSeries = buildVolumeZoneProfileSeries(volumeZones, volumeZoneOptions, candles.length - 1, profileXAxisIndex, interactiveOverlays)
  if (profileSeries) series.push(profileSeries as Record<string, unknown>)
  // Dashed zone-level lines extending past the formation box (own overlay
  // series; the candlestick series already carries the confirm/invalidate line).
  const zoneLevelMarkLine = buildZoneLevelMarkLine(volumeZones, volumeZoneOptions, zoneDateResolver, candles.length - 1)
  if (zoneLevelMarkLine) {
    series.push({ name: 'Poziomy stref', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: [], showSymbol: false, silent: true, markLine: zoneLevelMarkLine })
  }
  const evidenceSeries = buildEvidenceBalanceSeries(candles, volumeZones, evidenceGridIndex, evidenceYIndex)
  if (evidenceSeries) series.push(evidenceSeries as Record<string, unknown>)
  // Directional A/D phases ride on their own overlay series (the candlestick
  // series already carries the zone markArea, and a series has only one).
  const phaseBoxes = buildDirectionalEpisodeBoxSeries(
    volumeZones,
    volumeZoneOptions,
    zoneDateResolver,
    candles.length - 1,
    candles,
    interactiveOverlays,
  )
  if (phaseBoxes) series.push(phaseBoxes as Record<string, unknown>)
  const phaseOutcome = buildDirectionalEpisodeOutcomeSeries(volumeZones, volumeZoneOptions, zoneDateResolver, candles)
  if (phaseOutcome) series.push(phaseOutcome as Record<string, unknown>)
  // Transparent hover overlays that provide per-zone / per-phase tooltips.
  const zoneHover = buildZoneHoverSeries(volumeZones, volumeZoneOptions, zoneDateResolver, candles.length - 1, interactiveOverlays)
  if (zoneHover) series.push(zoneHover as Record<string, unknown>)
  const phaseHover = buildPhaseHoverSeries(volumeZones, volumeZoneOptions, zoneDateResolver, candles.length - 1, interactiveOverlays, candles)
  if (phaseHover) series.push(phaseHover as Record<string, unknown>)

  return {
    backgroundColor: 'transparent', animation: false,
    tooltip: crosshairOn ? TOOLTIP_STYLE : ITEM_TOOLTIP_STYLE, legend: { show: false },
    axisPointer: { link: [{ xAxisIndex: 'all' }], show: crosshairOn },
    dataZoom: dataZoomOpt(layout.xAxisCount),
    grid: layout.grids,
    xAxis,
    yAxis,
    series,
  }
}

function buildLineOption(
  seriesMap: Map<string, CandleDay[]>, showVolume: boolean, indicators: Set<string>,
  crosshairOn = true,
  lineScaleMode: LineScaleMode = 'price',
): object {
  const allDates = [...new Set([...seriesMap.values()].flatMap((c) => c.map((d) => d.date_quote)))].sort()
  const series: Record<string, unknown>[] = []
  let colorIdx = 0

  for (const [sym, candles] of seriesMap) {
    const byDate = new Map(candles.map((c) => [c.date_quote, c]))
    const closes = fillInteriorGaps(allDates.map((d) => { const v = byDate.get(d)?.close; return v != null ? Number(v) : null }))
    const domain = lineScaleDomain(closes)
    const lineData = closes.map((value) => {
      const scaled = scaleLineValue(value, domain, lineScaleMode)
      return scaled == null ? null : { value: scaled, raw: value, scaleMode: lineScaleMode }
    })
    const color = CHART_COLORS[colorIdx++ % CHART_COLORS.length] ?? '#3b82f6'
    series.push({ name: sym, type: 'line', data: lineData, showSymbol: false, lineStyle: { width: 2, color }, color, connectNulls: true })

    const dateToIdx = new Map(candles.map((c, i) => [c.date_quote, i]))
    const candleCloses = candles.map((c) => Number(c.close))
    for (const p of SMA_PERIODS) {
      if (!indicators.has(`sma-${p}`)) continue
      const smaVals = sma(candleCloses, p)
      const smaFull = fillInteriorGaps(allDates.map((d) => { const i = dateToIdx.get(d); return i !== undefined ? smaVals[i] ?? null : null }))
      const smaData = smaFull.map((value) => {
        const scaled = scaleLineValue(value, domain, lineScaleMode)
        return scaled == null ? null : { value: scaled, raw: value, scaleMode: lineScaleMode }
      })
      series.push({ name: `${sym} SMA${p}`, type: 'line', data: smaData, showSymbol: false, lineStyle: { width: 1.5, type: 'dashed', color }, color, connectNulls: true })
    }
    if (indicators.has('bb') && seriesMap.size === 1) {
      const bb = bollingerBands(candleCloses)
      const mapBB = (arr: (number | null)[]) => {
        const bbRaw = fillInteriorGaps(allDates.map((d) => {
          const i = dateToIdx.get(d)
          return i !== undefined ? arr[i] ?? null : null
        }))
        return bbRaw.map((raw) => {
          const scaled = scaleLineValue(raw, domain, lineScaleMode)
          return scaled == null ? null : { value: scaled, raw, scaleMode: lineScaleMode }
        })
      }
      series.push(
        { name: 'BB Upper', type: 'line', data: mapBB(bb.map((b) => b.upper)), showSymbol: false, lineStyle: { width: 1, color: '#f59e0b', opacity: 0.6 }, color: '#f59e0b', connectNulls: true },
        { name: 'BB Lower', type: 'line', data: mapBB(bb.map((b) => b.lower)), showSymbol: false, lineStyle: { width: 1, color: '#f59e0b', opacity: 0.6 }, color: '#f59e0b', connectNulls: true },
      )
    }
  }

  const isSingle = seriesMap.size === 1
  const hasVol   = showVolume && isSingle
  const showRsi  = indicators.has('rsi')  && isSingle
  const showMacd = indicators.has('macd') && isSingle
  const layout   = buildGridLayout(showRsi, showMacd, hasVol)
  const { rsiGridIndex, rsiYIndex, macdGridIndex, macdYIndex, volGridIndex, volYIndex } = layout

  if (hasVol && volGridIndex !== null && volYIndex !== null) {
    const first = [...seriesMap][0]
    if (first) {
      const byDate = new Map(first[1].map((c) => [c.date_quote, c]))
      series.push({ name: 'Volume', type: 'bar', xAxisIndex: volGridIndex, yAxisIndex: volYIndex, data: allDates.map((d) => byDate.get(d)?.volume ?? 0), itemStyle: { color: 'rgba(99,102,241,0.4)' } })
    }
  }

  if (showRsi && rsiGridIndex !== null && rsiYIndex !== null) {
    const first = [...seriesMap.values()][0]
    if (first) {
      const rsiCloses = first.map((c) => Number(c.close))
      const rsiVals   = rsiSeries(rsiCloses, 14)
      const dateToIdx = new Map(first.map((c, i) => [c.date_quote, i]))
      const rsiAligned = allDates.map((d) => { const i = dateToIdx.get(d); return i !== undefined ? rsiVals[i] ?? null : null })
      series.push({
        name: 'RSI (14)', type: 'line',
        xAxisIndex: rsiGridIndex, yAxisIndex: rsiYIndex,
        data: rsiAligned, showSymbol: false,
        lineStyle: { width: 1.5, color: '#a78bfa' }, color: '#a78bfa',
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.18)', width: 1 },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          label: { show: true, formatter: (p: any) => String((p as { value: number }).value), color: 'rgba(255,255,255,0.25)', fontSize: 9 },
          data: [{ yAxis: 70 }, { yAxis: 30 }],
        },
      })
    }
  }

  if (showMacd && macdGridIndex !== null && macdYIndex !== null) {
    const first = [...seriesMap.values()][0]
    if (first) {
      const macdCloses = first.map((c) => Number(c.close))
      const { macdLine, signalLine, histogram } = macdSeries(macdCloses)
      const dateToIdx = new Map(first.map((c, i) => [c.date_quote, i]))
      const align = (arr: (number | null)[]) => allDates.map((d) => { const i = dateToIdx.get(d); return i !== undefined ? arr[i] ?? null : null })
      series.push(
        {
          name: 'MACD Hist', type: 'bar',
          xAxisIndex: macdGridIndex, yAxisIndex: macdYIndex,
          data: align(histogram),
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          itemStyle: { color: (params: any) => { const v = (params as { value: number | null }).value; return v != null && v >= 0 ? 'rgba(16,185,129,0.7)' : 'rgba(239,68,68,0.7)' } },
        },
        { name: 'MACD',   type: 'line', xAxisIndex: macdGridIndex, yAxisIndex: macdYIndex, data: align(macdLine),   showSymbol: false, lineStyle: { width: 1.2, color: '#3b82f6' }, color: '#3b82f6' },
        { name: 'Signal', type: 'line', xAxisIndex: macdGridIndex, yAxisIndex: macdYIndex, data: align(signalLine), showSymbol: false, lineStyle: { width: 1.2, color: '#f97316' }, color: '#f97316' },
      )
    }
  }

  const xAxis = layout.grids.map((_, gi) => ({
    type: 'category', gridIndex: gi, data: allDates, boundaryGap: false,
    axisLabel: gi === layout.grids.length - 1 ? { ...AXIS_LABEL_STYLE, hideOverlap: true } : { show: false },
    axisPointer: { label: { show: gi === layout.grids.length - 1 } },
  }))

  const yAxis: object[] = [
    {
      gridIndex: 0,
      scale: true,
      ...(lineScaleMode === 'rangePercent' ? { min: 0, max: 100 } : {}),
      splitLine: SPLIT_LINE_STYLE,
      axisLabel: lineScaleMode === 'price'
        ? AXIS_LABEL_STYLE
        : { ...AXIS_LABEL_STYLE, formatter: (value: number) => formatLineValue(value, lineScaleMode) },
    },
  ]
  if (rsiGridIndex  !== null) yAxis.push({ gridIndex: rsiGridIndex,  min: 0, max: 100, splitNumber: 2, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9 }, splitLine: SPLIT_LINE_STYLE })
  if (macdGridIndex !== null) yAxis.push({ gridIndex: macdGridIndex, scale: true,      splitNumber: 2, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9 }, splitLine: SPLIT_LINE_STYLE })
  if (volGridIndex  !== null) yAxis.push({ gridIndex: volGridIndex,  splitNumber: 2, scale: true, splitLine: SPLIT_LINE_STYLE, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9, formatter: VOL_LABEL_FMT } })

  return {
    backgroundColor: 'transparent', animation: false,
    tooltip: crosshairOn ? TOOLTIP_STYLE : { show: false },
    legend: seriesMap.size > 1 ? { top: 8, textStyle: { color: 'rgba(255,255,255,0.6)', fontSize: 11 } } : { show: false },
    axisPointer: { link: [{ xAxisIndex: 'all' }], show: crosshairOn },
    dataZoom: dataZoomOpt(layout.xAxisCount),
    grid: layout.grids,
    xAxis,
    yAxis,
    series,
  }
}

function gridRect(chart: ChartLike): GridRect | null {
  try {
    const grid = chart.getModel().getComponent('grid', 0)
    return grid.coordinateSystem.getRect()
  } catch { return null }
}

function getAllGridRects(chart: ChartLike): GridRect[] {
  const r: GridRect[] = []
  for (let i = 0; ; i++) {
    try {
      const g = chart.getModel().getComponent('grid', i) as { coordinateSystem: { getRect(): GridRect } }
      r.push(g.coordinateSystem.getRect())
    } catch { break }
  }
  return r
}

function toData(chart: ChartLike, px: [number, number]): [number, number] | null {
  try {
    const r = chart.convertFromPixel({ xAxisIndex: 0, yAxisIndex: 0 }, px)
    return Array.isArray(r) ? (r as [number, number]) : null
  } catch { return null }
}

function toPx(chart: ChartLike, data: [number, number]): [number, number] | null {
  try {
    const r = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, data)
    return Array.isArray(r) ? (r as [number, number]) : null
  } catch { return null }
}

function inRect(px: [number, number], rect: { x: number; y: number; width: number; height: number }): boolean {
  return px[0] >= rect.x && px[0] <= rect.x + rect.width && px[1] >= rect.y && px[1] <= rect.y + rect.height
}

function distToSegment(p: [number, number], a: [number, number], b: [number, number]): number {
  const dx = b[0] - a[0], dy = b[1] - a[1]
  if (dx === 0 && dy === 0) return Math.hypot(p[0] - a[0], p[1] - a[1])
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))
}

function pick(st: EngineState, px: [number, number]): { id: string; part: string } | null {
  const TH_LINE = 6, TH_HANDLE = 10
  let best: { id: string; part: string } | null = null
  let bestDist = 1e9
  for (const a of st.annos) {
    if (a.type === 'trend') {
      const x1 = resolveXCoord(a.x1, st.xScale)
      const x2 = resolveXCoord(a.x2, st.xScale)
      if (x1 == null || x2 == null) continue
      const p1 = toPx(st.chart, [x1, a.y1])
      const p2 = toPx(st.chart, [x2, a.y2])
      if (!p1 || !p2) continue
      if (Math.hypot(px[0] - p1[0], px[1] - p1[1]) < TH_HANDLE) return { id: a.id, part: 'p1' }
      if (Math.hypot(px[0] - p2[0], px[1] - p2[1]) < TH_HANDLE) return { id: a.id, part: 'p2' }
      const d = distToSegment(px, p1, p2)
      if (d < TH_LINE && d < bestDist) { best = { id: a.id, part: 'line' }; bestDist = d }
    }
    if (a.type === 'hline') {
      const mid = toData(st.chart, [0, 0])
      if (!mid) continue
      const yPx = toPx(st.chart, [mid[0], a.y])
      if (!yPx) continue
      const d = Math.abs(px[1] - yPx[1])
      if (d < TH_LINE && d < bestDist) { best = { id: a.id, part: 'line' }; bestDist = d }
    }
    if (a.type === 'vline') {
      const mid = toData(st.chart, [0, 0])
      if (!mid) continue
      const x = resolveXCoord(a.x, st.xScale)
      if (x == null) continue
      const xPx = toPx(st.chart, [x, mid[1]])
      if (!xPx) continue
      const d = Math.abs(px[0] - xPx[0])
      if (d < TH_LINE && d < bestDist) { best = { id: a.id, part: 'line' }; bestDist = d }
    }
    if (a.type === 'channel') {
      const x1 = resolveXCoord(a.x1, st.xScale)
      const x2 = resolveXCoord(a.x2, st.xScale)
      if (x1 == null || x2 == null) continue
      const p1 = toPx(st.chart, [x1, a.y1])
      const p2 = toPx(st.chart, [x2, a.y2])
      const pp1 = toPx(st.chart, [x1, a.y1 + a.dy])
      const pp2 = toPx(st.chart, [x2, a.y2 + a.dy])
      if (p1 && p2) {
        if (Math.hypot(px[0] - p1[0], px[1] - p1[1]) < TH_HANDLE) return { id: a.id, part: 'p1' }
        if (Math.hypot(px[0] - p2[0], px[1] - p2[1]) < TH_HANDLE) return { id: a.id, part: 'p2' }
        const d = distToSegment(px, p1, p2)
        if (d < TH_LINE && d < bestDist) { best = { id: a.id, part: 'base' }; bestDist = d }
      }
      if (pp1 && pp2) {
        const d = distToSegment(px, pp1, pp2)
        if (d < TH_LINE && d < bestDist) { best = { id: a.id, part: 'parallel' }; bestDist = d }
      }
    }
  }
  return best
}

function defaultAnnoStyle(): AnnoStyle { return { color: '#e2e8f0', width: 1.5 } }

function styleFor(st: EngineState, a: Anno): { stroke: string; lineWidth: number; opacity: number } {
  const s = a.style
  return { stroke: s.color, lineWidth: s.width + (st.selectedId === a.id ? 0.8 : 0), opacity: 0.95 }
}

function scheduleRender(st: EngineState): void {
  if (st._raf) return
  st._raf = requestAnimationFrame(() => { st._raf = null; renderGraphic(st) })
}

function renderGraphic(st: EngineState): void {
  const chart = st.chart
  const rectOrNull = gridRect(chart)
  if (!rectOrNull) return
  const rect: { x: number; y: number; width: number; height: number } = rectOrNull

  const allRects = getAllGridRects(chart)
  const topY    = allRects[0]?.y ?? rect.y
  const lastR   = allRects[allRects.length - 1] ?? rect
  const bottomY = lastR.y + lastR.height

  // Vline stops before the volume grid (volume is always last if present).
  // Query the current option to find the Volume series and its xAxisIndex.
  const vlineBottomY = (() => {
    if (allRects.length <= 1) return bottomY
    try {
      const opt = (chart.getOption?.() ?? {}) as Record<string, unknown>
      let series = opt.series
      if (Array.isArray(series) && series.length > 0 && Array.isArray(series[0])) series = series[0]
      if (!Array.isArray(series)) return bottomY
      const volS = (series as Array<Record<string, unknown>>).find(s => s.name === 'Volume')
      if (!volS || typeof volS.xAxisIndex !== 'number' || volS.xAxisIndex <= 0) return bottomY
      const prev = allRects[volS.xAxisIndex - 1]
      return prev ? prev.y + prev.height : bottomY
    } catch { return bottomY }
  })()

  const els: unknown[]      = []
  const vlineEls: unknown[] = []
  const labelEls: unknown[] = []

  function addLine(
    x1: number, y1: number, x2: number, y2: number,
    style: { stroke: string; lineWidth: number; opacity: number },
    dashed: boolean, showHandles: boolean, id: string, suffix: string,
  ) {
    const p1 = toPx(chart, [x1, y1])
    const p2 = toPx(chart, [x2, y2])
    if (!p1 || !p2) return
    const stl: Record<string, unknown> = { stroke: style.stroke, lineWidth: style.lineWidth, opacity: style.opacity }
    if (dashed) stl.lineDash = [6, 4]
    els.push({ id: `${id}:l:${suffix}`, type: 'line', silent: true, shape: { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1] }, style: stl })
    if (showHandles) {
      els.push({ id: `${id}:h1:${suffix}`, type: 'circle', silent: true, shape: { cx: p1[0], cy: p1[1], r: 5 }, style: { fill: style.stroke, opacity: 0.9 } })
      els.push({ id: `${id}:h2:${suffix}`, type: 'circle', silent: true, shape: { cx: p2[0], cy: p2[1], r: 5 }, style: { fill: style.stroke, opacity: 0.9 } })
    }
  }

  function addHLine(y: number, style: { stroke: string; lineWidth: number; opacity: number }, dashed: boolean, id: string) {
    const mid = toData(chart, [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5])
    if (!mid) return
    const p = toPx(chart, [mid[0], y])
    if (!p) return
    const stl: Record<string, unknown> = { stroke: style.stroke, lineWidth: style.lineWidth, opacity: style.opacity }
    if (dashed) stl.lineDash = [6, 4]
    els.push({ id: `${id}:hline`, type: 'line', silent: true, shape: { x1: rect.x, y1: p[1], x2: rect.x + rect.width, y2: p[1] }, style: stl })
  }

  function addVLine(x: number, style: { stroke: string; lineWidth: number; opacity: number }, dashed: boolean, id: string) {
    const mid = toData(chart, [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5])
    if (!mid) return
    const p = toPx(chart, [x, mid[1]])
    if (!p) return
    const stl: Record<string, unknown> = { stroke: style.stroke, lineWidth: style.lineWidth, opacity: style.opacity }
    if (dashed) stl.lineDash = [6, 4]
    vlineEls.push({ id: `${id}:vline`, type: 'line', silent: true, shape: { x1: p[0], y1: topY, x2: p[0], y2: vlineBottomY }, style: stl })
  }

  for (const a of st.annos) {
    const stl = styleFor(st, a)
    const sel = st.selectedId === a.id
    if (a.type === 'trend') {
      const x1 = resolveXCoord(a.x1, st.xScale)
      const x2 = resolveXCoord(a.x2, st.xScale)
      if (x1 != null && x2 != null) addLine(x1, a.y1, x2, a.y2, stl, false, sel, a.id, 'trend')
    } else if (a.type === 'hline') {
      addHLine(a.y, stl, false, a.id)
      const midH = toData(chart, [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5])
      if (midH) {
        const pxH = toPx(chart, [midH[0], a.y])
        if (pxH) {
          const LH = 18, LW = 72
          labelEls.push({
            id: `${a.id}:hlabel`,
            type: 'group',
            x: rect.x - LW - 2,
            y: Math.round(pxH[1] - LH / 2),
            children: [
              { type: 'rect', shape: { x: 0, y: 0, width: LW, height: LH, r: 3 }, style: { fill: 'rgba(15,23,42,0.95)', stroke: stl.stroke, lineWidth: 1 } },
              { type: 'text', x: LW / 2, y: LH / 2, style: { text: a.y.toFixed(2), fill: '#e2e8f0', fontSize: 11, textAlign: 'center', textVerticalAlign: 'middle' } },
            ],
          })
        }
      }
    } else if (a.type === 'vline') {
      const x = resolveXCoord(a.x, st.xScale)
      if (x != null) {
        const midV = toData(chart, [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5])
        if (midV) {
          const pxV = toPx(chart, [x, midV[1]])
          if (pxV) {
            const vstl: Record<string, unknown> = { stroke: stl.stroke, lineWidth: stl.lineWidth, opacity: stl.opacity }
            const LH = 18, LW = 84, LGAP = 3
            // Label sits just below the price chart — same position as original crosshair label
            const labelY = rect.y + rect.height + 4

            if (labelY < vlineBottomY) {
              // Label falls within the vline span — draw two segments with a gap
              vlineEls.push({ id: `${a.id}:vline_top`, type: 'line', silent: true, shape: { x1: pxV[0], y1: topY, x2: pxV[0], y2: labelY - LGAP }, style: vstl })
              vlineEls.push({ id: `${a.id}:vline_bot`, type: 'line', silent: true, shape: { x1: pxV[0], y1: labelY + LH + LGAP, x2: pxV[0], y2: vlineBottomY }, style: vstl })
            } else {
              vlineEls.push({ id: `${a.id}:vline`, type: 'line', silent: true, shape: { x1: pxV[0], y1: topY, x2: pxV[0], y2: vlineBottomY }, style: vstl })
            }

            if (isXAnchor(a.x)) {
              labelEls.push({
                id: `${a.id}:vlabel`,
                type: 'group',
                x: Math.round(pxV[0] - LW / 2),
                y: labelY,
                children: [
                  { type: 'rect', shape: { x: 0, y: 0, width: LW, height: LH, r: 3 }, style: { fill: 'rgba(15,23,42,0.95)', stroke: stl.stroke, lineWidth: 1 } },
                  { type: 'text', x: LW / 2, y: LH / 2, style: { text: a.x.date, fill: '#e2e8f0', fontSize: 11, textAlign: 'center', textVerticalAlign: 'middle' } },
                ],
              })
            }
          }
        }
      }
    } else if (a.type === 'channel') {
      const x1 = resolveXCoord(a.x1, st.xScale)
      const x2 = resolveXCoord(a.x2, st.xScale)
      if (x1 != null && x2 != null) {
        addLine(x1, a.y1, x2, a.y2, stl, false, sel, a.id, 'base')
        addLine(x1, a.y1 + a.dy, x2, a.y2 + a.dy, stl, false, false, a.id, 'par')
      }
    }
  }

  const pv = { stroke: '#94a3b8', lineWidth: 1, opacity: 0.75 }
  if (st.mode && st.cursorPx && inRect(st.cursorPx, rect)) {
    const d = toData(chart, st.cursorPx)
    if (d) {
      const currentAnchor = anchorFromCurrentX(d[0], st.xScale)
      const currentX = currentAnchor ? (resolveXCoord(currentAnchor, st.xScale) ?? d[0]) : d[0]
      if (st.mode === 'trend' && st.stage === 1 && st.start) {
        const startX = resolveXCoord(st.start.x, st.xScale)
        if (startX != null) addLine(startX, st.start.y, currentX, d[1], pv, true, false, '__pv__', 't')
      }
      if (st.mode === 'hline') addHLine(d[1], pv, true, '__pv__')
      if (st.mode === 'vline') addVLine(currentX, pv, true, '__pv__')
      if (st.mode === 'channel') {
        if (st.stage === 1 && st.start) {
          const startX = resolveXCoord(st.start.x, st.xScale)
          if (startX != null) addLine(startX, st.start.y, currentX, d[1], pv, true, false, '__pv__', 'c1')
        } else if (st.stage === 2 && st.base) {
          const b = st.base
          const baseX1 = resolveXCoord(b.x1, st.xScale)
          const baseX2 = resolveXCoord(b.x2, st.xScale)
          if (baseX1 != null && baseX2 != null) {
            addLine(baseX1, b.y1, baseX2, b.y2, pv, true, false, '__pv__', 'cb')
            const dx = baseX2 - baseX1
            const t = dx === 0 ? 0 : (currentX - baseX1) / dx
            st.dyPreview = d[1] - (b.y1 + t * (b.y2 - b.y1))
            addLine(baseX1, b.y1 + st.dyPreview, baseX2, b.y2 + st.dyPreview, pv, true, false, '__pv__', 'cp')
          }
        }
      }
    }
  }

  chart.setOption(
    {
      graphic: {
        elements: [
          {
            id: '__ng_draw_layer__',
            type: 'group',
            x: 0, y: 0,
            silent: true,
            clipPath: { type: 'rect', shape: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } },
            children: els,
          },
          {
            id: '__ng_vline_layer__',
            type: 'group',
            x: 0, y: 0,
            silent: true,
            clipPath: { type: 'rect', shape: { x: rect.x, y: topY, width: rect.width, height: vlineBottomY - topY } },
            children: vlineEls,
          },
          {
            id: '__ng_label_layer__',
            type: 'group',
            x: 0, y: 0,
            silent: true,
            children: labelEls,
          },
        ],
      },
    },
    { lazyUpdate: true, replaceMerge: ['graphic'] },
  )
}

let _ctxMenu: HTMLDivElement | null = null

function getCtxMenu(): HTMLDivElement | null {
  if (typeof window === 'undefined') return null
  if (_ctxMenu) return _ctxMenu
  _ctxMenu = document.createElement('div')
  Object.assign(_ctxMenu.style, {
    position: 'fixed', display: 'none', zIndex: '99999',
    background: '#0f172a', border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: '10px', boxShadow: '0 12px 30px rgba(0,0,0,0.55)',
    padding: '6px', fontFamily: 'system-ui, sans-serif', fontSize: '13px',
    minWidth: '190px', userSelect: 'none', color: '#e2e8f0',
  })
  document.body.appendChild(_ctxMenu)
  window.addEventListener('mousedown', (e) => {
    if (_ctxMenu?.style.display === 'block' && !_ctxMenu.contains(e.target as Node)) hideCtxMenu()
  }, true)
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideCtxMenu() }, true)
  return _ctxMenu
}

function hideCtxMenu(): void { if (_ctxMenu) _ctxMenu.style.display = 'none' }

function ctxItem(label: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement('button')
  b.textContent = label
  Object.assign(b.style, {
    display: 'block', width: '100%', textAlign: 'left',
    padding: '7px 10px', margin: '0', border: '0',
    background: 'transparent', cursor: 'pointer', borderRadius: '6px',
    color: 'inherit', fontSize: 'inherit',
  })
  b.addEventListener('mouseenter', () => { b.style.background = 'rgba(255,255,255,0.08)' })
  b.addEventListener('mouseleave', () => { b.style.background = 'transparent' })
  b.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); onClick() })
  return b
}

function ctxSep(): HTMLDivElement {
  const d = document.createElement('div')
  d.style.cssText = 'height:1px;background:rgba(255,255,255,0.1);margin:4px 0;'
  return d
}

function ctxLabel(text: string): HTMLDivElement {
  const d = document.createElement('div')
  d.textContent = text
  d.style.cssText = 'padding:4px 10px;font-size:11px;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:0.05em;'
  return d
}

function showCtxMenu(st: EngineState, annoId: string, clientX: number, clientY: number, onRender: () => void): void {
  const menu = getCtxMenu()
  if (!menu) return
  hideCtxMenu()
  const a = st.annos.find((x) => x.id === annoId)
  if (!a) return

  menu.innerHTML = ''
  menu.appendChild(ctxItem('Usuń', () => {
    st.annos = st.annos.filter((x) => x.id !== annoId)
    if (st.selectedId === annoId) st.selectedId = null
    hideCtxMenu(); onRender()
  }))
  menu.appendChild(ctxSep())
  menu.appendChild(ctxLabel('Kolor'))
  const COLORS: [string, string][] = [
    ['Biały', '#e2e8f0'], ['Niebieski', '#3b82f6'], ['Zielony', '#10b981'],
    ['Czerwony', '#ef4444'], ['Fioletowy', '#8b5cf6'], ['Żółty', '#fbbf24'],
  ]
  for (const [name, c] of COLORS) {
    menu.appendChild(ctxItem(`● ${name}`, () => { a.style = { ...a.style, color: c }; hideCtxMenu(); onRender() }))
  }
  menu.appendChild(ctxSep())
  menu.appendChild(ctxLabel('Grubość'))
  for (const w of [1, 1.5, 2, 3] as const) {
    menu.appendChild(ctxItem(`• ${w}px`, () => { a.style = { ...a.style, width: w }; hideCtxMenu(); onRender() }))
  }

  const vw = window.innerWidth, vh = window.innerHeight
  menu.style.left = `${Math.min(clientX, vw - 210)}px`
  menu.style.top  = `${Math.min(clientY, vh - 320)}px`
  menu.style.display = 'block'
}

function attachDrawEngine(
  chart: unknown,
  savedAnnotos: Anno[],
  xScale: XScaleContext,
  cbs: { onStageChange: (s: number) => void; onModeReset: () => void },
): EngineState {
  const c = chart as ChartLike
  const zr = c.getZr?.()
  if (!zr) throw new Error('no ZRender')

  const opt = (c.getOption?.() ?? {}) as Record<string, unknown>
  const st: EngineState = {
    xScale,
    chart: c, annos: savedAnnotos, selectedId: null,
    mode: null, stage: 0, start: null, base: null, dyPreview: null,
    cursorPx: null, drag: null, _raf: null,
    crosshairOn: true,
    _origTooltip: deepClone(opt.tooltip),
    _origAxisPointer: deepClone(opt.axisPointer),
  }

  c.on('dataZoom', () => scheduleRender(st))
  c.on('restore',  () => scheduleRender(st))
  c.on('finished', () => scheduleRender(st))
  window.addEventListener('resize', () => scheduleRender(st))

  zr.on('mousemove', (ev) => {
    const e = ev.event ?? ev
    st.cursorPx = [e.offsetX as number, e.offsetY as number]

    if (st.drag) {
      const cur = toData(c, st.cursorPx!)
      if (!cur) return
      const curAnchor = anchorFromCurrentX(cur[0], st.xScale)
      const curRawX = rawPosFromCurrentX(cur[0], st.xScale)
      const a = st.annos.find((x) => x.id === st.drag!.id)
      if (!a) return
      const dy = cur[1] - st.drag.startData[1]
      const base = st.drag.startAnno

      if (a.type === 'trend') {
        if (st.drag.part === 'p1' && curAnchor)       { a.x1 = curAnchor; a.y1 = cur[1] }
        else if (st.drag.part === 'p2' && curAnchor)  { a.x2 = curAnchor; a.y2 = cur[1] }
        else if (curRawX != null && st.drag.startRawX != null) {
          const dxRaw = curRawX - st.drag.startRawX
          const baseX1 = rawPosFromXCoord(base.x1 as XCoord, st.xScale)
          const baseX2 = rawPosFromXCoord(base.x2 as XCoord, st.xScale)
          if (baseX1 != null && baseX2 != null) {
            const nextX1 = anchorFromRawPos(baseX1 + dxRaw, st.xScale)
            const nextX2 = anchorFromRawPos(baseX2 + dxRaw, st.xScale)
            if (nextX1 && nextX2) {
              a.x1 = nextX1; a.y1 = (base.y1 as number) + dy
              a.x2 = nextX2; a.y2 = (base.y2 as number) + dy
            }
          }
        }
      }
      if (a.type === 'hline') a.y = cur[1]
      if (a.type === 'vline' && curAnchor) a.x = curAnchor
      if (a.type === 'channel') {
        if (st.drag.part === 'p1' && curAnchor)           { a.x1 = curAnchor; a.y1 = cur[1] }
        else if (st.drag.part === 'p2' && curAnchor)      { a.x2 = curAnchor; a.y2 = cur[1] }
        else if (st.drag.part === 'base' && curRawX != null && st.drag.startRawX != null) {
          const dxRaw = curRawX - st.drag.startRawX
          const baseX1 = rawPosFromXCoord(base.x1 as XCoord, st.xScale)
          const baseX2 = rawPosFromXCoord(base.x2 as XCoord, st.xScale)
          if (baseX1 != null && baseX2 != null) {
            const nextX1 = anchorFromRawPos(baseX1 + dxRaw, st.xScale)
            const nextX2 = anchorFromRawPos(baseX2 + dxRaw, st.xScale)
            if (nextX1 && nextX2) {
              a.x1 = nextX1; a.y1 = (base.y1 as number) + dy
              a.x2 = nextX2; a.y2 = (base.y2 as number) + dy
            }
          }
        }
        else if (st.drag.part === 'parallel') a.dy = (base.dy as number) + dy
      }
      scheduleRender(st)
      return
    }

    if (st.mode) scheduleRender(st)
  })

  zr.on('click', (ev) => {
    const e = ev.event ?? ev
    const px: [number, number] = [e.offsetX as number, e.offsetY as number]
    const rect = gridRect(c)
    if (!rect || !inRect(px, rect)) return

    if (!st.mode) {
      const hit = pick(st, px)
      st.selectedId = hit?.id ?? null
      hideCtxMenu()
      scheduleRender(st)
      return
    }

    const d = toData(c, px)
    if (!d) return
    const x = d[0], y = d[1]
    const xAnchor = anchorFromCurrentX(x, st.xScale)

    if (st.mode === 'hline') {
      const id = nextAnnoId()
      st.annos.push({ id, type: 'hline', y, style: defaultAnnoStyle() })
      st.selectedId = id; st.mode = null; st.stage = 0
      cbs.onStageChange(0); cbs.onModeReset(); scheduleRender(st); return
    }

    if (st.mode === 'vline') {
      if (!xAnchor) return
      const id = nextAnnoId()
      st.annos.push({ id, type: 'vline', x: xAnchor, style: defaultAnnoStyle() })
      st.selectedId = id; st.mode = null; st.stage = 0
      cbs.onStageChange(0); cbs.onModeReset(); scheduleRender(st); return
    }

    if (st.mode === 'trend') {
      if (!xAnchor) return
      if (st.stage === 0) {
        st.start = { x: xAnchor, y }; st.stage = 1; cbs.onStageChange(1)
      } else {
        const id = nextAnnoId()
        st.annos.push({ id, type: 'trend', x1: st.start!.x, y1: st.start!.y, x2: xAnchor, y2: y, style: defaultAnnoStyle() })
        st.selectedId = id; st.mode = null; st.stage = 0; st.start = null
        cbs.onStageChange(0); cbs.onModeReset()
      }
      scheduleRender(st); return
    }

    if (st.mode === 'channel') {
      if (!xAnchor) return
      if (st.stage === 0) {
        st.start = { x: xAnchor, y }; st.stage = 1; cbs.onStageChange(1)
      } else if (st.stage === 1) {
        st.base = { x1: st.start!.x, y1: st.start!.y, x2: xAnchor, y2: y }; st.stage = 2; cbs.onStageChange(2)
      } else if (st.stage === 2) {
        const dy = st.dyPreview ?? 0
        const id = nextAnnoId()
        st.annos.push({ id, type: 'channel', x1: st.base!.x1, y1: st.base!.y1, x2: st.base!.x2, y2: st.base!.y2, dy, style: defaultAnnoStyle() })
        st.selectedId = id; st.mode = null; st.stage = 0; st.start = null; st.base = null; st.dyPreview = null
        cbs.onStageChange(0); cbs.onModeReset()
      }
      scheduleRender(st); return
    }
  })

  zr.on('mousedown', (ev) => {
    const e = ev.event ?? ev
    if (e.button !== 0 || st.mode) return
    const px: [number, number] = [e.offsetX as number, e.offsetY as number]
    const rect = gridRect(c)
    if (!rect || !inRect(px, rect)) return
    const hit = pick(st, px)
    if (!hit) return
    const d = toData(c, px)
    if (!d) return
    const a = st.annos.find((x) => x.id === hit.id)
    if (!a) return
    st.selectedId = hit.id
    st.drag = {
      id: hit.id,
      part: hit.part,
      startData: d,
      startRawX: rawPosFromCurrentX(d[0], st.xScale),
      startAnno: deepClone(a) as Record<string, unknown>,
    }
    hideCtxMenu(); scheduleRender(st)
  })

  zr.on('mouseup', () => { st.drag = null })

  const dom = c.getDom?.() as HTMLElement | null
  if (dom) {
    dom.addEventListener('contextmenu', (e) => {
      e.preventDefault()
      if (st.mode) return
      const r = dom.getBoundingClientRect()
      const px: [number, number] = [e.clientX - r.left, e.clientY - r.top]
      const rect = gridRect(c)
      if (!rect || !inRect(px, rect)) return
      const hit = pick(st, px)
      if (!hit) { hideCtxMenu(); return }
      st.selectedId = hit.id
      scheduleRender(st)
      showCtxMenu(st, hit.id, e.clientX, e.clientY, () => scheduleRender(st))
    }, { passive: false })
  }

  window.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !st.mode) return
    st.mode = null; st.stage = 0; st.start = null; st.base = null; st.dyPreview = null
    cbs.onStageChange(0); cbs.onModeReset(); scheduleRender(st)
  })

  scheduleRender(st)
  return st
}

function SymbolChip({ symbol, color, onRemove }: { symbol: string; color: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-white/10 text-white/80" style={{ borderLeftColor: color, borderLeftWidth: 3 }}>
      {symbol}
      <button type="button" aria-label={`Usuń ${symbol}`} onClick={onRemove} className="text-white/30 hover:text-white transition-colors"><X className="w-3 h-3" /></button>
    </span>
  )
}

function InstrumentSearch({
  activeMic,
  instruments,
  selectedKeys,
  onAdd,
}: {
  activeMic: string
  instruments: Instrument[]
  selectedKeys: string[]
  onAdd: (instrument: Instrument) => void
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const lq = q.toLowerCase()
    return instruments
      .filter((i) => !selectedKeys.includes(seriesKey(activeMic, i.symbol)) && (i.symbol.toLowerCase().includes(lq) || (i.shortname ?? '').toLowerCase().includes(lq)))
  }, [activeMic, instruments, selectedKeys, q])

  return (
    <div ref={ref} className="relative">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/30" />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="Dodaj instrument…"
          className="w-full pl-7 pr-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50 min-w-[200px]"
        />
      </div>
      {open && filtered.length > 0 && (
        <div className="absolute top-full mt-1 left-0 w-72 z-50 bg-slate-900 border border-white/10 rounded-xl shadow-2xl py-1 max-h-80 overflow-y-auto">
          {filtered.map((i) => (
            <button
              key={i.symbol}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault()
                onAdd(i)
                setQ('')
                setOpen(false)
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-white/5 transition-colors">
              <span className="text-sm font-medium text-white w-16 flex-shrink-0">{i.symbol}</span>
              <span className="text-xs text-white/40 truncate">{i.shortname}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const INDICATOR_ITEMS = [
  ...SMA_PERIODS.map((p) => ({ key: `sma-${p}`, label: `SMA ${p}` })),
  { key: 'bb',   label: 'Bollinger Bands (20)' },
  { key: 'rsi',  label: 'RSI (14)' },
  { key: 'macd', label: 'MACD (12,26,9)' },
]

const LINE_SCALE_ITEMS: Array<{ key: LineScaleMode; label: string }> = [
  { key: 'rangePercent', label: 'Zakres 0-100%' },
  { key: 'index100', label: 'Indeks 100' },
  { key: 'percent', label: 'Zmiana %' },
  { key: 'price', label: 'Cena' },
]

type ZoneLayerItem = { key: string; label: string; checked: boolean; onToggle: () => void; disabled?: boolean }

function IndicatorDropdown({ indicators, onChange, zoneLayers }: {
  indicators: Set<string>
  onChange: (key: string) => void
  zoneLayers?: ZoneLayerItem[]
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const activeCount = INDICATOR_ITEMS.filter((i) => indicators.has(i.key)).length
    + (zoneLayers?.filter((z) => z.checked).length ?? 0)

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-lg border border-white/10 bg-slate-900/40 text-white/60 hover:text-white hover:border-white/20 transition-colors"
      >
        Wskaźniki
        {activeCount > 0 && <span className="px-1 py-px rounded bg-blue-600 text-white text-[10px] leading-none">{activeCount}</span>}
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute top-full mt-1 right-0 z-50 w-52 bg-slate-900 border border-white/10 rounded-xl shadow-2xl py-1">
          {INDICATOR_ITEMS.map((item) => (
            <button key={item.key} onMouseDown={(e) => { e.preventDefault(); onChange(item.key) }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs hover:bg-white/5 transition-colors text-white/70 hover:text-white">
              <span className={`w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center ${indicators.has(item.key) ? 'bg-blue-600 border-blue-500' : 'border-white/20'}`}>
                {indicators.has(item.key) && <Check className="w-2.5 h-2.5 text-white" />}
              </span>
              {item.label}
            </button>
          ))}
          {zoneLayers && zoneLayers.length > 0 && (
            <>
              <div className="my-1 border-t border-white/10" />
              <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-white/30">Strefy wolumenowe</div>
              {zoneLayers.map((item) => (
                <button key={item.key} disabled={item.disabled}
                  onMouseDown={(e) => { e.preventDefault(); if (!item.disabled) item.onToggle() }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs hover:bg-white/5 transition-colors text-white/70 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed">
                  <span className={`w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center ${item.checked ? 'bg-emerald-600 border-emerald-500' : 'border-white/20'}`}>
                    {item.checked && <Check className="w-2.5 h-2.5 text-white" />}
                  </span>
                  {item.label}
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}

const DRAW_TOOLS: { mode: DrawMode; icon: React.ReactNode; title: string }[] = [
  { mode: 'cursor',  icon: <MousePointer2 className="w-3.5 h-3.5" />,                 title: 'Kursor (Esc)' },
  { mode: 'hline',   icon: <Minus className="w-3.5 h-3.5" />,                         title: 'Linia pozioma' },
  { mode: 'vline',   icon: <Minus className="w-3.5 h-3.5 rotate-90" />,               title: 'Linia pionowa' },
  { mode: 'trend',   icon: <TrendingUp className="w-3.5 h-3.5" />,                     title: 'Linia trendu (2 kliknięcia)' },
  { mode: 'channel', icon: <Layers className="w-3.5 h-3.5" />,                         title: 'Kanał (3 kliknięcia)' },
]

const STAGE_HINTS = ['', 'Kliknij drugi punkt', 'Kliknij szerokość kanału']

function DrawToolbar({
  drawMode, onModeChange, stage,
  crosshairOn, onToggleCrosshair,
  onUndo, onSave, onClear,
}: {
  drawMode: DrawMode
  onModeChange: (m: DrawMode) => void
  stage: number
  crosshairOn: boolean
  onToggleCrosshair: () => void
  onUndo: () => void
  onSave: () => void
  onClear: () => void
}) {
  return (
    <div className="flex flex-col items-center gap-1 py-2 px-1.5 border-r border-white/5 bg-slate-900/20 flex-shrink-0">
      {DRAW_TOOLS.map((t) => (
        <button key={t.mode} title={t.title} onClick={() => onModeChange(t.mode)}
          className={`w-7 h-7 flex items-center justify-center rounded-md transition-colors ${
            drawMode === t.mode ? 'bg-blue-600 text-white' : 'text-white/30 hover:text-white hover:bg-white/5'
          }`}>
          {t.icon}
        </button>
      ))}

      {stage > 0 && (
        <div className="text-center px-1" title={STAGE_HINTS[stage]}>
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse inline-block" />
          <p className="text-[9px] text-amber-400/70 mt-0.5 leading-tight" style={{ writingMode: 'vertical-rl' }}>
            {STAGE_HINTS[stage]}
          </p>
        </div>
      )}

      <div className="w-5 h-px bg-white/10 my-1" />

      <button title="Crosshair" onClick={onToggleCrosshair}
        className={`w-7 h-7 flex items-center justify-center rounded-md transition-colors ${
          crosshairOn ? 'text-blue-400 bg-blue-600/20' : 'text-white/30 hover:text-white hover:bg-white/5'
        }`}>
        <Crosshair className="w-3.5 h-3.5" />
      </button>

      <div className="w-5 h-px bg-white/10 my-1" />

      <button title="Cofnij ostatni" onClick={onUndo} className="w-7 h-7 flex items-center justify-center rounded-md text-white/30 hover:text-white hover:bg-white/5 transition-colors">
        <Undo2 className="w-3.5 h-3.5" />
      </button>
      <button title="Zapisz rysunki" onClick={onSave} className="w-7 h-7 flex items-center justify-center rounded-md text-white/30 hover:text-white hover:bg-white/5 transition-colors">
        <Save className="w-3.5 h-3.5" />
      </button>
      <button title="Wyczyść wszystkie" onClick={onClear} className="w-7 h-7 flex items-center justify-center rounded-md text-white/30 hover:text-red-400 hover:bg-white/5 transition-colors">
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

type ChartPanelProps = {
  sym: string
  name: string
  chartType: ChartType
  showVolume: boolean
  lineScaleMode: LineScaleMode
  color: string
  candles?: CandleDay[]
  seriesMap?: Map<string, CandleDay[]>
  volumeZones?: VolumeZonesResponse | null
  volumeZoneOptions: VolumeZoneChartOptions
  zoneLayers?: ZoneLayerItem[]
  zoneControls?: ZoneControls
}

type ZoneControls = {
  showZones: boolean
  showProfile: boolean
  singleSymbol: boolean
  visibility: ZoneVisibility
  setVisibility: (v: ZoneVisibility) => void
  phaseVisibility: PhaseVisibility
  setPhaseVisibility: (v: PhaseVisibility) => void
  profileMode: VolumeProfileToggle
  setProfileMode: (m: VolumeProfileToggle) => void
  opacity: number
  setOpacity: (o: number) => void
}

function ChartPanel({ sym, name, chartType, showVolume, lineScaleMode, color, candles, seriesMap, volumeZones, volumeZoneOptions, zoneLayers, zoneControls }: ChartPanelProps) {
  const [interval, setIntervalState] = useState<AggInterval>('D')
  const [indicators, setIndicators] = useState<Set<string>>(new Set())
  const [zoneDetailsOpen, setZoneDetailsOpen] = useState(false)
  const [drawMode, setDrawMode] = useState<DrawMode>('cursor')
  const [stage, setStage] = useState(0)
  const [crosshairOn, setCrosshairOn] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const engineRef = useRef<EngineState | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return

    const timer = window.setTimeout(() => {
      const saved = loadChartState(sym)
      setIntervalState(saved.interval)
      setIndicators(new Set(saved.indicators))
    }, 0)

    return () => window.clearTimeout(timer)
  }, [sym])

  const toggleIndicator = useCallback((key: string) => {
    setIndicators((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }, [])

  const aggCandles = useMemo(
    () => (candles ? aggregateCandles(candles, interval) : null),
    [candles, interval],
  )
  const rawDates = useMemo(() => {
    if (candles) return candles.map((c) => c.date_quote)
    if (!seriesMap) return []
    return [...new Set([...seriesMap.values()].flatMap((items) => items.map((item) => item.date_quote)))].sort()
  }, [candles, seriesMap])
  const xScale = useMemo(() => buildXScaleContext(rawDates, interval), [rawDates, interval])
  const aggSeriesMap = useMemo(() => {
    if (!seriesMap) return null
    const m = new Map<string, CandleDay[]>()
    for (const [s, c] of seriesMap) m.set(s, aggregateCandles(c, interval))
    return m
  }, [seriesMap, interval])

  const option = useMemo(() => {
    if (aggCandles && chartType === 'candlestick') {
      return buildCandlestickOption(sym, aggCandles, showVolume, indicators, volumeZones ?? null, volumeZoneOptions, crosshairOn)
    }
    const sm = aggSeriesMap ?? (aggCandles ? new Map([[sym, aggCandles]]) : null)
    if (!sm) return null
    return buildLineOption(sm, showVolume, indicators, crosshairOn, lineScaleMode)
  }, [aggCandles, aggSeriesMap, chartType, showVolume, indicators, sym, volumeZones, volumeZoneOptions, crosshairOn, lineScaleMode])

  const setMode = useCallback((mode: DrawMode) => {
    setDrawMode(mode)
    const eng = engineRef.current
    if (eng) {
      eng.mode = mode === 'cursor' ? null : mode
      eng.stage = 0; eng.start = null; eng.base = null; eng.dyPreview = null
      hideCtxMenu(); setStage(0)
      scheduleRender(eng)
    }
  }, [])

  const toggleCrosshair = useCallback(() => {
    // Crosshair drives the built option (tooltip + axis pointer + overlay
    // hoverability), so toggling state triggers a rebuild.
    setCrosshairOn((v) => {
      const next = !v
      const eng = engineRef.current
      if (eng) eng.crosshairOn = next
      return next
    })
  }, [])

  const handleUndo = useCallback(() => {
    const eng = engineRef.current
    if (!eng) return
    eng.annos.pop()
    if (eng.selectedId && !eng.annos.some((a) => a.id === eng.selectedId)) eng.selectedId = null
    eng.mode = null; eng.stage = 0; eng.start = null; eng.base = null; eng.dyPreview = null
    setStage(0); setDrawMode('cursor'); hideCtxMenu(); scheduleRender(eng)
  }, [])

  const handleSave = useCallback(() => {
    const eng = engineRef.current
    if (!eng) return
    saveChartState(sym, {
      draw: eng.annos,
      indicators: [...indicators],
      interval,
    })
    toast.success('Rysunki i ustawienia wykresu zapisane')
  }, [indicators, interval, sym])

  const handleClear = useCallback(() => {
    const eng = engineRef.current
    if (!eng) return
    eng.annos = []; eng.selectedId = null
    eng.mode = null; eng.stage = 0; eng.start = null; eng.base = null; eng.dyPreview = null
    setStage(0); setDrawMode('cursor'); hideCtxMenu()
    saveChartState(sym, {
      draw: [],
      indicators: [...indicators],
      interval,
    })
    scheduleRender(eng)
  }, [indicators, interval, sym])

  useEffect(() => {
    const eng = engineRef.current
    if (!eng) return
    eng.xScale = xScale
    scheduleRender(eng)
  }, [xScale])

  const onChartReady = useCallback((instance: unknown) => {
    const savedState = typeof window !== 'undefined'
      ? loadChartState(sym)
      : { draw: [], indicators: [], interval: 'D' as AggInterval }
    const savedDraw = normalizePersistedAnnotations(savedState.draw, rawDates, savedState.interval)
    engineRef.current = attachDrawEngine(instance, savedDraw, xScale, {
      onStageChange: setStage,
      onModeReset: () => setDrawMode('cursor'),
    })
  }, [rawDates, sym, xScale])

  const aggCount = aggCandles?.length ?? (aggSeriesMap ? ([...aggSeriesMap.values()][0]?.length ?? 0) : 0)
  const intervalLabel = interval === 'D' ? 'świec' : interval === 'W' ? 'tyg.' : 'mies.'
  const chartH = isFullscreen ? 'calc(100vh - 52px)' : '520px'

  if (!option) return null

  return (
    <div className={
      isFullscreen
        ? 'fixed inset-0 z-50 bg-slate-950 flex flex-col overflow-hidden'
        : 'bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col'
    }>
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          {sym !== 'combined' && <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />}
          <span className="text-sm font-semibold text-white">{sym !== 'combined' ? sym : 'Porównanie'}</span>
          {name && name !== sym && <span className="text-xs text-white/40 truncate max-w-[200px]">{name}</span>}
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {/* Volume-zone controls (left of D/W/M) */}
          {chartType === 'candlestick' && zoneControls?.showZones && zoneControls.singleSymbol && (
            <>
              <div className="flex rounded-lg overflow-hidden border border-white/10" role="group" aria-label="Widoczność stref">
                {([['all', 'Wszystkie'], ['significant', 'Istotne'], ['active', 'Aktywne']] as const).map(([m, l]) => (
                  <button key={m} type="button" aria-pressed={zoneControls.visibility === m}
                    onClick={() => zoneControls.setVisibility(m)}
                    className={`px-2 py-1 text-[11px] font-medium transition-colors ${zoneControls.visibility === m ? 'bg-emerald-700 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                    {l}
                  </button>
                ))}
              </div>
              <div className="flex rounded-lg overflow-hidden border border-white/10" role="group" aria-label="Widoczność faz A/D">
                {([
                  ['significant', 'A/D historyczne'],
                  ['current', 'A/D bieżąca'],
                  ['debug', 'A/D debug'],
                ] as const).map(([m, l]) => (
                  <button key={m} type="button" aria-pressed={zoneControls.phaseVisibility === m}
                    onClick={() => zoneControls.setPhaseVisibility(m)}
                    className={`px-2 py-1 text-[11px] font-medium transition-colors ${zoneControls.phaseVisibility === m ? 'bg-cyan-700 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                    {l}
                  </button>
                ))}
              </div>
              {zoneControls.showProfile && (
                <div className="flex rounded-lg overflow-hidden border border-white/10" role="group" aria-label="Tryb profilu wolumenowego">
                  {([
                    ['raw', 'Est. wolumen'],
                    ['active', 'Aktywność'],
                    ['structural', 'Akceptacja'],
                  ] as const).map(([m, l]) => (
                    <button key={m} type="button" aria-pressed={zoneControls.profileMode === m}
                      onClick={() => zoneControls.setProfileMode(m)}
                      className={`px-2 py-1 text-[11px] font-medium transition-colors ${zoneControls.profileMode === m ? 'bg-slate-700 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                      {l}
                    </button>
                  ))}
                </div>
              )}
              {zoneControls.showProfile && (
                <label className="flex items-center gap-1 text-[11px] text-white/40" title="Krycie profilu i stref">
                  <span>Krycie</span>
                  <input type="range" min="0.08" max="0.34" step="0.02" value={zoneControls.opacity}
                    onChange={(e) => zoneControls.setOpacity(Number(e.target.value))}
                    className="w-16 accent-emerald-500" aria-label="Krycie profilu i stref" />
                </label>
              )}
              {volumeZones && (
                <button onClick={() => setZoneDetailsOpen(true)}
                  className="flex items-center gap-1.5 px-2 py-1 text-[11px] rounded-lg border border-white/10 bg-slate-900/40 text-white/60 hover:text-white hover:border-white/20 transition-colors">
                  <Info className="w-3.5 h-3.5" />Opis
                </button>
              )}
            </>
          )}
          {/* Interval D/W/M */}
          <div className="flex rounded-lg overflow-hidden border border-white/10">
            {(['D', 'W', 'M'] as AggInterval[]).map((iv) => (
              <button key={iv} onClick={() => setIntervalState(iv)}
                className={`px-2.5 py-1 text-xs font-medium transition-colors ${interval === iv ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                {iv}
              </button>
            ))}
          </div>
          {/* Indicators dropdown */}
          <IndicatorDropdown indicators={indicators} onChange={toggleIndicator} zoneLayers={zoneLayers} />
          {/* Candle count */}
          {aggCount > 0 && <span className="text-xs text-white/25">{aggCount} {intervalLabel}</span>}
          {/* Fullscreen toggle */}
          <button title={isFullscreen ? 'Wyjdź z pełnego ekranu (Esc)' : 'Pełny ekran'} onClick={() => setIsFullscreen((v) => !v)}
            className="w-7 h-7 flex items-center justify-center rounded-md text-white/30 hover:text-white hover:bg-white/5 transition-colors">
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* DrawToolbar + Chart */}
      <div className="flex flex-1 min-h-0">
        <DrawToolbar
          drawMode={drawMode}
          onModeChange={setMode}
          stage={stage}
          crosshairOn={crosshairOn}
          onToggleCrosshair={toggleCrosshair}
          onUndo={handleUndo}
          onSave={handleSave}
          onClear={handleClear}
        />
        <div className="flex-1 min-w-0">
          <ReactECharts
            option={option}
            style={{ height: chartH, width: '100%' }}
            opts={{ renderer: 'canvas' }}
            notMerge
            lazyUpdate={false}
            onChartReady={onChartReady}
          />
        </div>
      </div>
      {volumeZones && chartType === 'candlestick' && (
        <ZoneDetailsDialog
          open={zoneDetailsOpen}
          onOpenChange={setZoneDetailsOpen}
          vz={volumeZones}
          profileMode={volumeZoneOptions.profileMode ?? 'raw'}
        />
      )}
    </div>
  )
}

function ZoneDetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1 border-b border-white/5">
      <span className="text-white/40">{label}</span>
      <span className="text-white/80 text-right">{value}</span>
    </div>
  )
}

function ZoneDetailsDialog({ open, onOpenChange, vz, profileMode }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  vz: VolumeZonesResponse
  profileMode: VolumeProfileToggle
}) {
  const az = vz.active_zone
  const meta = profileMode === 'active' ? vz.active_profile_metadata : vz.structural_profile_metadata
  const sourceLabel = (s: string | null | undefined) =>
    s === 'BOTH' ? 'Strukturalny + aktywny' : s === 'STRUCTURAL' ? 'Strukturalny' : s === 'ACTIVE' ? 'Aktywny' : '—'
  const Row = ZoneDetailRow
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-md border-white/10 text-white sm:max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-white text-base">
            {az ? `Strefa ${az.price_low.toFixed(2)}–${az.price_high.toFixed(2)}` : 'Brak aktywnej strefy'}
          </DialogTitle>
        </DialogHeader>
        <div className="text-xs">
          {az ? (
            <>
              <Row label="Bieżący stan" value={stateLabel(vz.current_state.state)} />
              <Row label="Status epizodu" value={lifecycleLabel(az.lifecycle_status)} />
              {vz.current_state.price_relation && <Row label="Relacja ceny" value={priceRelationLabel(vz.current_state.price_relation)} />}
              {vz.current_state.current_market_role && <Row label="Rola" value={marketRoleLabel(vz.current_state.current_market_role)} />}
              <Row label="Historyczny podpis" value={behaviorLabel(az.episode_signature ?? az.behavior)} />
              <Row label="Źródło profilu" value={sourceLabel(az.source_profile)} />
              <Row label="Spójność" value={`${Math.round(az.consistency * 100)}%`} />
              <Row label="Aktywność" value={`${az.activity_equivalent_sessions.toFixed(1)} sesji`} />
              {az.confirmation_price != null && <Row label="Potwierdzenie" value={az.confirmation_price.toFixed(2)} />}
              {az.invalidation_price != null && <Row label="Unieważnienie" value={az.invalidation_price.toFixed(2)} />}
              {az.current_free_float_turnover != null && <Row label="Obrót FF" value={`${az.current_free_float_turnover.toFixed(2)}%`} />}
              <Row label="Wykryta" value={az.first_detected_at} />
              {az.quality_gate === 'FAILED' ? (
                <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200/70">
                  Wynik kierunkowy: {az.raw_directional_score ?? az.evidence_score}/100 · jakość próbki niewystarczająca
                  {az.quality_fail_reasons && az.quality_fail_reasons.length > 0 && (
                    <ul className="mt-1 list-disc list-inside text-amber-200/50">
                      {az.quality_fail_reasons.map((reason) => <li key={reason}>{qualityFailLabel(reason)}</li>)}
                    </ul>
                  )}
                </div>
              ) : (
                <Row label="Siła dowodów" value={`${az.raw_directional_score ?? az.evidence_score}/100`} />
              )}
              {az.evidence.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {az.evidence.slice(0, 6).map((item) => (
                    <span key={`${item.code}:${item.value}`} className="rounded border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[11px] text-white/55">
                      {evidenceLabel(item.code)}
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <Row label="Bieżący stan" value={stateLabel(vz.current_state.state)} />
              {vz.nearest_zone_above && <Row label="Najbliższy opór" value={`${vz.nearest_zone_above.price_low.toFixed(2)}–${vz.nearest_zone_above.price_high.toFixed(2)} (${lifecycleLabel(vz.nearest_zone_above.lifecycle_status)})`} />}
              {vz.nearest_zone_below && <Row label="Najbliższe wsparcie" value={`${vz.nearest_zone_below.price_low.toFixed(2)}–${vz.nearest_zone_below.price_high.toFixed(2)} (${lifecycleLabel(vz.nearest_zone_below.lifecycle_status)})`} />}
            </>
          )}
          <Row label="Free float" value={vz.data_quality.current_free_float_used && vz.data_quality.current_free_float_pct != null
            ? `${vz.data_quality.current_free_float_pct.toFixed(2)}%`
            : 'Brak w snapshotach raportu'} />
          <p className="mt-3 text-[10px] leading-relaxed text-white/30">
            Profil: {VOLUME_PROFILE_MODE_LABELS[profileMode]}
            {meta?.bin_count != null ? ` · ${meta.bin_count} binów` : ''}
            {meta?.history_start && meta?.history_end ? ` · ${meta.history_start}–${meta.history_end}` : ''}
            {' · '}alokacja: zakres dzienny low–high. Wolumen po cenie jest estymowany na podstawie dziennych świec OHLCV.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ImportCsvModal({ symbol, dateFrom, dateTo, returnAll, onImported, onClose }: {
  symbol: string
  dateFrom: string | null
  dateTo: string | null
  returnAll: boolean
  onImported: (result: SyncCandlesResult) => void
  onClose: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<CandleDay[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isImporting, setIsImporting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (nextFile: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string
      const parsed = parseCsv(text)
      if (!parsed) {
        setError('Nie udało się odczytać. Format: data,open,high,low,close[,volume]')
        setPreview(null)
        setFile(null)
      } else {
        setPreview(parsed)
        setError(null)
        setFile(nextFile)
      }
    }
    reader.onerror = () => {
      setError('Nie udało się odczytać pliku')
      setPreview(null)
      setFile(null)
    }
    reader.readAsText(nextFile)
  }

  const handleImport = useCallback(async () => {
    if (!file || !preview?.length) return

    setIsImporting(true)
    setError(null)

    try {
      const content_b64 = await fileToBase64(file)
      const res = await fetch('/api/stock/candles/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          filename: file.name,
          content_b64,
          date_from: dateFrom,
          date_to: dateTo,
          return_all: returnAll,
        }),
      })

      const payload = await res.json().catch(() => ({})) as SyncCandlesResult & { error?: string }
      if (!res.ok) {
        const msg = payload.error ?? `Nie udało się zaimportować CSV dla ${symbol}`
        setError(msg)
        toast.error(msg)
        return
      }

      onImported(payload)
      toast.success(`${symbol}: zaimportowano ${payload.upserted_rows} wierszy`)
      onClose()
    } catch {
      const msg = 'Nie udało się wysłać pliku do backendu stock'
      setError(msg)
      toast.error(msg)
    } finally {
      setIsImporting(false)
    }
  }, [dateFrom, dateTo, file, onClose, onImported, preview, returnAll, symbol])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-lg mx-4 shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
          <div className="flex items-center gap-2"><Upload className="w-4 h-4 text-blue-400" /><h2 className="text-base font-semibold text-white">Import CSV</h2></div>
          <button onClick={onClose} className="text-white/40 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-xs text-white/40">Format: <code className="text-blue-400 bg-blue-500/10 px-1 rounded">data,open,high,low,close[,volume]</code></p>
          <div>
            <label className="block text-xs text-white/50 mb-1.5">Instrument</label>
            <div className="w-full px-3 py-2 text-sm bg-slate-800/60 border border-white/10 rounded-lg text-white">
              {symbol}
            </div>
            <p className="mt-1 text-[11px] text-white/35">
              Import zapisze świece dzienne dla istniejącego instrumentu w backendzie `stock`.
            </p>
          </div>
          <div onClick={() => fileRef.current?.click()} className="border-2 border-dashed border-white/15 rounded-xl p-6 text-center cursor-pointer hover:border-blue-500/40 transition-colors"
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}>
            <Upload className="w-6 h-6 text-white/20 mx-auto mb-2" />
            <p className="text-xs text-white/40">Przeciągnij plik CSV lub <span className="text-blue-400">kliknij</span></p>
            <input ref={fileRef} type="file" accept=".csv,.txt" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
          </div>
          {error && <p className="text-xs text-red-400 bg-red-500/5 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>}
          {preview && (
            <div>
              <p className="text-xs text-white/40 mb-2">{preview.length} wierszy — podgląd:</p>
              <div className="overflow-x-auto rounded-lg border border-white/5">
                <table className="w-full text-xs">
                  <thead><tr className="border-b border-white/10">{['Data','O','H','L','C','Vol'].map((h) => <th key={h} className="text-left px-2 py-1.5 text-white/30 font-medium">{h}</th>)}</tr></thead>
                  <tbody>
                    {preview.slice(0, 4).map((r) => (
                      <tr key={r.date_quote} className="border-b border-white/5 text-white/60">
                        <td className="px-2 py-1">{r.date_quote}</td><td className="px-2 py-1">{r.open}</td>
                        <td className="px-2 py-1">{r.high}</td><td className="px-2 py-1">{r.low}</td>
                        <td className="px-2 py-1">{r.close}</td><td className="px-2 py-1 text-white/30">{r.volume ?? '—'}</td>
                      </tr>
                    ))}
                    {preview.length > 4 && <tr><td colSpan={6} className="px-2 py-1 text-white/20 text-center">…i {preview.length - 4} więcej</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 px-5 py-4 border-t border-white/10">
          <button onClick={onClose} disabled={isImporting} className="px-4 py-2 text-xs text-white/50 hover:text-white disabled:opacity-50">Anuluj</button>
          <button disabled={!preview || !file || isImporting}
            onClick={() => void handleImport()}
            className="px-4 py-2 text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed">
            {isImporting ? 'Importowanie…' : `Importuj${preview ? ` (${preview.length})` : ''}`}
          </button>
        </div>
      </div>
    </div>
  )
}

type Props = {
  mic: string
  instruments: Instrument[]
  preselectedSymbol: string | null
  marketOptions?: MarketOption[]
}

export function ChartsPage({ mic, instruments, preselectedSymbol, marketOptions = DEFAULT_MARKETS }: Props) {
  const initialMic = normalizeMic(mic)
  const initialPreselectedSymbol = preselectedSymbol ? normalizeSymbol(preselectedSymbol) : null

  const [activeMic, setActiveMic] = useState(initialMic)
  const [activeInstruments, setActiveInstruments] = useState<Instrument[]>([])
  const [selectedSeries, setSelectedSeries] = useState<SelectedSeries[]>(
    initialPreselectedSymbol
      ? [{ key: seriesKey(initialMic, initialPreselectedSymbol), mic: initialMic, symbol: initialPreselectedSymbol }]
      : [],
  )
  const [chartType, setChartType]   = useState<ChartType>('candlestick')
  const [layout, setLayout]         = useState<Layout>('separate')
  const [lineScaleMode, setLineScaleMode] = useState<LineScaleMode>('rangePercent')
  const [showVolume, setShowVolume] = useState(true)
  const [dateRange, setDateRange]   = useState<DateRange>('ALL')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo]     = useState('')
  const [syncing, setSyncing]       = useState(false)
  const [seriesData, setSeriesData] = useState<Map<string, SeriesData>>(new Map())
  const [volumeZonesBySymbol, setVolumeZonesBySymbol] = useState<Map<string, VolumeZonesResponse>>(new Map())
  const [volumeZoneError, setVolumeZoneError] = useState<string | null>(null)
  // Volume-zone indicators are opt-in (off when a chart opens).
  const [showVolumeZones, setShowVolumeZones] = useState(false)
  const [showZoneProfile, setShowZoneProfile] = useState(false)
  const [zoneProfileOpacity, setZoneProfileOpacity] = useState(0.14)
  const [profileMode, setProfileMode] = useState<VolumeProfileToggle>('raw')
  const [zoneVisibility, setZoneVisibility] = useState<ZoneVisibility>('significant')
  const [phaseVisibility, setPhaseVisibility] = useState<PhaseVisibility>('significant')
  const [status, setStatus]         = useState<string | null>(null)
  const [showCsvModal, setShowCsvModal] = useState(false)
  const markets = useMemo(() => {
    const normalized = marketOptions
      .map((market) => ({
        mic: normalizeMic(market.mic),
        name: market.name.trim(),
      }))
      .filter((market) => market.mic)

    return normalized.length > 0 ? normalized : DEFAULT_MARKETS
  }, [marketOptions])
  const selectedKeys = useMemo(() => selectedSeries.map((selection) => selection.key), [selectedSeries])
  const visibleInstruments = normalizeMic(activeMic) === normalizeMic(mic) ? instruments : activeInstruments

  useEffect(() => {
    let cancelled = false
    const normalizedActiveMic = normalizeMic(activeMic)
    const normalizedRouteMic = normalizeMic(mic)

    if (normalizedActiveMic === normalizedRouteMic) {
      return
    }

    const qs = new URLSearchParams({ mic: normalizedActiveMic })
    void fetch(`/api/stock/instruments?${qs.toString()}`, {
      headers: { Accept: 'application/json' },
    })
      .then(async (res) => {
        const payload = await res.json().catch(() => []) as Instrument[] | { error?: string }
        if (cancelled) return
        if (!res.ok || !Array.isArray(payload)) {
          const msg = !Array.isArray(payload) && payload.error ? payload.error : 'Nie udało się pobrać instrumentów'
          toast.error(`${marketName(normalizedActiveMic, markets)}: ${msg}`)
          setActiveInstruments([])
          return
        }
        setActiveInstruments(payload)
      })
      .catch(() => {
        if (!cancelled) {
          toast.error(`${marketName(normalizedActiveMic, markets)}: błąd połączenia`)
          setActiveInstruments([])
        }
      })

    return () => {
      cancelled = true
    }
  }, [activeMic, markets, mic])

  const colorOf = useCallback((key: string): string => {
    const idx = [...seriesData.keys()].indexOf(key)
    const fallback = selectedKeys.indexOf(key)
    return CHART_COLORS[(idx >= 0 ? idx : fallback) % CHART_COLORS.length] ?? '#3b82f6'
  }, [seriesData, selectedKeys])

  const addInstrument = (instrument: Instrument) => {
    const symbol = normalizeSymbol(instrument.symbol)
    const normalizedMic = normalizeMic(activeMic)
    const key = seriesKey(normalizedMic, symbol)
    setSelectedSeries((prev) => (
      prev.some((selection) => selection.key === key)
        ? prev
        : [...prev, { key, mic: normalizedMic, symbol, shortname: instrument.shortname }]
    ))
  }
  const removeSymbol = (key: string) => {
    setSelectedSeries((p) => p.filter((selection) => selection.key !== key))
    setSeriesData((p) => { const m = new Map(p); m.delete(key); return m })
    setVolumeZonesBySymbol((p) => { const m = new Map(p); m.delete(key); return m })
  }

  const getRange = useCallback((): { from: string | null; to: string | null } => {
    if (dateRange === 'CUSTOM') return { from: customFrom ? customFrom.slice(0, 10) : null, to: customTo ? customTo.slice(0, 10) : null }
    return getDateRange(dateRange)
  }, [dateRange, customFrom, customTo])

  const openImportCsvModal = useCallback(() => {
    if (selectedSeries.length !== 1) {
      toast.warning('Wybierz dokładnie jeden instrument przed importem CSV')
      return
    }

    setShowCsvModal(true)
  }, [selectedSeries])

  const volumeZoneOptions = useMemo<VolumeZoneChartOptions>(() => ({
    showZones: showVolumeZones,
    showProfile: showVolumeZones && showZoneProfile,
    profileOpacity: zoneProfileOpacity,
    profileMode,
    zoneVisibility,
    phaseVisibility,
    showPhases: showVolumeZones && phaseVisibility !== 'off',
  }), [showVolumeZones, showZoneProfile, zoneProfileOpacity, profileMode, zoneVisibility, phaseVisibility])

  // Volume-zone layers are toggled from the Wskaźniki dropdown (per chart).
  const singleSymbol = selectedSeries.length === 1

  const zoneControls = useMemo<ZoneControls>(() => ({
    showZones: showVolumeZones,
    showProfile: showVolumeZones && showZoneProfile,
    singleSymbol,
    visibility: zoneVisibility,
    setVisibility: setZoneVisibility,
    phaseVisibility,
    setPhaseVisibility,
    profileMode,
    setProfileMode,
    opacity: zoneProfileOpacity,
    setOpacity: setZoneProfileOpacity,
  }), [showVolumeZones, showZoneProfile, singleSymbol, zoneVisibility, phaseVisibility, profileMode, zoneProfileOpacity])

  const fetchVolumeZonesForSeries = useCallback(async (selection: SelectedSeries, from: string | null, to: string | null): Promise<VolumeZonesResponse | null> => {
    const qs = new URLSearchParams({
      mic: selection.mic,
      symbol: selection.symbol,
      // Full page chart: return every detected zone (history); the backend still
      // marks up to three via highlighted_zone_ids.
      mode: 'full',
      include_timeline: 'true',
      max_zones: '3',
    })
    if (from) qs.set('date_from', from)
    if (to) qs.set('date_to', to)

    try {
      const res = await fetch(`/api/stock/analysis/volume-zones?${qs.toString()}`, {
        headers: { Accept: 'application/json' },
      })
      const payload = await res.json().catch(() => ({})) as VolumeZonesResponse & { error?: string }
      if (!res.ok) {
        const msg = payload.error ?? 'Nie udało się policzyć stref wolumenowych'
        setVolumeZoneError(msg)
        toast.error(`${seriesLabel(selection, markets)}: ${msg}`)
        return null
      }
      setVolumeZoneError(null)
      return payload
    } catch {
      const msg = 'Nie można połączyć się z analizą stref wolumenowych'
      setVolumeZoneError(msg)
      toast.error(`${seriesLabel(selection, markets)}: ${msg}`)
      return null
    }
  }, [markets])

  // Zones are opt-in; fetch them lazily from the toggle (event handler, not an
  // effect) the first time the layer is enabled for an already-loaded symbol.
  const ensureZonesFetched = useCallback(() => {
    if (selectedSeries.length !== 1) return
    const selection = selectedSeries[0]!
    if (volumeZonesBySymbol.has(selection.key) || !seriesData.has(selection.key)) return
    const { from, to } = getRange()
    void fetchVolumeZonesForSeries(selection, from, to).then((analysis) => {
      if (analysis) setVolumeZonesBySymbol((prev) => new Map(prev).set(selection.key, analysis))
    })
  }, [selectedSeries, volumeZonesBySymbol, seriesData, getRange, fetchVolumeZonesForSeries])

  const zoneLayers = useMemo<ZoneLayerItem[]>(() => [
    { key: 'vz-zones', label: 'Strefa wolumenowa', checked: showVolumeZones, disabled: !singleSymbol, onToggle: () => { if (!showVolumeZones) ensureZonesFetched(); setShowVolumeZones((v) => !v) } },
    { key: 'vz-profile', label: 'Profil ceny', checked: showZoneProfile, disabled: !singleSymbol || !showVolumeZones, onToggle: () => setShowZoneProfile((v) => !v) },
    { key: 'vz-phases', label: 'Fazy A/D', checked: phaseVisibility !== 'off', disabled: !singleSymbol || !showVolumeZones, onToggle: () => setPhaseVisibility((v) => v === 'off' ? 'significant' : 'off') },
  ], [showVolumeZones, showZoneProfile, phaseVisibility, singleSymbol, ensureZonesFetched])

  const syncAndRender = useCallback(async () => {
    if (!selectedSeries.length) { toast.warning('Wybierz przynajmniej jeden instrument'); return }
    setSyncing(true); setStatus('Synchronizacja danych…')
    const { from, to } = getRange()
    const newData = new Map<string, SeriesData>()
    const newVolumeZones = new Map<string, VolumeZonesResponse>()

    for (const selection of selectedSeries) {
      const label = seriesLabel(selection, markets)
      setStatus(`Pobieranie: ${label}…`)
      try {
        const res = await fetch('/api/stock/candles/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol: selection.symbol, date_from: from, date_to: to, return_all: !from, overlap_days: 7 }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({})) as { error?: string }
          toast.error(`${label}: ${err.error ?? 'Błąd sync'}`)
          continue
        }
        const result = await res.json() as SyncCandlesResult
        const candles = (result.items ?? []).sort((a, b) => a.date_quote.localeCompare(b.date_quote))
        newData.set(selection.key, { result, candles, selection, label })
      } catch {
        toast.error(`${label}: błąd połączenia`)
      }
    }

    const pointCount = [...newData.values()].reduce((a, d) => a + d.candles.length, 0)
    setSeriesData(newData)
    setVolumeZonesBySymbol(new Map())
    setSyncing(false)
    setStatus(newData.size > 0 ? `Dane gotowe — ${pointCount} punktów` : 'Brak danych')

    if (showVolumeZones && newData.size === 1 && selectedSeries.length === 1) {
      const selection = selectedSeries[0]!
      setStatus(`Dane gotowe — analiza stref: ${seriesLabel(selection, markets)}…`)
      const analysis = await fetchVolumeZonesForSeries(selection, from, to)
      if (analysis) newVolumeZones.set(selection.key, analysis)
      setVolumeZonesBySymbol(newVolumeZones)
      setStatus(newData.size > 0 ? `Gotowe — ${pointCount} punktów` : 'Brak danych')
    }
  }, [selectedSeries, getRange, fetchVolumeZonesForSeries, showVolumeZones, markets])

  const stableSyncRef = useRef<() => Promise<void>>(async () => {})

  useEffect(() => {
    stableSyncRef.current = syncAndRender
  }, [syncAndRender])

  useEffect(() => {
    if (!preselectedSymbol) return

    const timer = window.setTimeout(() => {
      void stableSyncRef.current()
    }, 0)

    return () => window.clearTimeout(timer)
  }, [preselectedSymbol])

  const handleCsvImported = useCallback((result: SyncCandlesResult) => {
    const currentSelection = selectedSeries[0] ?? {
      key: seriesKey(activeMic, result.symbol),
      mic: normalizeMic(activeMic),
      symbol: normalizeSymbol(result.symbol),
    }
    const label = seriesLabel(currentSelection, markets)
    const candles = (result.items ?? []).sort((a, b) => a.date_quote.localeCompare(b.date_quote))
    setSeriesData(new Map([[currentSelection.key, { result, candles, selection: currentSelection, label }]]))
    setSelectedSeries([currentSelection])
    setStatus(`Zaimportowano ${result.upserted_rows} wierszy dla ${label}`)
    const { from, to } = getRange()
    void fetchVolumeZonesForSeries(currentSelection, from, to).then((analysis) => {
      setVolumeZonesBySymbol(analysis ? new Map([[currentSelection.key, analysis]]) : new Map())
    })
  }, [activeMic, fetchVolumeZonesForSeries, getRange, markets, selectedSeries])

  const effectiveChartType: ChartType =
    chartType === 'candlestick' && layout === 'combined' && selectedSeries.length > 1 ? 'line' : chartType
  const effectiveLineScaleMode: LineScaleMode =
    effectiveChartType === 'line' && layout === 'combined' ? lineScaleMode : 'price'

  const chartEntries = useMemo(() => {
    if (!seriesData.size) return null
    if (layout === 'combined') {
      const combinedMap = new Map([...seriesData.values()].map(({ label, candles }) => [label, candles]))
      return [{ key: 'combined', sym: 'combined', name: 'Porównanie', seriesMap: combinedMap, candles: undefined as CandleDay[] | undefined }]
    }
    return [...seriesData.entries()].map(([key, { candles, result, label }]) => ({
      key, sym: label, name: result.name ?? label,
      candles, seriesMap: undefined as Map<string, CandleDay[]> | undefined,
    }))
  }, [seriesData, layout])

  return (
    <div className="px-4 py-4">
      <div className="max-w-screen-2xl mx-auto space-y-4">

        {/* Header */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
                <BarChart2 className="w-4 h-4 text-blue-400" />
              </div>
              <h1 className="text-xl font-semibold text-white">Wykresy</h1>
            </div>
            {status && (
              <span className={`text-xs px-3 py-1 rounded-lg border ${syncing ? 'bg-blue-500/10 border-blue-500/20 text-blue-300' : 'bg-slate-700/40 border-white/10 text-white/40'}`}>
                {syncing && <RefreshCw className="w-3 h-3 inline mr-1.5 animate-spin" />}{status}
              </span>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl p-4 space-y-3">
          {/* Row 1: market + symbols */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-48">
              <Select value={activeMic} onValueChange={(value) => setActiveMic(normalizeMic(value))}>
                <SelectTrigger
                  aria-label="Market"
                  className="h-8 w-full border-white/10 bg-slate-900 text-xs font-medium text-white/75 hover:bg-slate-900 hover:text-white focus-visible:border-blue-500/50"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-white/10 text-white">
                {markets.map((market) => (
                  <SelectItem key={market.mic} value={market.mic} className="text-xs text-white/80 focus:bg-white/10 focus:text-white">
                    {MIC_LABELS[market.mic] ?? market.name ?? market.mic}
                  </SelectItem>
                ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {selectedSeries.map((selection) => (
                <SymbolChip key={selection.key} symbol={seriesLabel(selection, markets)} color={colorOf(selection.key)} onRemove={() => removeSymbol(selection.key)} />
              ))}
            </div>
            <InstrumentSearch activeMic={activeMic} instruments={visibleInstruments} selectedKeys={selectedKeys} onAdd={addInstrument} />
          </div>

          {/* Row 2: chart options + date range */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-lg overflow-hidden border border-white/10">
                <button onClick={() => setChartType('candlestick')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${chartType === 'candlestick' ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                  <CandlestickChart className="w-3.5 h-3.5" />Świecowy
                </button>
                <button onClick={() => setChartType('line')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${chartType === 'line' ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                  <LineChart className="w-3.5 h-3.5" />Liniowy
                </button>
              </div>
              <div className="flex rounded-lg overflow-hidden border border-white/10">
                {(['separate', 'combined'] as Layout[]).map((l) => (
                  <button key={l} onClick={() => setLayout(l)}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${layout === l ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                    {l === 'separate' ? 'Osobno' : 'Nakładany'}
                  </button>
                ))}
              </div>
              {effectiveChartType === 'line' && layout === 'combined' && (
                <div className="flex rounded-lg overflow-hidden border border-white/10" role="group" aria-label="Skala porównania">
                  {LINE_SCALE_ITEMS.map((item) => (
                    <button key={item.key} type="button" onClick={() => setLineScaleMode(item.key)}
                      className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${lineScaleMode === item.key ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                      {item.label}
                    </button>
                  ))}
                </div>
              )}
              <button onClick={() => setShowVolume((v) => !v)}
                className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${showVolume ? 'bg-blue-600 border-blue-500 text-white' : 'bg-slate-900/40 border-white/10 text-white/50 hover:text-white hover:border-white/20'}`}>
                Wolumen
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-lg overflow-hidden border border-white/10">
                {(['1M', '3M', '1Y', 'ALL'] as const).map((r) => (
                  <button key={r} onClick={() => setDateRange(r)}
                    className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${dateRange === r ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                    {r === 'ALL' ? 'Wszystkie' : r}
                  </button>
                ))}
                <button onClick={() => setDateRange('CUSTOM')}
                  className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium transition-colors ${dateRange === 'CUSTOM' ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                  <ChevronDown className="w-3 h-3" />Własny
                </button>
              </div>
              {dateRange === 'CUSTOM' && (
                <>
                  <DateTimePicker value={customFrom} onChange={setCustomFrom} placeholder="Od" className="w-36" />
                  <span className="text-white/30 text-xs">–</span>
                  <DateTimePicker value={customTo} onChange={setCustomTo} placeholder="Do" className="w-36" />
                </>
              )}
              <button onClick={openImportCsvModal}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-white/10 bg-slate-900/40 text-white/60 hover:text-white hover:border-white/20 rounded-lg transition-colors">
                <Upload className="w-3.5 h-3.5" />Import CSV
              </button>
              <button onClick={() => void syncAndRender()} disabled={syncing || !selectedSeries.length}
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />Sync &amp; Render
              </button>
            </div>
          </div>

          {chartType === 'candlestick' && layout === 'combined' && selectedSeries.length > 1 && (
            <p className="text-xs text-amber-400/70 bg-amber-500/5 border border-amber-500/10 rounded-lg px-3 py-1.5">
              Tryb nakładany ze świecami jest dostępny tylko dla jednego symbolu — przełączono na liniowy.
            </p>
          )}
          {volumeZoneError && (
            <p className="text-xs text-amber-300/80 bg-amber-500/5 border border-amber-500/10 rounded-lg px-3 py-1.5">
              {volumeZoneError}
            </p>
          )}
        </div>

        {/* Empty state */}
        {!chartEntries && (
          <div className="bg-slate-800/40 border border-white/10 rounded-xl flex flex-col items-center justify-center py-20 gap-3">
            <TrendingUp className="w-10 h-10 text-white/10" />
            <p className="text-white/30 text-sm">Wybierz instrumenty i kliknij Sync &amp; Render</p>
            <p className="text-white/20 text-xs">Dane zostaną zsynchronizowane z serwisu giełdowego</p>
          </div>
        )}

        {/* Charts */}
        {chartEntries && chartEntries.map(({ key, sym, name, candles, seriesMap }) => (
          <ChartPanel key={key} sym={sym} name={name} chartType={effectiveChartType}
            showVolume={showVolume} lineScaleMode={effectiveLineScaleMode} color={colorOf(key)} candles={candles} seriesMap={seriesMap}
            volumeZones={key !== 'combined' ? volumeZonesBySymbol.get(key) ?? null : null}
            volumeZoneOptions={volumeZoneOptions}
            zoneLayers={zoneLayers}
            zoneControls={zoneControls}
          />
        ))}
      </div>

      {showCsvModal && selectedSeries.length === 1 && (
        <ImportCsvModal
          symbol={selectedSeries[0]!.symbol}
          dateFrom={getRange().from}
          dateTo={getRange().to}
          returnAll={!getRange().from}
          onImported={handleCsvImported}
          onClose={() => setShowCsvModal(false)}
        />
      )}
    </div>
  )
}
