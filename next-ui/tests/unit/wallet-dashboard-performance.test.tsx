import { render, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { buildPerfRowsFromHoldings } from '@/app/(dashboard)/wallet/page'
import { StockPerfCard } from '@/features/wallet/components/StockTableCard'
import type { HoldingRawRow } from '@/lib/api/holdings'
import { nextUiUnitStory } from '../allure'

function holding(symbol: string, pnlPct: number, pnlView: number): HoldingRawRow {
  const cost = 1000
  const value = cost + pnlView
  return {
    id: symbol,
    accountId: 'cross-wallet',
    symbol,
    instrumentMic: 'XWAR',
    name: symbol,
    currency: 'PLN',
    accountsDisp: '2 rachunki',
    accountBreakdown: [
      { accountId: 'account-1', accountName: 'Rachunek 1', quantity: 5, costRaw: cost / 2 },
      { accountId: 'account-2', accountName: 'Rachunek 2', quantity: 5, costRaw: cost / 2 },
    ],
    quantity: 10,
    avgCostRaw: cost / 10,
    priceRaw: value / 10,
    costRaw: cost,
    valueRaw: value,
    pnlAmountRaw: pnlView,
    pnlPct,
    costView: cost,
    valueView: value,
    pnlView,
    changePct: 0,
    quoteMissing: false,
  }
}

describe('wallet dashboard performance cards', () => {
  it('renders the correct five of six aggregated gains and losses', async () => {
    await nextUiUnitStory('Wallet dashboard renders top five aggregated holdings in both cards', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'money', 'next-ui'],
    })

    const rows = [
      holding('GAIN-1', 0.5, 500),
      holding('GAIN-2', 1, 1000),
      holding('GAIN-3', 0.8, 800),
      holding('GAIN-4', 0.7, 700),
      holding('GAIN-5', 0.6, 600),
      holding('GAIN-6', 0.4, 400),
      holding('LOSS-1', -0.6, -600),
      holding('LOSS-2', -0.9, -900),
      holding('LOSS-3', -0.8, -800),
      holding('LOSS-4', -0.7, -700),
      holding('LOSS-5', -0.5, -500),
      holding('LOSS-6', -0.4, -400),
    ]
    const gainers = buildPerfRowsFromHoldings(rows, 'PLN', 'desc')
    const losers = buildPerfRowsFromHoldings(rows, 'PLN', 'asc')

    const { container } = render(
      <>
        <StockPerfCard title="Największe zyski" rows={gainers} currency="PLN" />
        <StockPerfCard title="Największe straty" rows={losers} currency="PLN" />
      </>,
    )

    const tables = container.querySelectorAll<HTMLTableElement>('table')
    expect(tables).toHaveLength(2)
    const gainsTable = tables[0]
    const lossesTable = tables[1]
    if (!gainsTable || !lossesTable) throw new Error('Expected gains and losses tables')

    expect(gainsTable.querySelectorAll('tbody tr')).toHaveLength(5)
    expect(lossesTable.querySelectorAll('tbody tr')).toHaveLength(5)
    expect(within(gainsTable).getByText('GAIN-2')).toBeInTheDocument()
    expect(within(gainsTable).getByText('GAIN-1')).toBeInTheDocument()
    expect(within(gainsTable).queryByText('GAIN-6')).not.toBeInTheDocument()
    expect(within(lossesTable).getByText('LOSS-2')).toBeInTheDocument()
    expect(within(lossesTable).getByText('-900 PLN')).toBeInTheDocument()
    expect(within(lossesTable).getByText('LOSS-5')).toBeInTheDocument()
    expect(within(lossesTable).queryByText('LOSS-6')).not.toBeInTheDocument()
  })
})
