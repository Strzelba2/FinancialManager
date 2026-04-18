'use client'

import ReactECharts from 'echarts-for-react'

export type AssetsChartData = {
  months: string[]
  nominal: (number | null)[]
  real: (number | null)[]       
  inflacja: (number | null)[]   
  mom: (number | null)[]        
  currency: string
}

type Props = {
  data: AssetsChartData
}

const SERIES = {
  nominal: 'Nominalnie',
  real: 'Realnie (CPI)',
  inflation: 'Inflacja %',
  mom: 'Zmiana m/m',
} as const

const COLORS = {
  nominal: '#34d399',
  real: '#60a5fa',
  inflation: '#f59e0b',
  mom: '#f87171',
} as const

const AXIS_LAYOUT = {
  gridRight: 80,
  momOffset: 72,
} as const

// ── formatting ────────────────────────────────────────────────────────────────

function fmtNumber(v: number): string {
  return v.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function fmtVal(v: number, ccy: string): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M ${ccy}`
  if (abs >= 1_000) return `${(v / 1_000).toFixed(2)}k ${ccy}`
  return `${fmtNumber(v)} ${ccy}`
}

function fmtValFull(v: number, ccy: string): string {
  return `${fmtNumber(v)} ${ccy}`
}

function fmtPct(v: number): string {
  return `${v.toFixed(2)}%`
}

function hasNumericPoints(values: (number | null)[]): boolean {
  return values.some((value) => typeof value === 'number' && Number.isFinite(value))
}

// ── empty state ───────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-1.5 flex-1 min-h-[200px]">
      <svg className="w-5 h-5 text-white/15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
      </svg>
      <p className="text-xs text-white/25">Brak danych historycznych</p>
    </div>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export function AssetsLineCard({ data }: Props) {
  const hasData = data.months.length > 0 && data.nominal.some((v) => v !== null)
  const hasReal = hasNumericPoints(data.real)
  const hasInflation = hasNumericPoints(data.inflacja)
  const hasMom = hasNumericPoints(data.mom)
  const ccy = data.currency
  const showMom = hasData

  const series: any[] = []
  const leftLegend: string[]  = []  

  if (hasData) {
    leftLegend.push(SERIES.nominal)
    series.push({
      name: SERIES.nominal,
      type: 'line',
      data: data.nominal,
      color: COLORS.nominal,
      smooth: true,
      connectNulls: true,
      showSymbol: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: COLORS.nominal },
      itemStyle: { color: COLORS.nominal },
      areaStyle: { color: COLORS.nominal, opacity: 0.10 },
      yAxisIndex: 0,
    })
  }

  if (hasReal) {
    leftLegend.push(SERIES.real)
    series.push({
      name: SERIES.real,
      type: 'line',
      data: data.real,
      color: COLORS.real,
      smooth: true,
      connectNulls: true,
      showSymbol: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, type: 'dashed', color: COLORS.real },
      itemStyle: { color: COLORS.real },
      yAxisIndex: 0,
    })
  }

  if (hasInflation) {
    series.push({
      name: SERIES.inflation,
      type: 'line',
      data: data.inflacja,
      color: COLORS.inflation,
      smooth: true,
      connectNulls: true,
      showSymbol: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: COLORS.inflation },
      itemStyle: { color: COLORS.inflation },
      yAxisIndex: 1,
    })
  }

  if (showMom) {
    series.push({
      name: SERIES.mom,
      type: 'line',
      data: hasMom ? data.mom : data.months.map(() => null),
      color: COLORS.mom,
      smooth: true,
      connectNulls: true,
      showSymbol: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: COLORS.mom },
      itemStyle: { color: COLORS.mom },
      yAxisIndex: 2,
    })
  }

  const legendStyle = {
    textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 10 },
    itemWidth: 14,
    itemHeight: 8,
    top: 6,
  }

  const legends = [
    { ...legendStyle, left: 8, data: leftLegend },
  ]

  const option = {
    backgroundColor: 'transparent',
    legend: legends,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', snap: true },
      backgroundColor: 'rgba(15,23,42,0.92)',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#fff', fontSize: 11 },
      confine: true,
      formatter(params: any[]) {
        if (!params?.length) return ''
        const label = params[0]?.axisValue ?? ''
        const pctSeries = new Set<string>([SERIES.inflation])
        const rows = params
          .filter((p) => p.value !== null && p.value !== undefined)
          .map((p: any) => {
            const isPercent = pctSeries.has(p.seriesName as string)
            const valStr = isPercent
              ? fmtPct(p.value as number)
              : fmtValFull(p.value as number, ccy)
            return `<div style="display:flex;justify-content:space-between;gap:14px;">
              <span style="color:rgba(255,255,255,0.5)">${p.marker}${p.seriesName}</span>
              <b>${valStr}</b>
            </div>`
          })
          .join('')
        return `<div style="font-size:11px;min-width:210px">
          <div style="margin-bottom:4px;color:rgba(255,255,255,0.4)">${label}</div>
          ${rows}
        </div>`
      },
    },
    xAxis: {
      type: 'category',
      data: data.months,
      boundaryGap: false,
      axisLabel: { color: 'rgba(255,255,255,0.35)', fontSize: 9, hideOverlap: true, margin: 6 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        axisPointer: {
          label: {
            formatter: ({ value }: { value: number }) => fmtValFull(value, ccy),
          },
        },
        axisLabel: {
          color: 'rgba(255,255,255,0.45)',
          fontSize: 9,
          formatter: (v: number) => fmtVal(v, ccy),
        },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      },
      {
        type: 'value',
        position: 'right',
        axisPointer: {
          label: {
            formatter: ({ value }: { value: number }) => fmtPct(value),
          },
        },
        axisLabel: {
          color: COLORS.inflation,
          fontSize: 9,
          formatter: (v: number) => fmtPct(v),
        },
        axisLine: { show: true, lineStyle: { color: 'rgba(245,158,11,0.45)' } },
        splitLine: { show: false },
      },
      {
        type: 'value',
        position: 'right',
        offset: 72,
        axisPointer: {
          label: {
            formatter: ({ value }: { value: number }) => fmtValFull(value, ccy),
          },
        },
        axisLabel: {
          color: COLORS.mom,
          fontSize: 9,
          formatter: (v: number) => fmtVal(v, ccy),
        },
        axisLine: { show: true, lineStyle: { color: 'rgba(248,113,113,0.45)' } },
        splitLine: { show: false },
      },
    ],
    grid: { left: 20, right: AXIS_LAYOUT.gridRight, bottom: 28, top: 44, containLabel: true },
    series,
  }

  return (
    <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full">
      <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
        <p className="text-xs font-medium text-white/50 uppercase tracking-wide">
          Aktywa: Nominalnie vs Realnie
        </p>
      </div>
      {!hasData ? (
        <EmptyState />
      ) : (
        <div className="flex-1 p-1 relative">
          {hasInflation && (
            <div
              className="pointer-events-none absolute top-[6px] z-10"
              style={{
                right: `${AXIS_LAYOUT.gridRight + AXIS_LAYOUT.momOffset}px`,
                width: 0,
              }}
            >
              <div className="-translate-x-1/2 flex w-[64px] flex-col items-center gap-1 leading-none text-center text-[9px] text-white/55">
                <span className="inline-block h-0.5 w-4 rounded-full" style={{ backgroundColor: COLORS.inflation }} />
                <span>Inflacja %</span>
              </div>
            </div>
          )}
          {showMom && (
            <div
              className="pointer-events-none absolute top-[6px] z-10"
              style={{
                right: `${AXIS_LAYOUT.gridRight}px`,
                width: 0,
              }}
            >
              <div className="-translate-x-1/2 flex w-[72px] flex-col items-center gap-1 leading-none text-center text-[9px] text-white/55">
                <span className="inline-block h-0.5 w-4 rounded-full" style={{ backgroundColor: COLORS.mom }} />
                <span>Zmiana m/m</span>
              </div>
            </div>
          )}
          <ReactECharts option={option} style={{ height: '290px' }} theme="dark" />
        </div>
      )}
    </div>
  )
}
