import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'

import { HoldingsPage } from '@/features/wallet/components/HoldingsPage'
import type { HoldingRawRow, HoldingsResult } from '@/lib/api/holdings'
import { nextUiUnitStory } from '../allure'

const brokerageAccounts = [{ id: 'brokerage-1', name: 'ING Makler' }]
const multiBrokerageAccounts = [
  { id: 'brokerage-1', name: 'ING Makler' },
  { id: 'brokerage-2', name: 'XTB' },
]
const routerPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: routerPush,
  }),
}))

vi.mock('@/features/wallet/components/FavoritesDialog', () => ({
  FavoritesDialog: ({ symbol, name, mic }: { symbol: string; name: string | null; mic: string }) => (
    <div role="dialog" aria-label="Ulubione i alerty">
      <p>Ulubione i alerty</p>
      <p>{symbol} — {name ?? ''}</p>
      <p>{mic}</p>
    </div>
  ),
}))

function row(overrides: Partial<HoldingRawRow>): HoldingRawRow {
  const holding: HoldingRawRow = {
    id: 'PKO',
    accountId: 'brokerage-1',
    symbol: 'PKO',
    instrumentMic: 'XWAR',
    name: 'PKOBP',
    currency: 'PLN',
    accountsDisp: 'ING Makler',
    accountBreakdown: [{
      accountId: 'brokerage-1',
      accountName: 'ING Makler',
      quantity: 10,
      costRaw: 100,
    }],
    quantity: 10,
    avgCostRaw: 10,
    priceRaw: 20,
    costRaw: 100,
    valueRaw: 200,
    pnlAmountRaw: 100,
    pnlPct: 1,
    costView: 100,
    valueView: 200,
    pnlView: 100,
    changePct: 1.2,
    quoteMissing: false,
    ...overrides,
  }
  if (
    overrides.pnlPct !== undefined
    && overrides.priceRaw === undefined
    && overrides.valueRaw === undefined
    && !holding.quoteMissing
  ) {
    holding.valueRaw = holding.costRaw * (1 + overrides.pnlPct)
    holding.priceRaw = holding.quantity > 0 ? holding.valueRaw / holding.quantity : 0
    holding.pnlAmountRaw = holding.valueRaw - holding.costRaw
    holding.valueView = holding.valueRaw
    holding.pnlView = holding.pnlAmountRaw
  }
  if (!overrides.accountBreakdown) {
    holding.accountBreakdown = [{
      accountId: holding.accountId,
      accountName: holding.accountsDisp,
      quantity: holding.quantity,
      costRaw: holding.costRaw,
    }]
  }
  return holding
}

function openRowAccountMenu(symbol: string) {
  const trigger = screen.getByRole('button', { name: `Wybierz rachunki dla ${symbol}` })
  fireEvent.keyDown(trigger, { key: 'Enter', code: 'Enter' })
  return trigger
}

function result(rows: HoldingRawRow[], accounts = brokerageAccounts): HoldingsResult {
  return {
    rows,
    totalValueView: rows.reduce((sum, item) => sum + (item.valueView ?? 0), 0),
    totalCostView: rows.reduce((sum, item) => sum + (item.costView ?? 0), 0),
    viewCcy: 'PLN',
    fxRates: null,
    brokerageAccounts: accounts,
  }
}

function multiAccountRow(overrides: Partial<HoldingRawRow> = {}): HoldingRawRow {
  return row({
    id: 'PKO',
    accountId: 'brokerage-1',
    symbol: 'PKO',
    accountsDisp: '2 rachunki',
    quantity: 15,
    avgCostRaw: 200 / 15,
    priceRaw: 20,
    costRaw: 200,
    valueRaw: 300,
    pnlAmountRaw: 100,
    pnlPct: 0.5,
    costView: 200,
    valueView: 300,
    pnlView: 100,
    accountBreakdown: [
      { accountId: 'brokerage-1', accountName: 'ING Makler', quantity: 10, costRaw: 100 },
      { accountId: 'brokerage-2', accountName: 'XTB', quantity: 5, costRaw: 100 },
    ],
    ...overrides,
  })
}

let holdingsResult = result([])

describe('HoldingsPage', () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    routerPush.mockClear()
    holdingsResult = result([])
    server.resetHandlers()
    server.use(
      http.get('*/api/wallet/holdings', () => HttpResponse.json(holdingsResult)),
    )
  })

  it('does not show positive PnL positions in the losing positions strip', async () => {
    await nextUiUnitStory('Brokerage holdings only show real losses in the losing strip', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'financial-data', 'next-ui'],
    })
    const rows = [
      row({ id: 'AGL', symbol: 'AGL', pnlPct: 0.0547, changePct: -6.18 }),
      row({ id: 'PKO', symbol: 'PKO', pnlPct: 2.7575, changePct: 11 }),
    ]
    holdingsResult = result(rows)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={brokerageAccounts}
      />,
    )

    expect(screen.queryByText('Tracące:')).not.toBeInTheDocument()
    expect(screen.getByText('Zyskujące:')).toBeInTheDocument()
    expect(screen.getByText('PKO +275,75%')).toBeInTheDocument()
    expect(screen.getByText('AGL +5,47%')).toBeInTheDocument()
  })

  it('formats quote change percentages without multiplying them by one hundred', async () => {
    await nextUiUnitStory('Brokerage holdings format quote daily change percentages correctly', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'quotes', 'next-ui'],
    })
    const rows = [
      row({
        id: 'LOSS',
        symbol: 'LOSS',
        name: 'Losing position',
        priceRaw: 5,
        valueRaw: 50,
        valueView: 50,
        pnlAmountRaw: -50,
        pnlView: -50,
        pnlPct: -0.5,
        changePct: -6.18,
      }),
      row({ id: 'GAIN', symbol: 'GAIN', name: 'Gaining position', pnlPct: 1, changePct: 3.25 }),
    ]
    holdingsResult = result(rows)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={brokerageAccounts}
      />,
    )

    expect(screen.getByText('Tracące:')).toBeInTheDocument()
    expect(screen.getByText('LOSS -50,00%')).toBeInTheDocument()
    expect(screen.getByText('-6,18%')).toBeInTheDocument()
    expect(screen.queryByText('-618,00%')).not.toBeInTheDocument()
  })

  it('formats the total PnL percentage as a ratio-based percent in the header', async () => {
    await nextUiUnitStory('Brokerage holdings header shows total PnL percentage from value versus cost', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'pnl', 'next-ui'],
    })
    const rows = [
      row({
        id: 'TOTAL',
        symbol: 'TOTAL',
        quantity: 100,
        avgCostRaw: 930,
        priceRaw: 1143,
        costRaw: 93000,
        valueRaw: 114300,
        pnlAmountRaw: 21300,
        pnlPct: 0.2290322581,
        costView: 93000,
        valueView: 114300,
        pnlView: 21300,
      }),
    ]
    holdingsResult = result(rows)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={brokerageAccounts}
      />,
    )

    expect(screen.getAllByText('+22,90%')).toHaveLength(2)
    expect(screen.queryByText('+0,23%')).not.toBeInTheDocument()
  })

  it('marks holdings without current quotes instead of treating price zero as a loss', async () => {
    await nextUiUnitStory('Brokerage holdings mark missing quotes without creating artificial losses', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'quotes', 'next-ui'],
    })
    const rows = [
      row({
        id: 'OLD',
        symbol: 'OLD',
        name: 'Old renamed instrument',
        priceRaw: 0,
        valueRaw: 0,
        pnlAmountRaw: 0,
        pnlPct: 0,
        costView: null,
        valueView: null,
        pnlView: null,
        changePct: 0,
        quoteMissing: true,
      }),
    ]
    holdingsResult = result(rows)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={brokerageAccounts}
      />,
    )

    expect(screen.getAllByText('Brak notowań')).toHaveLength(2)
    expect(screen.queryByText('Tracące:')).not.toBeInTheDocument()
    expect(screen.queryByText('OLD -100,00%')).not.toBeInTheDocument()
  })

  it('recalculates a multi-account holding from the selected row account without changing row count', async () => {
    await nextUiUnitStory('Brokerage holdings recalculate visible PnL for selected accounts inside one instrument row', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'money', 'filters', 'next-ui'],
    })
    const rows = [multiAccountRow()]
    holdingsResult = result(rows, multiBrokerageAccounts)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={multiBrokerageAccounts}
      />,
    )

    expect(screen.getByText('1 pozycja')).toBeInTheDocument()
    expect(screen.getAllByText(/300,00\sPLN/)).toHaveLength(2)

    openRowAccountMenu('PKO')
    expect(await screen.findByRole('menuitemcheckbox', { name: 'ING Makler' })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'XTB' }))

    const holdingRow = screen.getByText('PKO').closest('tr')
    expect(holdingRow).not.toBeNull()
    await waitFor(() => {
      expect(within(holdingRow!).getByText('10')).toBeInTheDocument()
      expect(within(holdingRow!).getByText(/200,00\sPLN/)).toBeInTheDocument()
      expect(within(holdingRow!).getByText(/\+100,00\sPLN/)).toBeInTheDocument()
      expect(within(holdingRow!).getByText('+100,00%')).toBeInTheDocument()
      expect(screen.getByText('1 pozycja')).toBeInTheDocument()
    })
    expect(screen.queryByText(/300,00\sPLN/)).not.toBeInTheDocument()
  })

  it('resets row account selections when the search query changes', async () => {
    await nextUiUnitStory('Brokerage holdings reset row account selection when search changes', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'search', 'filters', 'next-ui'],
    })
    const rows = [multiAccountRow()]
    holdingsResult = result(rows, multiBrokerageAccounts)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={multiBrokerageAccounts}
      />,
    )

    openRowAccountMenu('PKO')
    fireEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'XTB' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Wybierz rachunki dla PKO' })).toHaveTextContent('ING Makler')
    })

    fireEvent.change(screen.getByPlaceholderText('Szukaj instrumentu…'), { target: { value: 'pk' } })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Wybierz rachunki dla PKO' })).toHaveTextContent('2 rachunki')
      expect(screen.getAllByText(/300,00\sPLN/)).toHaveLength(2)
      expect(screen.getByText('1 pozycja')).toBeInTheDocument()
    })
  })

  it('opens favorites dialog from the holding context menu', async () => {
    await nextUiUnitStory('Brokerage holdings context menu opens favorites for a held instrument', {
      severity: 'normal',
      tags: ['wallet', 'brokerage', 'holdings', 'favorites', 'next-ui'],
    })
    const rows = [
      row({
        id: 'FAV',
        symbol: 'FAV',
        instrumentMic: 'XWAR',
        name: 'Favorite Holding',
      }),
    ]
    holdingsResult = result(rows)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={brokerageAccounts}
      />,
    )

    const symbolCell = screen.getByText('FAV')
    const holdingRow = symbolCell.closest('tr')
    expect(holdingRow).not.toBeNull()
    fireEvent.contextMenu(holdingRow!)
    fireEvent.click(screen.getByRole('button', { name: 'Ulubione' }))

    expect(await screen.findByText('Ulubione i alerty')).toBeInTheDocument()
    expect(screen.getByText('FAV — Favorite Holding')).toBeInTheDocument()
    expect(screen.getByText('XWAR')).toBeInTheDocument()
  })

  it('opens a holding correction dialog and sends an audited ADJUSTMENT event', async () => {
    await nextUiUnitStory('Brokerage holdings can create audited holding adjustment events', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'adjustment', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(
      http.post('*/api/wallet/brokerage/event', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ success: true })
      }),
    )
    const rows = [
      row({
        id: 'OLD',
        accountId: 'brokerage-1',
        symbol: 'OLD',
        instrumentMic: 'XWAR',
        name: 'Old renamed instrument',
        quantity: 10,
        avgCostRaw: 12.5,
        priceRaw: 0,
        valueRaw: 0,
        pnlAmountRaw: 0,
        pnlPct: 0,
        costView: null,
        valueView: null,
        pnlView: null,
        changePct: 0,
        quoteMissing: true,
      }),
    ]
    holdingsResult = result(rows)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={brokerageAccounts}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Split lub korekta OLD' }))
    await screen.findByRole('dialog')
    expect(screen.getByLabelText('Ilość po korekcie *')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Ilość po korekcie *'), { target: { value: '13' } })
    fireEvent.change(screen.getByLabelText('Śr. cena po korekcie *'), { target: { value: '50,25' } })
    fireEvent.change(screen.getByLabelText('Notatka korekty *'), {
      target: { value: 'Korekta holdingu, stara nazwa: WORKSERV' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => {
      expect(requests).toHaveLength(1)
    })
    await expect(requests[0]?.json()).resolves.toEqual(expect.objectContaining({
      brokerage_account_id: 'brokerage-1',
      instrument_symbol: 'OLD',
      instrument_mic: 'XWAR',
      instrument_name: 'Old renamed instrument',
      kind: 'ADJUSTMENT',
      quantity: '13',
      price: '50.25',
      currency: 'PLN',
      split_ratio: '0',
      note: 'Korekta holdingu, stara nazwa: WORKSERV',
    }))
  })

  it('opens a holding split dialog and sends a SPLIT event from the holdings row', async () => {
    await nextUiUnitStory('Brokerage holdings can create split events directly from a holding row', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'split', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(
      http.post('*/api/wallet/brokerage/event', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ success: true })
      }),
    )
    const rows = [
      row({
        id: 'DEL',
        accountId: 'brokerage-1',
        symbol: 'DEL',
        instrumentMic: 'XWAR',
        name: 'Delko',
        quantity: 10,
        avgCostRaw: 20,
        quoteMissing: false,
      }),
    ]
    holdingsResult = result(rows)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={brokerageAccounts}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Split lub korekta DEL' }))
    await screen.findByRole('dialog')
    fireEvent.change(screen.getByLabelText('Współczynnik splitu *'), { target: { value: '0,1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => {
      expect(requests).toHaveLength(1)
    })
    await expect(requests[0]?.json()).resolves.toEqual(expect.objectContaining({
      brokerage_account_id: 'brokerage-1',
      instrument_symbol: 'DEL',
      instrument_mic: 'XWAR',
      instrument_name: 'Delko',
      kind: 'SPLIT',
      quantity: '0',
      price: '0',
      currency: 'PLN',
      split_ratio: '0.1',
      note: null,
    }))
  })

  it('opens a holding conversion dialog and sends source and target instrument data', async () => {
    await nextUiUnitStory('Brokerage holdings can create instrument conversion events from a holding row', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'holdings', 'conversion', 'next-ui'],
    })
    const requests: Request[] = []
    server.use(
      http.post('*/api/wallet/brokerage/event', async ({ request }) => {
        requests.push(request.clone())
        return HttpResponse.json({ success: true })
      }),
    )
    const rows = [
      row({
        id: 'WORK',
        accountId: 'brokerage-1',
        symbol: 'WORK',
        instrumentMic: 'XWAR',
        name: 'WORKSERV SA',
        quantity: 1000,
        avgCostRaw: 2,
        quoteMissing: false,
      }),
    ]
    holdingsResult = result(rows)

    render(
      <HoldingsPage
        initialRows={rows}
        initialTotalValue={holdingsResult.totalValueView}
        initialTotalCost={holdingsResult.totalCostView}
        initialViewCcy="PLN"
        fxRates={null}
        brokerageAccounts={brokerageAccounts}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Split lub korekta WORK' }))
    await screen.findByRole('dialog')
    fireEvent.click(screen.getAllByText('SPLIT')[0]!)
    fireEvent.click(screen.getByRole('option', { name: 'Konwersja' }))
    fireEvent.change(screen.getByLabelText('Ilość do konwersji *'), { target: { value: '1000' } })
    fireEvent.change(screen.getByLabelText('Współczynnik konwersji *'), { target: { value: '0,2' } })
    fireEvent.change(screen.getByLabelText('Nowy symbol *'), { target: { value: 'gig' } })
    fireEvent.change(screen.getByLabelText('Rynek *'), { target: { value: 'xwar' } })
    fireEvent.change(screen.getByLabelText('Nazwa'), { target: { value: 'GIGROUP SA' } })
    fireEvent.change(screen.getByLabelText('Notatka konwersji *'), {
      target: { value: 'WORKSERV -> GIGROUP, scalenie 1:5' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => {
      expect(requests).toHaveLength(1)
    })
    await expect(requests[0]?.json()).resolves.toEqual(expect.objectContaining({
      brokerage_account_id: 'brokerage-1',
      instrument_symbol: 'WORK',
      instrument_mic: 'XWAR',
      instrument_name: 'WORKSERV SA',
      kind: 'CONVERSION',
      quantity: '1000',
      price: '0',
      currency: 'PLN',
      split_ratio: '0.2',
      note: 'WORKSERV -> GIGROUP, scalenie 1:5',
      target_instrument_symbol: 'GIG',
      target_instrument_mic: 'XWAR',
      target_instrument_name: 'GIGROUP SA',
    }))
  })
})
