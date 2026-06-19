import type {
  CandleDay,
  DirectionalPhase,
  VolumeProfileBin,
  VolumeZone,
  VolumeZonesResponse,
} from '@/lib/api/stock'

export const VOLUME_ZONE_EVIDENCE_LABELS: Record<string, string> = {
  HIGH_RELATIVE_VOLUME: 'Ponadprzeciętny wolumen',
  DECLINING_DOWNSIDE_EFFECTIVENESS: 'Spadki tracą skuteczność',
  DECLINING_UPSIDE_EFFECTIVENESS: 'Wzrosty tracą skuteczność',
  FAILED_BREAKDOWNS: 'Nieudane wybicia dołem',
  FAILED_BREAKOUTS: 'Nieudane wybicia górą',
  VOLATILITY_COMPRESSION: 'Kompresja zmienności',
}

export const VOLUME_ZONE_BEHAVIOR_LABELS: Record<string, string> = {
  DEMAND_ABSORPTION_PROXY: 'Absorpcja popytowa (proxy)',
  SUPPLY_ABSORPTION_PROXY: 'Absorpcja podażowa (proxy)',
  NEUTRAL_LIQUIDITY: 'Neutralna płynność',
  INSUFFICIENT_DIRECTIONAL_EVIDENCE: 'Niewystarczające dowody kierunku',
  BROAD_NEUTRAL_LIQUIDITY: 'Szeroka strefa płynności',
}

export const VOLUME_ZONE_LIFECYCLE_LABELS: Record<string, string> = {
  CANDIDATE: 'Kandydat',
  ACTIVE: 'Aktywna',
  CONFIRMED: 'Potwierdzona',
  INVALIDATED: 'Unieważniona',
  CLOSED: 'Zamknięta',
}

export const VOLUME_ZONE_MARKET_ROLE_LABELS: Record<string, string> = {
  ACTIVE_DEMAND: 'Aktywny popyt',
  ACTIVE_SUPPLY: 'Aktywna podaż',
  FORMER_DEMAND_NOW_SUPPLY: 'Dawny popyt, teraz podaż',
  FORMER_SUPPLY_NOW_DEMAND: 'Dawna podaż, teraz popyt',
  HISTORICAL_SUPPORT: 'Historyczne wsparcie',
  HISTORICAL_RESISTANCE: 'Historyczny opór',
  NEUTRAL_LIQUIDITY: 'Neutralna płynność',
}

export const VOLUME_ZONE_PRICE_RELATION_LABELS: Record<string, string> = {
  INSIDE_ZONE: 'Cena w strefie',
  ABOVE_ZONE: 'Cena powyżej',
  BELOW_ZONE: 'Cena poniżej',
  APPROACHING_FROM_ABOVE: 'Dochodzi z góry',
  APPROACHING_FROM_BELOW: 'Dochodzi z dołu',
  RETESTING_FROM_ABOVE: 'Retest z góry',
  RETESTING_FROM_BELOW: 'Retest z dołu',
  BROKEN_UP: 'Przełamana w górę',
  BROKEN_DOWN: 'Przełamana w dół',
}

export const VOLUME_ZONE_QUALITY_FAIL_LABELS: Record<string, string> = {
  MINIMUM_EFFECTIVE_SESSIONS_NOT_MET: 'Za mało efektywnych sesji',
  MINIMUM_ACTIVE_WEEKS_NOT_MET: 'Za mało aktywnych tygodni',
  MINIMUM_ACTIVITY_EQUIVALENT_SESSIONS_NOT_MET: 'Za niska równoważna aktywność',
  DOMINANT_SESSION_SHARE_EXCEEDED: 'Aktywność skupiona w jednej sesji',
  MINIMUM_CONSISTENCY_NOT_MET: 'Za niska spójność',
}

export const VOLUME_ZONE_STATE_LABELS: Record<string, string> = {
  NEUTRAL: 'Neutralny',
  ACCUMULATION_CANDIDATE: 'Kandydat akumulacji',
  ACCUMULATION_ACTIVE: 'Akumulacja aktywna',
  MARKUP: 'Wzrost (markup)',
  FAILED_ACCUMULATION: 'Nieudana akumulacja',
  REACCUMULATION_CANDIDATE: 'Kandydat reakumulacji',
  REACCUMULATION_ACTIVE: 'Reakumulacja aktywna',
  DISTRIBUTION_CANDIDATE: 'Kandydat dystrybucji',
  DISTRIBUTION_ACTIVE: 'Dystrybucja aktywna',
  MARKDOWN: 'Spadek (markdown)',
  FAILED_DISTRIBUTION: 'Nieudana dystrybucja',
  REDISTRIBUTION_CANDIDATE: 'Kandydat redystrybucji',
  REDISTRIBUTION_ACTIVE: 'Redystrybucja aktywna',
}

const SLATE: [number, number, number] = [148, 163, 184]
const BEHAVIOR_COLORS: Record<string, [number, number, number]> = {
  DEMAND_ABSORPTION_PROXY: [34, 197, 94],
  SUPPLY_ABSORPTION_PROXY: [239, 68, 68],
  NEUTRAL_LIQUIDITY: SLATE,
  INSUFFICIENT_DIRECTIONAL_EVIDENCE: SLATE,
  BROAD_NEUTRAL_LIQUIDITY: SLATE,
}

export type VolumeProfileToggle = 'raw' | 'active' | 'structural'
export type ZoneVisibility = 'all' | 'significant' | 'active'
export type PhaseVisibility = 'off' | 'significant' | 'current' | 'debug'

export const VOLUME_PROFILE_MODE_LABELS: Record<VolumeProfileToggle, string> = {
  raw: 'Estymowany wolumen',
  active: 'Aktywność bieżąca',
  structural: 'Akceptacja strukturalna',
}

const SIGNIFICANT_PHASE_LIMIT = 6
const OUTCOME_LABEL_LIMIT = 6

export type VolumeZoneChartOptions = {
  showZones: boolean
  showProfile: boolean
  profileOpacity: number
  profileMode?: VolumeProfileToggle
  zoneVisibility?: ZoneVisibility
  phaseVisibility?: PhaseVisibility
  showPhases?: boolean
}

export const DIRECTIONAL_PHASE_LABELS: Record<string, string> = {
  ACCUMULATION: 'Akumulacja',
  DISTRIBUTION: 'Dystrybucja',
}

export function phaseShortLabel(phase: Pick<DirectionalPhase, 'phase' | 'status'>): string {
  return phase.phase === 'ACCUMULATION' ? 'A' : 'D'
}

export function phaseOutcomeLabel(phase: Pick<DirectionalPhase, 'phase' | 'status'>): string | null {
  const base = phaseShortLabel(phase)
  if (phase.status === 'CONFIRMED') return `${base}✓`
  if (phase.status === 'INVALIDATED') return `${base}×`
  return null
}

function phaseStyle(
  phase: Pick<DirectionalPhase, 'phase' | 'status'>,
): { fill: string; border: string; type: 'solid' | 'dashed' } {
  const rgb = phase.phase === 'ACCUMULATION' ? '34,197,94' : '239,68,68'
  const fillOpacity = phase.status === 'CONFIRMED' ? 0.12
    : phase.status === 'ACTIVE' ? 0.10
    : 0.07
  return {
    fill: `rgba(${rgb},${fillOpacity})`,
    border: `rgba(${rgb},0.8)`,
    type: 'solid',
  }
}

const ACTIVE_LIFECYCLES = new Set(['CANDIDATE', 'ACTIVE', 'CONFIRMED'])

type CandlePeriod = { period_start?: string; period_end?: string; date_quote: string }

// Maps a raw daily date to the index of the (possibly aggregated) category that
// contains it. Uses each category's period bounds rather than lexicographic
// string matching, so weekly/monthly buckets resolve correctly (correction 13).
export function buildDateIndexResolver(
  categories: CandlePeriod[],
): (date: string | null | undefined) => number | null {
  if (!categories.length) return () => null
  return (date) => {
    if (!date) return null
    let fallback: number | null = null
    for (let i = 0; i < categories.length; i++) {
      const c = categories[i]!
      const start = c.period_start ?? c.date_quote
      const end = c.period_end ?? c.date_quote
      if (date >= start && date <= end) return i
      if (date >= start) fallback = i
    }
    return fallback ?? (date < (categories[0]!.period_start ?? categories[0]!.date_quote) ? 0 : categories.length - 1)
  }
}

type CustomRenderParams = {
  coordSys: {
    x: number
    y: number
    width: number
    height: number
  }
}

type CustomRenderApi = {
  value: (index: number) => string | number
  coord: (value: [string | number, string | number]) => [number, number]
}

type ColorCallbackParams = {
  value: number | null
}

export function evidenceLabel(code: string): string {
  return VOLUME_ZONE_EVIDENCE_LABELS[code] ?? code
}

export function behaviorLabel(code: string | null | undefined): string {
  return code ? (VOLUME_ZONE_BEHAVIOR_LABELS[code] ?? code) : '—'
}

export function lifecycleLabel(code: string | null | undefined): string {
  return code ? (VOLUME_ZONE_LIFECYCLE_LABELS[code] ?? code) : '—'
}

export function marketRoleLabel(code: string | null | undefined): string {
  return code ? (VOLUME_ZONE_MARKET_ROLE_LABELS[code] ?? code) : '—'
}

export function priceRelationLabel(code: string | null | undefined): string {
  return code ? (VOLUME_ZONE_PRICE_RELATION_LABELS[code] ?? code) : '—'
}

export function qualityFailLabel(code: string): string {
  return VOLUME_ZONE_QUALITY_FAIL_LABELS[code] ?? code
}

export function stateLabel(code: string | null | undefined): string {
  return code ? (VOLUME_ZONE_STATE_LABELS[code] ?? code) : '—'
}

const NEUTRAL_BEHAVIORS = new Set<string>([
  'NEUTRAL_LIQUIDITY',
  'INSUFFICIENT_DIRECTIONAL_EVIDENCE',
  'BROAD_NEUTRAL_LIQUIDITY',
])

// Single source of truth: a zone reads as invalidated from lifecycle_status, or
// (when that field is absent on older payloads) from the legacy status.
export function isZoneInvalidated(
  zone: Pick<VolumeZone, 'lifecycle_status' | 'status'>,
): boolean {
  if (zone.lifecycle_status) {
    return zone.lifecycle_status === 'INVALIDATED' || zone.lifecycle_status === 'CLOSED'
  }
  return zone.status === 'INVALIDATED'
}

type ZoneColorInput = Pick<
  VolumeZone,
  'behavior' | 'evidence_balance' | 'evidence_score' | 'lifecycle_status' | 'status'
>

export function zoneColor(zone: ZoneColorInput, opacity = 0.22): string {
  // Invalidated / broken or purely liquidity zones read gray, never live green
  // accumulation - the live state must not contradict the lifecycle.
  if (isZoneInvalidated(zone) || NEUTRAL_BEHAVIORS.has(zone.behavior)) {
    const [r, g, b] = SLATE
    const strength = Math.max(0.08, Math.min(0.2, opacity * 0.65))
    return `rgba(${r},${g},${b},${strength.toFixed(3)})`
  }
  const [r, g, b] = BEHAVIOR_COLORS[zone.behavior] ?? SLATE
  const strength = Math.max(0.12, Math.min(0.42, opacity + Math.abs(zone.evidence_balance) * (zone.evidence_score / 100) * 0.25))
  return `rgba(${r},${g},${b},${strength.toFixed(3)})`
}

type ZoneBorderInput = Pick<
  VolumeZone,
  'behavior' | 'episode_signature' | 'lifecycle_status' | 'status'
>

// The border carries the historical signature (so a broken accumulation zone
// still shows its green origin); the fill carries the current (gray) state.
export function zoneBorderStyle(
  zone: ZoneBorderInput,
): { color: string; type: 'solid' | 'dashed'; width: number } {
  const signature = zone.episode_signature ?? zone.behavior
  const [r, g, b] = BEHAVIOR_COLORS[signature] ?? SLATE
  const invalid = isZoneInvalidated(zone)
  return {
    color: `rgba(${r},${g},${b},${invalid ? '0.85' : '0.72'})`,
    type: invalid ? 'dashed' : 'solid',
    width: 1,
  }
}

export function zoneBorderColor(zone: ZoneBorderInput): string {
  return zoneBorderStyle(zone).color
}

function zonesForVisibility(
  analysis: VolumeZonesResponse,
  visibility: ZoneVisibility,
): VolumeZone[] {
  const sorted = [...analysis.zones].sort(
    (a, b) => (a.display_priority ?? 99) - (b.display_priority ?? 99),
  )
  if (visibility === 'significant') {
    const ids = new Set(analysis.highlighted_zone_ids ?? [])
    const sig = sorted.filter((z) => ids.has(z.zone_id))
    return sig.length ? sig : sorted.slice(0, 3)
  }
  if (visibility === 'active') {
    const activeId = analysis.active_zone?.zone_id
    return sorted.filter(
      (z) => z.zone_id === activeId
        || (z.lifecycle_status != null && ACTIVE_LIFECYCLES.has(z.lifecycle_status)),
    )
  }
  return sorted // 'all' — every detected historical zone
}

function phaseSortDate(phase: DirectionalPhase): string {
  return phase.confirmed_at
    ?? phase.invalidated_at
    ?? phase.ended_at
    ?? phase.active_at
    ?? phase.candidate_at
}

function phasePriority(phase: DirectionalPhase): number {
  const isCurrent = phase.status === 'ACTIVE' || phase.status === 'CANDIDATE'
  return (isCurrent ? 400 : 0)
    + (phase.historical_outcome_score ?? phase.setup_score ?? phase.significance_score ?? phase.evidence_score)
    + Math.min(60, Math.max(0, phase.session_count))
}

function newestPhases(phases: DirectionalPhase[], limit: number): DirectionalPhase[] {
  return [...phases]
    .sort((a, b) => phaseSortDate(b).localeCompare(phaseSortDate(a)))
    .slice(0, limit)
    .sort((a, b) => phaseSortDate(a).localeCompare(phaseSortDate(b)))
}

function latestDate(...dates: Array<string | null | undefined>): string | null {
  const valid = dates.filter((date): date is string => Boolean(date))
  return valid.length ? valid.sort((a, b) => a.localeCompare(b))[valid.length - 1]! : null
}

function zoneBoxDates(zone: VolumeZone): { start: string; end: string } {
  const episode = zone.episodes[zone.episodes.length - 1]
  const start = episode?.estimated_start_date ?? zone.estimated_start_date
  const end = latestDate(
    episode?.last_active_at,
    episode?.confirmed_at,
    episode?.invalidated_at,
    zone.last_active_at,
  ) ?? zone.last_active_at
  return { start, end }
}

function phaseBoxDates(phase: DirectionalPhase): { start: string; end: string } {
  return {
    start: phase.estimated_start_at ?? phase.candidate_at,
    end: phase.ended_at,
  }
}

function candleOverlapsDateRange(candle: CandleDay, startDate: string, endDate: string): boolean {
  const start = candle.period_start ?? candle.date_quote
  const end = candle.period_end ?? candle.date_quote
  return end >= startDate && start <= endDate
}

function candlePriceExtent(
  candles: CandleDay[] | undefined,
  startDate: string,
  endDate: string,
): { low: number; high: number } | null {
  if (!candles?.length) return null
  let low = Number.POSITIVE_INFINITY
  let high = Number.NEGATIVE_INFINITY
  for (const candle of candles) {
    if (!candleOverlapsDateRange(candle, startDate, endDate)) continue
    low = Math.min(low, candle.low)
    high = Math.max(high, candle.high)
  }
  return Number.isFinite(low) && Number.isFinite(high) ? { low, high } : null
}

function candleCloseAtDate(candles: CandleDay[] | undefined, date: string): number | null {
  const candle = candles?.find((item) => candleOverlapsDateRange(item, date, date))
  return candle?.close ?? null
}

function resolveVisibleBoxIndexes(
  startDate: string,
  endDate: string,
  resolver: (date: string | null | undefined) => number | null,
  lastIndex = 0,
): [number, number] {
  let start = resolver(startDate) ?? 0
  let end = resolver(endDate) ?? lastIndex
  if (end < start) end = start

  // A one-session episode must still be a hoverable box on a category axis,
  // not a hairline. Prefer extending right; at the right edge extend left.
  if (end <= start) {
    if (start < lastIndex) {
      end = start + 1
    } else {
      start = Math.max(0, start - 1)
    }
  }
  return [start, end]
}

function phasesForVisibility(
  analysis: VolumeZonesResponse,
  visibility: PhaseVisibility,
): DirectionalPhase[] {
  if (visibility === 'off') return []

  const resolved = analysis.resolved_directional_episodes
  const major = analysis.major_directional_phases
  const raw = analysis.directional_episodes ?? []
  const hasMajorLayer = Array.isArray(major)
  const phases = visibility === 'debug'
    ? raw
    : visibility === 'current'
      ? (resolved ?? raw)
      : (hasMajorLayer ? major : (resolved ?? raw))
  if (!phases.length) return []

  if (visibility === 'debug') return phases

  if (visibility === 'current') {
    return newestPhases(
      phases.filter((phase) => phase.status === 'ACTIVE' || phase.status === 'CANDIDATE'),
      1,
    )
      .concat(
        phases.some((phase) => phase.status === 'ACTIVE' || phase.status === 'CANDIDATE')
          ? []
          : newestPhases(phases, 1),
      )
  }

  if (hasMajorLayer) {
    return phases
      .filter((phase) => phase.status === 'CONFIRMED' || phase.historical_outcome_score != null)
      .sort((a, b) => phaseSortDate(a).localeCompare(phaseSortDate(b)))
  }

  const significant = phases
    .filter((phase) => phase.status === 'CONFIRMED' || phase.historical_outcome_score != null)
    .sort((a, b) =>
      (b.historical_outcome_score ?? phasePriority(b))
      - (a.historical_outcome_score ?? phasePriority(a)),
    )
    .slice(0, SIGNIFICANT_PHASE_LIMIT)

  return (significant.length ? significant : newestPhases(phases, Math.min(3, SIGNIFICANT_PHASE_LIMIT)))
    .sort((a, b) => phaseSortDate(a).localeCompare(phaseSortDate(b)))
}

// Short on-chart code for a volume zone (full description lives in the tooltip):
// "S" = strefa wolumenowa, "S×" = przełamana.
function zoneShortLabel(zone: Pick<VolumeZone, 'lifecycle_status' | 'status'>): string {
  return isZoneInvalidated(zone) ? 'S×' : 'S'
}

export function buildVolumeZoneMarkArea(
  analysis: VolumeZonesResponse | null,
  options: VolumeZoneChartOptions,
  resolver?: (date: string | null | undefined) => number | null,
  lastIndex?: number,
): object | undefined {
  if (!analysis || !options.showZones || !analysis.zones.length) return undefined
  const zones = zonesForVisibility(analysis, options.zoneVisibility ?? 'all')
  const data: object[][] = []
  for (const zone of zones) {
    const border = zoneBorderStyle(zone)
    const isActive = zone.zone_id === analysis.active_zone?.zone_id
    // Without a resolver fall back to a full-width band (back-compat path).
    if (!resolver) {
      data.push([
        {
          name: zone.zone_id,
          yAxis: zone.price_low,
          itemStyle: {
            color: zoneColor(zone),
            borderColor: border.color,
            borderType: border.type,
            borderWidth: isActive ? border.width + 0.5 : border.width,
          },
          label: { show: true, position: 'insideTopLeft', fontSize: 10, color: 'rgba(226,232,240,0.85)', formatter: zoneShortLabel(zone) },
        },
        { yAxis: zone.price_high },
      ])
      continue
    }
    const box = zoneBoxDates(zone)
    const [startIdx, endIdx] = resolveVisibleBoxIndexes(
      box.start, box.end, resolver, lastIndex ?? 0,
    )
    // Formation / decision box: the candles that actually built or resolved
    // the zone, so the breakout/rejection level is visible as a rectangle.
    data.push([
      {
        name: zone.zone_id,
        xAxis: startIdx,
        yAxis: zone.price_low,
        itemStyle: {
          color: zoneColor(zone),
          borderColor: border.color,
          borderType: border.type,
          borderWidth: isActive ? border.width + 0.5 : border.width,
        },
        label: { show: true, position: 'insideTopLeft', fontSize: 10, color: 'rgba(226,232,240,0.85)', formatter: zoneShortLabel(zone) },
      },
      { xAxis: endIdx, yAxis: zone.price_high },
    ])
  }
  return { silent: false, label: { show: false }, itemStyle: { borderWidth: 1 }, data }
}

// The level a zone leaves behind after its formation box: dashed horizontal
// lines at the zone's low and high, from formation end until the zone is
// invalidated (or the latest candle if still valid). Drawn on a dedicated
// overlay series (the candlestick series already owns the confirm/invalid line).
export function buildZoneLevelMarkLine(
  analysis: VolumeZonesResponse | null,
  options: VolumeZoneChartOptions,
  resolver?: (date: string | null | undefined) => number | null,
  lastIndex?: number,
): object | undefined {
  if (!analysis || !options.showZones || !resolver || !analysis.zones.length) {
    return undefined
  }
  const zones = zonesForVisibility(analysis, options.zoneVisibility ?? 'all')
  const data: object[][] = []
  for (const zone of zones) {
    const border = zoneBorderStyle(zone)
    const box = zoneBoxDates(zone)
    const [, endIdx] = resolveVisibleBoxIndexes(box.start, box.end, resolver, lastIndex ?? 0)
    const episode = zone.episodes[zone.episodes.length - 1]
    const stopIdx = episode?.invalidated_at != null
      ? (resolver(episode.invalidated_at) ?? (lastIndex ?? endIdx))
      : (lastIndex ?? endIdx)
    if (stopIdx <= endIdx) continue
    // The projected level is always dashed (it is a remembered level, not the
    // filled formation box).
    const lineStyle = { type: 'dashed' as const, color: border.color, width: 1, opacity: 0.7 }
    for (const price of [zone.price_low, zone.price_high]) {
      data.push([
        { coord: [endIdx, price], lineStyle },
        { coord: [stopIdx, price] },
      ])
    }
  }
  if (!data.length) return undefined
  return { silent: true, symbol: 'none', data }
}

// Directional accumulation/distribution phases as their own time+price boxes,
// independent of liquidity zones. Attached to a dedicated overlay series.
export function buildDirectionalEpisodeMarkArea(
  analysis: VolumeZonesResponse | null,
  options: VolumeZoneChartOptions,
  resolver?: (date: string | null | undefined) => number | null,
  lastIndex?: number,
  candles?: CandleDay[],
): object | undefined {
  if (!analysis || !options.showPhases) return undefined
  const episodes = phasesForVisibility(
    analysis,
    options.phaseVisibility ?? (options.showPhases ? 'significant' : 'off'),
  )
  if (!episodes.length) return undefined
  const data = episodes.map((phase) => {
    const style = phaseStyle(phase)
    const dates = phaseBoxDates(phase)
    const extent = candlePriceExtent(candles, dates.start, dates.end)
    const corner: Record<string, unknown> = {
      name: phase.phase_id,
      yAxis: extent?.low ?? phase.price_low,
      itemStyle: { color: style.fill, borderColor: style.border, borderType: style.type, borderWidth: 1 },
      label: { show: false, position: 'insideTop', fontSize: 10, color: style.border, formatter: phaseShortLabel(phase) },
    }
    const end: Record<string, unknown> = { yAxis: extent?.high ?? phase.price_high }
    if (resolver) {
      const [startIdx, endIdx] = resolveVisibleBoxIndexes(
        dates.start,
        dates.end,
        resolver,
        lastIndex ?? 0,
      )
      corner.xAxis = startIdx
      end.xAxis = endIdx
    }
    return [corner, end]
  })
  return { silent: true, label: { show: false }, itemStyle: { borderWidth: 1 }, data }
}

export function buildDirectionalEpisodeBoxSeries(
  analysis: VolumeZonesResponse | null,
  options: VolumeZoneChartOptions,
  resolver?: (date: string | null | undefined) => number | null,
  lastIndex?: number,
  candles?: CandleDay[],
  interactive = true,
): object | null {
  if (!analysis || !options.showPhases || !resolver) return null
  const boxes = phasesForVisibility(
    analysis,
    options.phaseVisibility ?? (options.showPhases ? 'significant' : 'off'),
  ).map(
    (phase): [number, number, number, number, string, string, string] => {
      const dates = phaseBoxDates(phase)
      const [startIdx, endIdx] = resolveVisibleBoxIndexes(
        dates.start,
        dates.end,
        resolver,
        lastIndex ?? 0,
      )
      const extent = candlePriceExtent(candles, dates.start, dates.end)
      const style = phaseStyle(phase)
      return [
        startIdx,
        endIdx,
        extent?.low ?? phase.price_low,
        extent?.high ?? phase.price_high,
        phaseTooltipHtml(phase),
        style.fill,
        style.border,
      ]
    },
  )
  if (!boxes.length) return null
  return {
    name: 'Fazy A/D',
    type: 'custom',
    coordinateSystem: 'cartesian2d',
    xAxisIndex: 0,
    yAxisIndex: 0,
    silent: !interactive,
    z: 2,
    encode: { x: [0, 1], y: [2, 3] },
    tooltip: { trigger: 'item', formatter: (p: { data: Array<number | string> }) => String(p.data[4]) },
    data: boxes,
    renderItem: (_params: CustomRenderParams, api: CustomRenderApi) => {
      const p0 = api.coord([api.value(0), api.value(2)])
      const p1 = api.coord([api.value(1), api.value(3)])
      const x = Math.min(p0[0], p1[0])
      const y = Math.min(p0[1], p1[1])
      const width = Math.max(4, Math.abs(p1[0] - p0[0]))
      const height = Math.max(4, Math.abs(p1[1] - p0[1]))
      return {
        type: 'rect',
        shape: { x, y, width, height },
        style: {
          fill: String(api.value(5)),
          stroke: String(api.value(6)),
          lineWidth: 1,
        },
      }
    },
  }
}

const DIRECTIONAL_PHASE_STATUS_LABELS: Record<string, string> = {
  CANDIDATE: 'Kandydat', ACTIVE: 'Aktywna', CONFIRMED: 'Potwierdzona',
  INVALIDATED: 'Unieważniona', CLOSED: 'Zamknięta',
}

function formatVolume(v: number): string {
  return v >= 1_000_000 ? `${(v / 1_000_000).toFixed(2)} mln` : `${Math.round(v).toLocaleString('pl-PL')} szt.`
}

function formatPercent(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

function sourceProfileLabel(s: string | null | undefined): string {
  return s === 'BOTH' ? 'Strukturalny + aktywny'
    : s === 'STRUCTURAL' ? 'Strukturalny'
    : s === 'ACTIVE' ? 'Aktywny' : '—'
}

function zoneTooltipHtml(zone: VolumeZone): string {
  const share = Math.max(zone.structural_strength ?? 0, zone.active_strength ?? 0)
  const dates = zone.top_session_dates ?? []
  const box = zoneBoxDates(zone)
  const lines = [
    `<b>Strefa wolumenowa · ${behaviorLabel(zone.episode_signature ?? zone.behavior)}</b>`,
    `Zakres ceny: ${zone.price_low.toFixed(2)}–${zone.price_high.toFixed(2)}`,
    `Świece strefy: ${box.start}–${box.end}`,
    `Raw volume: ${formatVolume(zone.raw_volume)}`,
    `Udział w profilu: ${share.toFixed(1)}%`,
    `Activity score: ${zone.activity_score.toFixed(0)}`,
    `Liczba sesji: ${Math.round(zone.effective_sessions)}`,
    dates.length ? `Top dni: ${dates.join(', ')}` : '',
    `Źródło: ${sourceProfileLabel(zone.source_profile)}`,
  ]
  return lines.filter(Boolean).join('<br/>')
}

function phaseTooltipHtml(phase: DirectionalPhase): string {
  const lines = [
    `<b>${DIRECTIONAL_PHASE_LABELS[phase.phase] ?? phase.phase} (${phaseShortLabel(phase)})</b>`,
    `Zakres ceny: ${phase.price_low.toFixed(2)}–${phase.price_high.toFixed(2)}`,
    `Szacowany początek: ${phase.estimated_start_at ?? phase.candidate_at}`,
    `Wykryto: ${phase.candidate_at}`,
    `Koniec prostokąta: ${phase.ended_at}`,
    phase.confirmed_at ? `Potwierdzono: ${phase.confirmed_at}` : '',
    phase.invalidated_at ? `Unieważniono: ${phase.invalidated_at}` : '',
    `Status: ${DIRECTIONAL_PHASE_STATUS_LABELS[phase.status] ?? phase.status}`,
    `Średni bilans: ${phase.average_balance.toFixed(2)}`,
    `Sesje: ${phase.session_count}`,
    `Siła setupu: ${(phase.setup_score ?? phase.significance_score ?? phase.evidence_score).toFixed(0)}/100`,
    phase.historical_outcome_score != null
      ? `Wynik historyczny: ${phase.historical_outcome_score.toFixed(0)}/100`
      : '',
    phase.subsequent_return_20 != null ? `Zwrot 20 sesji: ${formatPercent(phase.subsequent_return_20)}` : '',
    phase.subsequent_return_60 != null ? `Zwrot 60 sesji: ${formatPercent(phase.subsequent_return_60)}` : '',
    phase.maximum_favorable_excursion != null ? `MFE: ${formatPercent(phase.maximum_favorable_excursion)}` : '',
    phase.maximum_adverse_excursion != null ? `MAE: ${formatPercent(phase.maximum_adverse_excursion)}` : '',
    phase.expected_direction_return != null ? `Zwrot w kierunku fazy: ${formatPercent(phase.expected_direction_return)}` : '',
    phase.opposite_move_penalty != null ? `Ruch przeciwny: ${phase.opposite_move_penalty.toFixed(1)}%` : '',
    phase.linked_zone_ids.length ? `Powiązane strefy: ${phase.linked_zone_ids.join(', ')}` : '',
  ]
  return lines.filter(Boolean).join('<br/>')
}

// Transparent, hoverable rectangles laid over the zone / phase boxes so each
// gets its own item tooltip (ECharts markArea has no per-item tooltip).
function buildBoxHoverSeries(
  name: string,
  boxes: Array<[number, number, number, number, string]>,
  interactive: boolean,
): object | null {
  if (!boxes.length) return null
  return {
    name,
    type: 'custom',
    coordinateSystem: 'cartesian2d',
    xAxisIndex: 0,
    yAxisIndex: 0,
    silent: !interactive,
    // Map the y-axis extent to the PRICE dims (2,3); the index dims (0,1) are x.
    // Without this ECharts treats dim 1 (endIdx ~ candle count) as a y value and
    // blows up the price axis to thousands.
    encode: { x: [0, 1], y: [2, 3] },
    tooltip: { trigger: 'item', formatter: (p: { data: Array<number | string> }) => String(p.data[4]) },
    data: boxes,
    renderItem: (_params: CustomRenderParams, api: CustomRenderApi) => {
      const p0 = api.coord([api.value(0), api.value(2)])
      const p1 = api.coord([api.value(1), api.value(3)])
      const x = Math.min(p0[0], p1[0])
      const y = Math.min(p0[1], p1[1])
      const width = Math.max(3, Math.abs(p1[0] - p0[0]))
      const height = Math.max(3, Math.abs(p1[1] - p0[1]))
      return {
        type: 'rect',
        shape: { x, y, width, height },
        // Near-transparent fill keeps the markArea visuals but stays hoverable.
        style: { fill: 'rgba(255,255,255,0.004)' },
      }
    },
  }
}

export function buildZoneHoverSeries(
  analysis: VolumeZonesResponse | null,
  options: VolumeZoneChartOptions,
  resolver?: (date: string | null | undefined) => number | null,
  lastIndex?: number,
  interactive = true,
): object | null {
  if (!analysis || !options.showZones || !resolver || !analysis.zones.length) return null
  const boxes = zonesForVisibility(analysis, options.zoneVisibility ?? 'all').map(
    (zone): [number, number, number, number, string] => {
      const box = zoneBoxDates(zone)
      const [startIdx, endIdx] = resolveVisibleBoxIndexes(
        box.start, box.end, resolver, lastIndex ?? 0,
      )
      return [startIdx, endIdx, zone.price_low, zone.price_high, zoneTooltipHtml(zone)]
    },
  )
  return buildBoxHoverSeries('Strefy (info)', boxes, interactive)
}

export function buildPhaseHoverSeries(
  analysis: VolumeZonesResponse | null,
  options: VolumeZoneChartOptions,
  resolver?: (date: string | null | undefined) => number | null,
  lastIndex?: number,
  interactive = true,
  candles?: CandleDay[],
): object | null {
  if (!analysis || !options.showPhases || !resolver) return null
  const boxes = phasesForVisibility(
    analysis,
    options.phaseVisibility ?? (options.showPhases ? 'significant' : 'off'),
  ).map(
    (phase): [number, number, number, number, string] => {
      const dates = phaseBoxDates(phase)
      const [startIdx, endIdx] = resolveVisibleBoxIndexes(
        dates.start,
        dates.end,
        resolver,
        lastIndex ?? 0,
      )
      const extent = candlePriceExtent(candles, dates.start, dates.end)
      return [
        startIdx,
        endIdx,
        extent?.low ?? phase.price_low,
        extent?.high ?? phase.price_high,
        phaseTooltipHtml(phase),
      ]
    },
  )
  return buildBoxHoverSeries('Fazy (info)', boxes, interactive)
}

export function buildDirectionalEpisodeOutcomeSeries(
  analysis: VolumeZonesResponse | null,
  options: VolumeZoneChartOptions,
  resolver?: (date: string | null | undefined) => number | null,
  candles?: CandleDay[],
): object | null {
  if (!analysis || !options.showPhases || !resolver) return null
  const phases = phasesForVisibility(
    analysis,
    options.phaseVisibility ?? (options.showPhases ? 'significant' : 'off'),
  )
  const showLabels = phases.length <= OUTCOME_LABEL_LIMIT
  const data = phases
    .map((phase) => {
      const label = phaseOutcomeLabel(phase)
      const outcomeDate = phase.confirmed_at ?? phase.invalidated_at ?? null
      if (!label || !outcomeDate) return null
      const x = resolver(outcomeDate)
      if (x == null) return null
      const rgb = phase.phase === 'ACCUMULATION' ? '34,197,94' : '239,68,68'
      const y = candleCloseAtDate(candles, outcomeDate) ?? phase.center_price
      return {
        value: [x, y],
        label: {
          show: showLabels,
          formatter: label,
          color: `rgba(${rgb},0.95)`,
          fontSize: 11,
          fontWeight: 700,
          position: phase.phase === 'ACCUMULATION' ? 'top' : 'bottom',
        },
        itemStyle: { color: `rgba(${rgb},0.95)` },
        tooltip: { formatter: phaseTooltipHtml(phase) },
      }
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
  if (!data.length) return null
  return {
    name: 'Wyniki faz A/D',
    type: 'scatter',
    coordinateSystem: 'cartesian2d',
    xAxisIndex: 0,
    yAxisIndex: 0,
    symbolSize: showLabels ? 5 : 3,
    z: 7,
    silent: false,
    tooltip: { trigger: 'item' },
    data,
  }
}

function zoneForProfileBin(bin: VolumeProfileBin, zones: VolumeZone[]): VolumeZone | null {
  const binCenter = bin.center_price
  return zones.find((zone) => binCenter >= zone.price_low && binCenter <= zone.price_high) ?? null
}

export function buildVolumeZoneMarkLine(analysis: VolumeZonesResponse | null): object | undefined {
  const zone = analysis?.active_zone
  if (!zone) return undefined
  const confirmHold = analysis?.current_state?.confirmation_hold_sessions ?? null
  const invalidHold = analysis?.current_state?.invalidation_hold_sessions ?? null
  const supply = (zone.episode_signature ?? zone.behavior) === 'SUPPLY_ABSORPTION_PROXY'
    || zone.direction_label.includes('DISTRIBUTION')
    || zone.direction_label.includes('SUPPLY')
  const data: object[] = []
  if (zone.confirmation_price != null) {
    const price = zone.confirmation_price.toFixed(2)
    const side = supply ? 'poniżej' : 'powyżej'
    const cond = confirmHold != null
      ? `Potwierdzenie: zamknięcia ${side} ${price} przez ${confirmHold} sesji`
      : `Potwierdzenie: zamknięcia ${side} ${price}`
    data.push({
      name: 'Potwierdzenie',
      yAxis: zone.confirmation_price,
      lineStyle: { type: 'solid', color: 'rgba(56,189,248,0.9)', width: 1.4 },
      label: { formatter: cond, color: 'rgba(186,230,253,0.9)', fontSize: 10 },
    })
  }
  if (zone.invalidation_price != null) {
    const price = zone.invalidation_price.toFixed(2)
    const side = supply ? 'powyżej' : 'poniżej'
    const cond = invalidHold != null
      ? `Unieważnienie: zamknięcia ${side} ${price} przez ${invalidHold} sesji`
      : `Unieważnienie: zamknięcia ${side} ${price}`
    data.push({
      name: 'Unieważnienie',
      yAxis: zone.invalidation_price,
      lineStyle: { type: 'dashed', color: 'rgba(251,113,133,0.95)', width: 1.2 },
      label: { formatter: cond, color: 'rgba(254,205,211,0.9)', fontSize: 10 },
    })
  }
  if (!data.length) return undefined
  return {
    silent: false,
    symbol: 'none',
    data,
  }
}

export function buildVolumeZoneProfileSeries(
  analysis: VolumeZonesResponse | null,
  options: VolumeZoneChartOptions,
  lastIndex = 0,
  xAxisIndex = 0,
  interactive = true,
): object | null {
  if (!analysis || !options.showProfile) return null
  const mode = options.profileMode ?? 'raw'
  // 'active' draws the decayed recent-window profile; 'raw' and 'structural'
  // both draw the full-history structural bins (which carry conserved
  // raw_volume) and differ only in which field sets the bar length.
  const bins = mode === 'active'
    ? (analysis.profile.length ? analysis.profile : (analysis.structural_profile ?? []))
    : (analysis.structural_profile?.length ? analysis.structural_profile : analysis.profile)
  if (!bins.length) return null
  const meta = mode === 'active' ? analysis.active_profile_metadata : analysis.structural_profile_metadata
  const maxRaw = bins.reduce((m, b) => Math.max(m, b.raw_volume), 0) || 1
  // The profile rides on its own x-axis (xAxisIndex) that is NOT controlled by
  // dataZoom, so it stays pinned to the grid's right edge regardless of the
  // visible window (it no longer vanishes when the range excludes the latest
  // candle). The anchor index only feeds the y-coord lookup / hit testing.
  const anchor = Math.max(0, lastIndex)
  const fmtVol = (v: number): string =>
    v >= 1_000_000 ? `${(v / 1_000_000).toFixed(2)} mln` : `${Math.round(v).toLocaleString('pl-PL')} szt.`
  return {
    name: 'Profil ceny i wolumenu',
    type: 'custom',
    coordinateSystem: 'cartesian2d',
    xAxisIndex,
    yAxisIndex: 0,
    z: 1,
    silent: !interactive,
    encode: { x: 0 },
    tooltip: {
      trigger: 'item',
      formatter: (p: { data: Array<number | string> }) => {
        const d = p.data
        const low = Number(d[3]).toFixed(2)
        const high = Number(d[4]).toFixed(2)
        const raw = Number(d[6])
        const activity = Number(d[8])
        const sessions = Number(d[9])
        const lines = [
          `Cena: ${low}–${high}`,
          `<b>${VOLUME_PROFILE_MODE_LABELS[mode]}</b>`,
          `Estymowany wolumen: ${fmtVol(raw)}`,
          `Aktywność: ${activity.toFixed(0)}/100`,
          `Liczba sesji: ${sessions}`,
        ]
        if (meta) {
          if (meta.history_start && meta.history_end) lines.push(`Zakres: ${meta.history_start}–${meta.history_end}`)
          if (mode === 'active' && meta.lookback_sessions) lines.push(`Okno: ${meta.lookback_sessions} sesji · half-life ${meta.half_life_sessions ?? '—'}`)
        }
        return lines.join('<br/>')
      },
    },
    data: bins.map((bin) => {
      const zone = zoneForProfileBin(bin, analysis.zones)
      const color = zone
        ? zoneColor(zone, Math.max(0.10, options.profileOpacity))
        : `rgba(148,163,184,${Math.max(0.06, options.profileOpacity * 0.55).toFixed(3)})`
      // Bar length: raw mode = raw_volume share, otherwise normalized activity.
      const metric = mode === 'raw' ? (bin.raw_volume / maxRaw) * 100 : bin.activity_score
      return [anchor, bin.center_price, metric, bin.price_low, bin.price_high, color, bin.raw_volume, bin.weighted_volume, bin.activity_score, bin.contributing_sessions ?? 0]
    }),
    renderItem: (params: CustomRenderParams, api: CustomRenderApi) => {
      const score = Number(api.value(2))
      const yLow = api.coord([api.value(0), api.value(3)])[1]
      const yHigh = api.coord([api.value(0), api.value(4)])[1]
      const height = Math.max(2, Math.abs(yHigh - yLow) * 0.86)
      const maxWidth = params.coordSys.width * 0.12
      const width = Math.max(2, Math.min(maxWidth, maxWidth * Math.max(0, Math.min(score, 100)) / 100))
      const y = Math.min(yLow, yHigh)
      const gridTop = params.coordSys.y
      const gridBottom = params.coordSys.y + params.coordSys.height
      const clippedY = Math.max(y, gridTop)
      const clippedBottom = Math.min(y + height, gridBottom)
      if (clippedBottom <= clippedY) return null
      return {
        type: 'rect',
        shape: {
          x: params.coordSys.x + params.coordSys.width - width,
          y: clippedY,
          width,
          height: clippedBottom - clippedY,
        },
        style: {
          fill: String(api.value(5)),
          stroke: 'rgba(255,255,255,0.10)',
          lineWidth: 1,
        },
      }
    },
  }
}

export function buildEvidenceBalanceSeries(
  candles: CandleDay[],
  analysis: VolumeZonesResponse | null,
  xAxisIndex: number | null,
  yAxisIndex: number | null,
): object | null {
  if (!analysis || !analysis.timeline.length || xAxisIndex == null || yAxisIndex == null) return null
  const balanceByDate = new Map(analysis.timeline.map((point) => [point.date, point.evidence_balance]))
  return {
    name: 'Siła dowodów',
    type: 'bar',
    xAxisIndex,
    yAxisIndex,
    data: candles.map((candle) => balanceByDate.get(candle.date_quote) ?? null),
    itemStyle: {
      color: (params: ColorCallbackParams) => {
        const value = Number(params.value)
        if (!Number.isFinite(value)) return 'rgba(148,163,184,0.18)'
        return value >= 0 ? 'rgba(34,197,94,0.55)' : 'rgba(239,68,68,0.55)'
      },
    },
  }
}
