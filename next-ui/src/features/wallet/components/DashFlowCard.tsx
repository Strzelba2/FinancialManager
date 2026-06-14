'use client'

import ReactECharts from 'echarts-for-react'

export type DashFlowData = {
  months: string[]
  inc: number[]    
  exp: number[]    
  tax: number[]
  cap: number[]   
  currency: string
}

type Props = {
  data: DashFlowData
}

// ── number formatting ─────────────────────────────────────────────────────────

function fmtVal(v: number, ccy: string): string {
  const abs = Math.abs(v)
  const sign = v < 0 ? '−' : ''
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M ${ccy}`
  if (abs >= 1_000) return `${sign}${Math.round(abs / 1_000)}k ${ccy}`
  return `${sign}${Math.round(abs)} ${ccy}`
}

// ── empty state ───────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-1.5 flex-1 min-h-[200px]">
      <svg className="w-5 h-5 text-white/15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
      <p className="text-xs text-white/25">Brak danych przepływów</p>
    </div>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export function DashFlowCard({ data }: Props) {
  const hasData = data.months.length > 0

  const expNeg = data.exp.map((v) => (v === 0 ? null : -Math.abs(v)))
  const taxNeg = data.tax.map((v) => (v === 0 ? null : -Math.abs(v)))
  const profit = computeDashFlowProfit(data)

  const ccy = data.currency
  const legendData = ['Przychody', 'Wydatki', 'Podatki', 'Kapitał', 'Zysk']

  const option = {
    backgroundColor: 'transparent',
    legend: {
      top: 4,
      data: legendData,
      textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 10 },
      itemWidth: 14,
      itemHeight: 8,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(15,23,42,0.92)',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#fff', fontSize: 11 },
      confine: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter(params: any[]) {
        if (!params?.length) return ''
        const label = params[0]?.axisValue ?? ''
        const rows = params
          .filter((p) => p.value !== null && p.value !== undefined && p.value !== 0)
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          .map((p: any) => `<div style="display:flex;justify-content:space-between;gap:14px;">
              <span style="color:rgba(255,255,255,0.5)">${p.marker}${p.seriesName}</span>
              <b>${fmtVal(p.value as number, ccy)}</b>
            </div>`)
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
      axisTick: { alignWithLabel: true },
      axisLabel: { color: 'rgba(255,255,255,0.35)', fontSize: 9, hideOverlap: true },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        color: 'rgba(255,255,255,0.35)',
        fontSize: 9,
        formatter: (v: number) => fmtVal(v, ccy),
      },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
    },
    grid: { left: 16, right: 16, bottom: 28, top: 40, containLabel: true },
    barCategoryGap: '12%',
    barGap: '6%',
    series: [
      {
        name: 'Przychody',
        type: 'bar',
        data: data.inc,
        itemStyle: { color: '#3b82f6' },
        emphasis: { focus: 'series' },
      },
      {
        name: 'Wydatki',
        type: 'bar',
        data: expNeg,
        itemStyle: { color: '#ef4444' },
        emphasis: { focus: 'series' },
      },
      {
        name: 'Podatki',
        type: 'bar',
        data: taxNeg,
        itemStyle: { color: '#f59e0b' },
        emphasis: { focus: 'series' },
      },
      {
        name: 'Kapitał',
        type: 'bar',
        data: data.cap,
        itemStyle: { color: '#8b5cf6' },
        emphasis: { focus: 'series' },
      },
      {
        name: 'Zysk',
        type: 'bar',
        data: profit,
        itemStyle: { color: '#22c55e' },
        emphasis: { focus: 'series' },
      },
    ],
  }

  return (
    <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full">
      <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
        <p className="text-xs font-medium text-white/50 uppercase tracking-wide">Dash Flow</p>
      </div>
      {!hasData ? (
        <EmptyState />
      ) : (
        <div className="flex-1 p-1">
          <ReactECharts option={option} style={{ height: '280px' }} theme="dark" />
        </div>
      )}
    </div>
  )
}

export function computeDashFlowProfit(data: DashFlowData): number[] {
  return data.inc.map((inc, i) => {
    const e = data.exp[i] ?? 0
    const t = data.tax[i] ?? 0
    const c = data.cap[i] ?? 0
    return inc + c - Math.abs(e) - Math.abs(t)
  })
}
