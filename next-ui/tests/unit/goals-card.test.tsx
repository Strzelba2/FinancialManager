import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { GoalsCard } from '@/features/wallet/components/GoalsCard'
import { nextUiUnitStory } from '../allure'

type GoalsChartOption = {
  yAxis: { data: string[] }
  xAxis: { min: number }
  series: [
    { data: number[] },
    {
      data: Array<{ value: number; itemStyle: { color: string } }>
      label: { formatter: (param: { value: number }) => string }
    },
  ]
  tooltip: { formatter: (params: Array<Record<string, unknown>>) => string }
}

const chartOptions = vi.hoisted(() => [] as GoalsChartOption[])

vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option: GoalsChartOption }) => {
    chartOptions.push(option)
    return <div data-testid="goals-chart" />
  },
}))

describe('GoalsCard', () => {
  it('renders capital gain progress with a negative range and tooltip values', async () => {
    await nextUiUnitStory('Wallet goals card charts annual capital gain progress separately', {
      severity: 'critical',
      tags: ['wallet', 'goals', 'money', 'financial-data', 'next-ui'],
    })
    chartOptions.length = 0

    render(
      <GoalsCard
        href="/wallet?modal=goals"
        data={{
          revActual: 18000,
          revTarget: 20000,
          expActual: 7000,
          expBudget: 9000,
          capActual: -1500,
          capTarget: 3000,
          currency: 'PLN',
        }}
      />,
    )

    expect(screen.getByTestId('goals-chart')).toBeInTheDocument()
    const option = chartOptions[0]!
    expect(option.yAxis.data).toEqual(['Wydatki', 'Przychody', 'Zysk kap.'])
    expect(option.xAxis.min).toBeCloseTo(-2025)
    expect(option.series[0].data).toEqual([9000, 20000, 3000])
    expect(option.series[1].data[2]).toEqual(expect.objectContaining({
      value: -1500,
      itemStyle: expect.objectContaining({ color: '#ef4444' }),
    }))

    const labelFormatter = option.series[1].label.formatter
    expect(labelFormatter({ value: -1_200_000 })).toBe('-1.2M PLN')
    expect(labelFormatter({ value: -1500 })).toBe('-2k PLN')
    expect(labelFormatter({ value: 950 })).toBe('950 PLN')

    const tooltipFormatter = option.tooltip.formatter
    expect(tooltipFormatter([])).toBe('')
    expect(tooltipFormatter([
      { axisValue: 'Zysk kap.', seriesName: 'Cel YTD', value: 3000 },
    ])).toBe('')
    expect(tooltipFormatter([
      { axisValue: 'Zysk kap.', seriesName: 'Stan YTD', value: -1500 },
    ])).toContain('-2k PLN')
    expect(tooltipFormatter([
      { axisValue: 'Zysk kap.', seriesName: 'Cel YTD', value: 3000 },
      { axisValue: 'Zysk kap.', seriesName: 'Stan YTD', value: 1500 },
    ])).toContain('(50%)')
  })
})
