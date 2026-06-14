'use client'

import Link from 'next/link'
import ReactECharts from 'echarts-for-react'

export type GoalsProgressData = {
  revActual: number   // actual YTD income in view ccy
  revTarget: number   // pro-rated annual revenue target (× month fraction) in view ccy
  expActual: number   // actual YTD expenses in view ccy
  expBudget: number   // pro-rated annual expense budget (× month fraction) in view ccy
  capActual: number   // actual YTD capital gains in view ccy
  capTarget: number   // pro-rated annual capital gain target (× month fraction) in view ccy
  currency: string
}

type Props = {
  data: GoalsProgressData | null
  href: string
}

type TooltipParam = {
  axisValue?: string | number
  seriesName?: string
  value?: number | null
}

function fmtShort(v: number): string {
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}${Math.round(abs / 1_000)}k`
  return `${sign}${Math.round(abs).toFixed(0)}`
}

function CardShell({
  href,
  children,
}: {
  href: string
  children: React.ReactNode
}) {
  return (
    <Link href={href} className="block group h-full">
      <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full group-hover:bg-slate-800/60 transition-colors cursor-pointer">
        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between flex-shrink-0">
          <p className="text-xs font-medium text-white/50 uppercase tracking-wide">Cele YTD</p>
          <svg
            className="w-3 h-3 text-white/20 group-hover:text-white/40 transition-colors"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>
        {children}
      </div>
    </Link>
  )
}

export function GoalsCard({ data, href }: Props) {
  if (data === null) {
    return (
      <CardShell href={href}>
        <div className="flex flex-col items-center justify-center py-8 gap-1.5 flex-1 min-h-[200px]">
          <svg
            className="w-5 h-5 text-white/15"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z"
            />
          </svg>
          <p className="text-xs text-white/25">Brak celów</p>
        </div>
      </CardShell>
    )
  }

  const revColor = data.revActual >= data.revTarget ? '#22c55e' : '#f59e0b'
  const expColor = data.expActual <= data.expBudget ? '#22c55e' : '#ef4444'
  const capColor = data.capActual < 0 ? '#ef4444' : data.capActual >= data.capTarget ? '#22c55e' : '#f59e0b'
  const ccy = data.currency

  const xMax = Math.max(
    data.revTarget,
    data.revActual,
    data.expBudget,
    data.expActual,
    data.capTarget,
    Math.abs(data.capActual),
    1,
  ) * 1.35
  const xMin = data.capActual < 0 ? data.capActual * 1.35 : 0

  const option = {
    backgroundColor: 'transparent',
    grid: { left: 88, right: 68, top: 18, bottom: 18 },
    xAxis: {
      type: 'value',
      max: xMax,
      min: xMin,
      show: false,
    },
    yAxis: {
      type: 'category',
      data: ['Wydatki', 'Przychody', 'Zysk kap.'],
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: 'rgba(255,255,255,0.45)', fontSize: 10 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'none' },
      backgroundColor: 'rgba(15,23,42,0.92)',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#fff', fontSize: 11 },
      formatter(params: TooltipParam[]) {
        if (!params?.length) return ''
        const label = (params[0]?.axisValue ?? '') as string
        const cel = params.find((p) => p.seriesName === 'Cel YTD')
        const stan = params.find((p) => p.seriesName === 'Stan YTD')
        if (!stan) return ''
        const stanVal = stan.value ?? 0
        const celVal = cel?.value ?? null
        const pct = typeof celVal === 'number' && celVal > 0 ? Math.round((stanVal / celVal) * 100) : 0
        return `<div style="font-size:11px;min-width:150px">
          <div style="margin-bottom:4px;color:rgba(255,255,255,0.45)">${label}</div>
          <div style="display:flex;justify-content:space-between;gap:14px;margin-bottom:2px">
            <span>Stan YTD</span><b>${fmtShort(stanVal)} ${ccy}</b>
          </div>
          ${typeof celVal === 'number'
            ? `<div style="display:flex;justify-content:space-between;gap:14px;color:rgba(255,255,255,0.4)">
                <span>Cel YTD</span><span>${fmtShort(celVal)} ${ccy} &nbsp;(${pct}%)</span>
              </div>`
            : ''}
        </div>`
      },
    },
    series: [
      {
        name: 'Cel YTD',
        type: 'bar',
        data: [data.expBudget, data.revTarget, data.capTarget],
        barMaxWidth: 20,
        itemStyle: { color: 'rgba(255,255,255,0.13)', borderRadius: [0, 3, 3, 0] },
        z: 1,
        label: { show: false },
      },
      {
        name: 'Stan YTD',
        type: 'bar',
        data: [
          { value: data.expActual, itemStyle: { color: expColor, borderRadius: [0, 3, 3, 0] } },
          { value: data.revActual, itemStyle: { color: revColor, borderRadius: [0, 3, 3, 0] } },
          { value: data.capActual, itemStyle: { color: capColor, borderRadius: [0, 3, 3, 0] } },
        ],
        barMaxWidth: 13,
        barGap: '-100%',
        z: 2,
        label: {
          show: true,
          position: 'right',
          color: 'rgba(255,255,255,0.5)',
          fontSize: 9,
          formatter: (p: { value: number }) => `${fmtShort(p.value)} ${ccy}`,
        },
      },
    ],
  }

  return (
    <CardShell href={href}>
      <div className="flex-1">
        <ReactECharts option={option} style={{ height: '220px' }} theme="dark" />
      </div>
    </CardShell>
  )
}
