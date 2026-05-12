'use client'

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import ReactECharts from 'echarts-for-react'
import { toast } from 'sonner'
import {
  BarChart2, TrendingUp, RefreshCw, Search, X, ChevronDown,
  CandlestickChart, LineChart, MousePointer2, Minus, Layers,
  Undo2, Save, Trash2, Upload, Check, Crosshair, Maximize2, Minimize2,
} from 'lucide-react'
import type { CandleDay, SyncCandlesResult } from '@/lib/api/stock'
import { DateTimePicker } from '@/components/ui/date-time-picker'

// ── Constants ──────────────────────────────────────────────────────────────────

const MIC_LABELS: Record<string, string> = { XWAR: 'GPW', XNCO: 'NewConnect', STCM: 'RAW' }
const MICS = ['XWAR', 'XNCO', 'STCM'] as const
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
type SeriesData = { result: SyncCandlesResult; candles: CandleDay[] }

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
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function tooltipFormatter(params: any[]): string {
  if (!params?.length) return ''
  const date = params[0]?.axisValue ?? ''
  let html = `<div style="font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:4px">${date}</div>`
  for (const p of params) {
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
      if (Number.isFinite(n) && n !== 0) display = VOL_LABEL_FMT(n)
    } else {
      // line / scatter etc.
      if (v == null) continue
      const n = Number(v)
      if (Number.isFinite(n)) display = n.toFixed(2)
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
const dataZoomOpt = (hasVol: boolean) => [
  { type: 'inside', xAxisIndex: hasVol ? [0, 1] : [0], start: 60, end: 100 },
  { type: 'slider', xAxisIndex: hasVol ? [0, 1] : [0], height: 20, bottom: 4, borderColor: 'rgba(255,255,255,0.1)', fillerColor: 'rgba(59,130,246,0.15)', handleStyle: { color: '#3b82f6' }, textStyle: { color: 'rgba(255,255,255,0.35)', fontSize: 9 } },
]

function buildCandlestickOption(
  symbol: string, candles: CandleDay[], showVolume: boolean, indicators: Set<string>,
): object {
  const xs = candles.map((c) => c.date_quote)
  const closes = candles.map((c) => Number(c.close))

  const series: Record<string, unknown>[] = [
    {
      name: symbol, type: 'candlestick',
      data: candles.map((c) => [c.open, c.close, c.low, c.high]),
      itemStyle: { color: '#10b981', color0: '#ef4444', borderColor: '#10b981', borderColor0: '#ef4444' },
    },
  ]
  for (const p of SMA_PERIODS) {
    if (!indicators.has(`sma-${p}`)) continue
    series.push({ name: `SMA ${p}`, type: 'line', data: sma(closes, p), smooth: true, showSymbol: false, lineStyle: { width: 1.5, opacity: 0.9 } })
  }
  if (indicators.has('bb')) {
    const bb = bollingerBands(closes)
    series.push(
      { name: 'BB Upper', type: 'line', data: bb.map((b) => b.upper), showSymbol: false, lineStyle: { width: 1, opacity: 0.6 }, color: '#f59e0b' },
      { name: 'BB Mid',   type: 'line', data: bb.map((b) => b.mid),   showSymbol: false, lineStyle: { width: 1, type: 'dashed', opacity: 0.5 }, color: '#f59e0b' },
      { name: 'BB Lower', type: 'line', data: bb.map((b) => b.lower), showSymbol: false, lineStyle: { width: 1, opacity: 0.6 }, color: '#f59e0b' },
    )
  }
  if (showVolume) {
    series.push({ name: 'Volume', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: candles.map((c) => c.volume ?? 0), itemStyle: { color: 'rgba(99,102,241,0.4)' } })
  }

  return {
    backgroundColor: 'transparent', animation: false,
    tooltip: TOOLTIP_STYLE, legend: { show: false },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    dataZoom: dataZoomOpt(showVolume),
    grid: showVolume
      ? [{ left: 60, right: 16, top: 40, height: '55%' }, { left: 60, right: 16, top: '74%', height: '16%' }]
      : [{ left: 60, right: 16, top: 40, bottom: 60 }],
    xAxis: showVolume
      ? [
          { type: 'category', data: xs, axisLabel: { show: false }, boundaryGap: true },
          { type: 'category', gridIndex: 1, data: xs, boundaryGap: true, axisLabel: { ...AXIS_LABEL_STYLE, hideOverlap: true } },
        ]
      : [{ type: 'category', data: xs, boundaryGap: true, axisLabel: { ...AXIS_LABEL_STYLE, hideOverlap: true } }],
    yAxis: showVolume
      ? [
          { scale: true, splitLine: SPLIT_LINE_STYLE, axisLabel: AXIS_LABEL_STYLE },
          { gridIndex: 1, splitNumber: 2, scale: true, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9, formatter: VOL_LABEL_FMT } },
        ]
      : [{ scale: true, splitLine: SPLIT_LINE_STYLE, axisLabel: AXIS_LABEL_STYLE }],
    series,
  }
}

function buildLineOption(
  seriesMap: Map<string, CandleDay[]>, showVolume: boolean, indicators: Set<string>,
): object {
  const allDates = [...new Set([...seriesMap.values()].flatMap((c) => c.map((d) => d.date_quote)))].sort()
  const series: Record<string, unknown>[] = []
  let colorIdx = 0

  for (const [sym, candles] of seriesMap) {
    const byDate = new Map(candles.map((c) => [c.date_quote, c]))
    const closes = allDates.map((d) => { const v = byDate.get(d)?.close; return v != null ? Number(v) : null })
    const color = CHART_COLORS[colorIdx++ % CHART_COLORS.length] ?? '#3b82f6'
    series.push({ name: sym, type: 'line', data: closes, showSymbol: false, lineStyle: { width: 2, color }, color, connectNulls: false })

    const dateToIdx = new Map(candles.map((c, i) => [c.date_quote, i]))
    const candleCloses = candles.map((c) => Number(c.close))
    for (const p of SMA_PERIODS) {
      if (!indicators.has(`sma-${p}`)) continue
      const smaVals = sma(candleCloses, p)
      const smaFull = allDates.map((d) => { const i = dateToIdx.get(d); return i !== undefined ? smaVals[i] : null })
      series.push({ name: `${sym} SMA${p}`, type: 'line', data: smaFull, showSymbol: false, lineStyle: { width: 1.5, type: 'dashed', color }, color, connectNulls: false })
    }
    if (indicators.has('bb') && seriesMap.size === 1) {
      const bb = bollingerBands(candleCloses)
      const mapBB = (arr: (number | null)[]) => allDates.map((d) => { const i = dateToIdx.get(d); return i !== undefined ? arr[i] : null })
      series.push(
        { name: 'BB Upper', type: 'line', data: mapBB(bb.map((b) => b.upper)), showSymbol: false, lineStyle: { width: 1, color: '#f59e0b', opacity: 0.6 }, color: '#f59e0b', connectNulls: false },
        { name: 'BB Lower', type: 'line', data: mapBB(bb.map((b) => b.lower)), showSymbol: false, lineStyle: { width: 1, color: '#f59e0b', opacity: 0.6 }, color: '#f59e0b', connectNulls: false },
      )
    }
  }

  const hasVol = showVolume && seriesMap.size === 1
  if (hasVol) {
    const first = [...seriesMap][0]
    if (first) {
      const byDate = new Map(first[1].map((c) => [c.date_quote, c]))
      series.push({ name: 'Volume', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: allDates.map((d) => byDate.get(d)?.volume ?? 0), itemStyle: { color: 'rgba(99,102,241,0.4)' } })
    }
  }

  return {
    backgroundColor: 'transparent', animation: false,
    tooltip: TOOLTIP_STYLE,
    legend: seriesMap.size > 1 ? { top: 8, textStyle: { color: 'rgba(255,255,255,0.6)', fontSize: 11 } } : { show: false },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    dataZoom: dataZoomOpt(hasVol),
    grid: hasVol
      ? [{ left: 60, right: 16, top: 40, height: '55%' }, { left: 60, right: 16, top: '74%', height: '16%' }]
      : [{ left: 60, right: 16, top: 40, bottom: 60 }],
    xAxis: hasVol
      ? [
          { type: 'category', data: allDates, axisLabel: { show: false }, boundaryGap: false },
          { type: 'category', gridIndex: 1, data: allDates, boundaryGap: false, axisLabel: { ...AXIS_LABEL_STYLE, hideOverlap: true } },
        ]
      : [{ type: 'category', data: allDates, boundaryGap: false, axisLabel: { ...AXIS_LABEL_STYLE, hideOverlap: true } }],
    yAxis: hasVol
      ? [
          { scale: true, splitLine: SPLIT_LINE_STYLE, axisLabel: AXIS_LABEL_STYLE },
          { gridIndex: 1, splitNumber: 2, scale: true, axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9, formatter: VOL_LABEL_FMT } },
        ]
      : [{ scale: true, splitLine: SPLIT_LINE_STYLE, axisLabel: AXIS_LABEL_STYLE }],
    series,
  }
}

function gridRect(chart: ChartLike): GridRect | null {
  try {
    const grid = chart.getModel().getComponent('grid', 0)
    return grid.coordinateSystem.getRect()
  } catch { return null }
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

  const els: unknown[] = []

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
    els.push({ id: `${id}:vline`, type: 'line', silent: true, shape: { x1: p[0], y1: rect.y, x2: p[0], y2: rect.y + rect.height }, style: stl })
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
    } else if (a.type === 'vline') {
      const x = resolveXCoord(a.x, st.xScale)
      if (x != null) addVLine(x, stl, false, a.id)
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
        elements: [{
          id: '__ng_draw_layer__',
          type: 'group',
          x: 0, y: 0,
          silent: true,
          clipPath: { type: 'rect', shape: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } },
          children: els,
        }],
      },
    },
    { lazyUpdate: true, replaceMerge: ['graphic'] },
  )
}

function applyCrosshair(st: EngineState): void {
  if (st.crosshairOn) {
    if (st._origTooltip) st.chart.setOption({ tooltip: deepClone(st._origTooltip) }, { lazyUpdate: true })
    if (st._origAxisPointer) st.chart.setOption({ axisPointer: deepClone(st._origAxisPointer) }, { lazyUpdate: true })
  } else {
    st.chart.setOption({ tooltip: { show: false }, axisPointer: { link: [] } }, { lazyUpdate: true })
  }
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
      <button onClick={onRemove} className="text-white/30 hover:text-white transition-colors"><X className="w-3 h-3" /></button>
    </span>
  )
}

function InstrumentSearch({ instruments, selected, onAdd }: { instruments: Instrument[]; selected: string[]; onAdd: (sym: string) => void }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const lq = q.toLowerCase()
    return instruments
      .filter((i) => !selected.includes(i.symbol) && (i.symbol.toLowerCase().includes(lq) || (i.shortname ?? '').toLowerCase().includes(lq)))
  }, [instruments, selected, q])

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
                onAdd(i.symbol)
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
  { key: 'bb', label: 'Bollinger Bands (20)' },
]

function IndicatorDropdown({ indicators, onChange }: { indicators: Set<string>; onChange: (key: string) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const activeCount = INDICATOR_ITEMS.filter((i) => indicators.has(i.key)).length

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
  color: string
  candles?: CandleDay[]
  seriesMap?: Map<string, CandleDay[]>
}

function ChartPanel({ sym, name, chartType, showVolume, color, candles, seriesMap }: ChartPanelProps) {
  const [interval, setIntervalState] = useState<AggInterval>('D')
  const [indicators, setIndicators] = useState<Set<string>>(new Set())
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
      return buildCandlestickOption(sym, aggCandles, showVolume, indicators)
    }
    const sm = aggSeriesMap ?? (aggCandles ? new Map([[sym, aggCandles]]) : null)
    if (!sm) return null
    return buildLineOption(sm, showVolume, indicators)
  }, [aggCandles, aggSeriesMap, chartType, showVolume, indicators, sym])

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
    const eng = engineRef.current
    if (!eng) return
    eng.crosshairOn = !eng.crosshairOn
    setCrosshairOn(eng.crosshairOn)
    applyCrosshair(eng)
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
        <div className="flex items-center gap-2">
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
          <IndicatorDropdown indicators={indicators} onChange={toggleIndicator} />
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
    </div>
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

type Props = { mic: string; instruments: Instrument[]; preselectedSymbol: string | null }

export function ChartsPage({ mic, instruments, preselectedSymbol }: Props) {
  const router = useRouter()

  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(preselectedSymbol ? [preselectedSymbol] : [])
  const [chartType, setChartType]   = useState<ChartType>('candlestick')
  const [layout, setLayout]         = useState<Layout>('separate')
  const [showVolume, setShowVolume] = useState(true)
  const [dateRange, setDateRange]   = useState<DateRange>('ALL')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo]     = useState('')
  const [syncing, setSyncing]       = useState(false)
  const [seriesData, setSeriesData] = useState<Map<string, SeriesData>>(new Map())
  const [status, setStatus]         = useState<string | null>(null)
  const [showCsvModal, setShowCsvModal] = useState(false)

  const colorOf = useCallback((sym: string): string => {
    const idx = [...seriesData.keys()].indexOf(sym)
    const fallback = selectedSymbols.indexOf(sym)
    return CHART_COLORS[(idx >= 0 ? idx : fallback) % CHART_COLORS.length] ?? '#3b82f6'
  }, [seriesData, selectedSymbols])

  const addSymbol    = (sym: string) => { if (!selectedSymbols.includes(sym)) setSelectedSymbols((p) => [...p, sym]) }
  const removeSymbol = (sym: string) => {
    setSelectedSymbols((p) => p.filter((s) => s !== sym))
    setSeriesData((p) => { const m = new Map(p); m.delete(sym); return m })
  }

  const getRange = useCallback((): { from: string | null; to: string | null } => {
    if (dateRange === 'CUSTOM') return { from: customFrom ? customFrom.slice(0, 10) : null, to: customTo ? customTo.slice(0, 10) : null }
    return getDateRange(dateRange)
  }, [dateRange, customFrom, customTo])

  const openImportCsvModal = useCallback(() => {
    if (selectedSymbols.length !== 1) {
      toast.warning('Wybierz dokładnie jeden instrument przed importem CSV')
      return
    }

    setShowCsvModal(true)
  }, [selectedSymbols])

  const syncAndRender = useCallback(async () => {
    if (!selectedSymbols.length) { toast.warning('Wybierz przynajmniej jeden instrument'); return }
    setSyncing(true); setStatus('Synchronizacja danych…')
    const { from, to } = getRange()
    const newData = new Map<string, SeriesData>()

    for (const sym of selectedSymbols) {
      setStatus(`Pobieranie: ${sym}…`)
      try {
        const res = await fetch('/api/stock/candles/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol: sym, date_from: from, date_to: to, return_all: !from, overlap_days: 7 }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({})) as { error?: string }
          toast.error(`${sym}: ${err.error ?? 'Błąd sync'}`)
          continue
        }
        const result = await res.json() as SyncCandlesResult
        const candles = (result.items ?? []).sort((a, b) => a.date_quote.localeCompare(b.date_quote))
        newData.set(sym, { result, candles })
      } catch {
        toast.error(`${sym}: błąd połączenia`)
      }
    }

    setSeriesData(newData)
    setSyncing(false)
    setStatus(newData.size > 0 ? `Gotowe — ${[...newData.values()].reduce((a, d) => a + d.candles.length, 0)} punktów` : 'Brak danych')
  }, [selectedSymbols, getRange])

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
    const candles = (result.items ?? []).sort((a, b) => a.date_quote.localeCompare(b.date_quote))
    setSeriesData(new Map([[result.symbol, { result, candles }]]))
    setSelectedSymbols([result.symbol])
    setStatus(`Zaimportowano ${result.upserted_rows} wierszy dla ${result.symbol}`)
  }, [])

  const effectiveChartType: ChartType =
    chartType === 'candlestick' && layout === 'combined' && selectedSymbols.length > 1 ? 'line' : chartType

  const chartEntries = useMemo(() => {
    if (!seriesData.size) return null
    if (layout === 'combined') {
      const combinedMap = new Map([...seriesData.entries()].map(([sym, { candles }]) => [sym, candles]))
      return [{ key: 'combined', sym: 'combined', name: 'Porównanie', seriesMap: combinedMap, candles: undefined as CandleDay[] | undefined }]
    }
    return [...seriesData.entries()].map(([sym, { candles, result }]) => ({
      key: sym, sym, name: result.name ?? sym,
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
            <div className="flex rounded-lg overflow-hidden border border-white/10">
              {MICS.map((m) => (
                <button key={m} onClick={() => router.push(`/stock/charts/${m}`)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${mic === m ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'}`}>
                  {MIC_LABELS[m]}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {selectedSymbols.map((sym) => (
                <SymbolChip key={sym} symbol={sym} color={colorOf(sym)} onRemove={() => removeSymbol(sym)} />
              ))}
            </div>
            <InstrumentSearch instruments={instruments} selected={selectedSymbols} onAdd={addSymbol} />
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
              <button onClick={() => void syncAndRender()} disabled={syncing || !selectedSymbols.length}
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />Sync &amp; Render
              </button>
            </div>
          </div>

          {chartType === 'candlestick' && layout === 'combined' && selectedSymbols.length > 1 && (
            <p className="text-xs text-amber-400/70 bg-amber-500/5 border border-amber-500/10 rounded-lg px-3 py-1.5">
              Tryb nakładany ze świecami jest dostępny tylko dla jednego symbolu — przełączono na liniowy.
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
            showVolume={showVolume} color={colorOf(sym)} candles={candles} seriesMap={seriesMap}
          />
        ))}
      </div>

      {showCsvModal && selectedSymbols.length === 1 && (
        <ImportCsvModal
          symbol={selectedSymbols[0]!}
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
