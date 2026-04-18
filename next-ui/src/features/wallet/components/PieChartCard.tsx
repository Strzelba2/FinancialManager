'use client'

import ReactECharts from 'echarts-for-react'

export type PieSlice = { name: string; value: number }

type Props = {
  title: string
  series: PieSlice[]
  emptyMsg?: string
}

export function PieChartCard({ title, series, emptyMsg = 'Brak danych' }: Props) {
  const data = series.filter((s) => s.value > 0)

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15,23,42,0.92)',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#fff', fontSize: 11 },
      formatter: '{b}: {d}%',
    },
    legend: {
      orient: 'horizontal',
      bottom: 4,
      textStyle: { color: 'rgba(255,255,255,0.45)', fontSize: 10 },
      icon: 'circle',
      itemWidth: 7,
      itemHeight: 7,
      itemGap: 10,
    },
    series: [
      {
        type: 'pie',
        radius: ['42%', '66%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 11, fontWeight: 'bold', color: '#fff' },
        },
        data,
      },
    ],
  }

  return (
    <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col">
      <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
        <p className="text-xs font-medium text-white/50 uppercase tracking-wide">{title}</p>
      </div>

      {data.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 gap-1.5 flex-1 min-h-[180px]">
          <p className="text-xs text-white/25">{emptyMsg}</p>
        </div>
      ) : (
        <ReactECharts option={option} style={{ height: '220px' }} theme="dark" />
      )}
    </div>
  )
}
