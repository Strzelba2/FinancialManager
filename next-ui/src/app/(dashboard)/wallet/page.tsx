// Main wallet dashboard — Server Component.
// Mirrors build_body() in pages/wallet/user_wallet.py.

import { headers } from 'next/headers'
import { Decimal } from 'decimal.js'
import { syncUser, getLatestRealEstatePrice, listWalletGoals, listRecurringExpenses } from '@/lib/api/wallet'
import { saveWalletUserId } from '@/lib/api/session'
import { getFxRates } from '@/lib/api/nbp'
import { fetchHoldings } from '@/lib/api/holdings'
import type { HoldingRawRow } from '@/lib/api/holdings'
import { KpiCard } from '@/features/wallet/components/KpiCard'
import { StockPerfCard, ObservedStocksCard } from '@/features/wallet/components/StockTableCard'
import { PriceAlertsCard } from '@/features/wallet/components/PriceAlertsCard'
import type { PerfRow } from '@/features/wallet/components/StockTableCard'
import { PieChartCard } from '@/features/wallet/components/PieChartCard'
import type { PieSlice } from '@/features/wallet/components/PieChartCard'
import { GoalsCard } from '@/features/wallet/components/GoalsCard'
import type { GoalsProgressData } from '@/features/wallet/components/GoalsCard'
import { GoalsDialogWrapper } from '@/features/wallet/components/GoalsDialogWrapper'
import { DepositTransactionsCard } from '@/features/wallet/components/DepositTransactionsCard'
import type { DepositTxRow } from '@/features/wallet/components/DepositTransactionsCard'
import { BrokerageTransactionsCard } from '@/features/wallet/components/BrokerageTransactionsCard'
import type { BrokerageTxRow } from '@/features/wallet/components/BrokerageTransactionsCard'
import { RecurringExpensesCard } from '@/features/wallet/components/RecurringExpensesCard'
import type { RecurringExpenseRow } from '@/features/wallet/components/RecurringExpensesCard'
import { RecurringExpensesDialogWrapper } from '@/features/wallet/components/RecurringExpensesDialogWrapper'
import type { ExpenseWalletOpt } from '@/features/wallet/components/RecurringExpensesDialog'
import { AssetsLineCard } from '@/features/wallet/components/AssetsLineCard'
import type { AssetsChartData } from '@/features/wallet/components/AssetsLineCard'
import { DashFlowCard } from '@/features/wallet/components/DashFlowCard'
import type { DashFlowData } from '@/features/wallet/components/DashFlowCard'
import { MarketDataNotice } from '@/features/wallet/components/MarketDataNotice'
import { NoWalletState } from '@/features/wallet/components/NoWalletState'
import { NoAccountState } from '@/features/wallet/components/NoAccountState'
import { WalletToolbar } from '@/features/wallet/components/WalletToolbar'
import { CreateWalletDialogWrapper } from '@/features/wallet/components/CreateWalletDialogWrapper'
import { DeleteWalletDialogWrapper } from '@/features/wallet/components/DeleteWalletDialogWrapper'
import { CreateAccountDialogWrapper } from '@/features/wallet/components/CreateAccountDialogWrapper'
import { InvestmentsDialogWrapper } from '@/features/wallet/components/InvestmentsDialogWrapper'
import { DebtsDialogWrapper } from '@/features/wallet/components/DebtsDialogWrapper'
import { NotesDialogWrapper } from '@/features/wallet/components/NotesDialogWrapper'
import { TransactionsDialogWrapper } from '@/features/wallet/components/TransactionsDialogWrapper'
import type { RealEstateRow, MetalRow, WalletOpt } from '@/features/wallet/components/InvestmentsDialog'
import type { DebtRow, DebtWalletOpt } from '@/features/wallet/components/DebtsDialog'
import type {
  TransactionAccountOpt,
  TransactionBrokerageAccountOpt,
} from '@/features/wallet/components/TransactionsDialog'
import { logger } from '@/lib/logger'
import { getStockServiceStatus } from '@/lib/api/stock'
import {
  convertDecimalCurrency as conv,
  dec,
  formatWholeCurrency as fmtKpi,
  type NullableFxRates,
} from '@/lib/money'
import type { Currency, WalletListItem, YearGoalOut, RecurringExpenseOut } from '@/lib/types/wallet'

function computeCash(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): Decimal {
  return wallets.reduce((total, w) =>
    w.accounts.reduce((sum, a) => {
      const amount = dec(a.available)
      return sum.plus(conv(amount, a.currency, ccy, rates))
    }, total),
  new Decimal(0))
}

function computeBrokerage(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): Decimal {
  return wallets.reduce((total, w) =>
    w.brokerage_accounts.reduce((s, ba) =>
      Object.entries(ba.totals_by_currency).reduce((ss, [fromCcy, amount]) =>
        ss.plus(conv(dec(amount), fromCcy, ccy, rates)), s),
    total),
  new Decimal(0))
}

function estateKey(re: WalletListItem['real_estates'][0], fallbackCcy: Currency): string {
  return `${re.type ?? ''}|${re.country ?? ''}|${re.city ?? ''}|${re.purchase_currency ?? fallbackCcy}`
}

function estateValue(re: WalletListItem['real_estates'][0], fallbackCcy: Currency, priceMap: Map<string, string>): Decimal {
  const perM2 = priceMap.get(estateKey(re, fallbackCcy))
  if (perM2 && re.area_m2) return dec(re.area_m2).mul(dec(perM2))
  return dec(re.purchase_price)
}

function computeEstates(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates, priceMap: Map<string, string>): Decimal {
  return wallets.reduce((total, w) =>
    w.real_estates.reduce((s, re) =>
      s.plus(conv(estateValue(re, ccy, priceMap), re.purchase_currency ?? ccy, ccy, rates)),
    total),
  new Decimal(0))
}

function computeMetals(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): Decimal {
  return wallets.reduce((total, w) =>
    w.metal_holdings.reduce((s, m) => {
      if (m.price && dec(m.price).gt(0)) {
        const val = dec(m.price).mul(dec(m.grams))
        const fromCcy = m.price_currency ?? ccy
        return s.plus(conv(val, fromCcy, ccy, rates))
      }
      return s.plus(conv(dec(m.cost_basis), m.cost_currency ?? ccy, ccy, rates))
    }, total),
  new Decimal(0))
}

function computeDebts(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): Decimal {
  return wallets.reduce((total, w) =>
    w.debts.reduce((sum, d) =>
      sum.plus(conv(dec(d.amount), d.currency, ccy, rates)),
    total),
  new Decimal(0))
}

export function computeExpensesYtd(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): Decimal {
  const total = wallets.reduce((walletSum, w) =>
    Object.entries(w.expense_ytd_by_currency).reduce((currencySum, [fromCcy, amount]) =>
      currencySum.plus(conv(dec(amount), fromCcy, ccy, rates)),
    walletSum),
  new Decimal(0))

  return total.abs()
}

function computeCapitalGains(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): Decimal {
  return wallets.reduce((total, w) => {
    const maps = [
      w.capital_gains_deposit_ytd,
      w.capital_gains_broker_ytd,
      w.capital_gains_real_estate_ytd,
      w.capital_gains_metal_ytd,
    ]
    return maps.reduce((s, map) =>
      Object.entries(map).reduce((ss, [fromCcy, amount]) =>
        ss.plus(conv(dec(amount), fromCcy, ccy, rates)),
      s),
    total)
  }, new Decimal(0))
}

function debtSubtitle(wallets: WalletListItem[]): string {
  const debts = wallets.flatMap((wallet) => wallet.debts)
  if (debts.length === 0) return 'brak zobowiązań'

  const avgRate = debts
    .reduce((sum, debt) => sum.plus(dec(debt.interest_rate_pct)), new Decimal(0))
    .div(debts.length)

  const label = debts.length === 1 ? 'kredyt' : debts.length <= 4 ? 'kredyty' : 'kredytów'
  return `${debts.length} ${label} · średn. ${avgRate.toFixed(1)}%`
}

function computeAllocationSeries(
  wallets: WalletListItem[],
  ccy: Currency,
  rates: NullableFxRates,
  priceMap: Map<string, string>,
): PieSlice[] {
  const totals: Record<string, Decimal> = {}

  function add(originalCcy: string, amountInOriginalCcy: Decimal) {
    if (amountInOriginalCcy.lte(0)) return
    const inViewCcy = conv(amountInOriginalCcy, originalCcy, ccy, rates)
    totals[originalCcy] = (totals[originalCcy] ?? new Decimal(0)).plus(inViewCcy)
  }

  for (const w of wallets) {
    for (const a of w.accounts) add(a.currency, dec(a.available))
    for (const ba of w.brokerage_accounts) {
      for (const [cur, amount] of Object.entries(ba.totals_by_currency)) add(cur, dec(amount))
    }
    for (const re of w.real_estates) {
      add(re.purchase_currency ?? ccy, estateValue(re, ccy, priceMap))
    }
    for (const m of w.metal_holdings) {
      if (m.price && dec(m.price).gt(0)) add(m.price_currency ?? ccy, dec(m.price).mul(dec(m.grams)))
      else add(m.cost_currency ?? ccy, dec(m.cost_basis))
    }
  }

  const total = Object.values(totals).reduce((s, v) => s.plus(v), new Decimal(0))
  if (total.lte(0)) return []
  return Object.entries(totals)
    .filter(([, v]) => v.gt(0))
    .map(([name, v]) => ({ name, value: parseFloat(v.div(total).mul(100).toFixed(1)) }))
    .sort((a, b) => b.value - a.value)
}

function computeCapitalGainsSeries(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): PieSlice[] {
  type Entry = { name: string; map: keyof Pick<WalletListItem, 'capital_gains_broker_ytd' | 'capital_gains_deposit_ytd' | 'capital_gains_real_estate_ytd' | 'capital_gains_metal_ytd'> }
  const entries: Entry[] = [
    { name: 'Akcje',          map: 'capital_gains_broker_ytd' },
    { name: 'Gotówka',        map: 'capital_gains_deposit_ytd' },
    { name: 'Nieruchomości',  map: 'capital_gains_real_estate_ytd' },
    { name: 'Metale',         map: 'capital_gains_metal_ytd' },
  ]
  const slices: { name: string; value: Decimal }[] = entries.map(({ name, map }) => ({
    name,
    value: wallets.reduce((sum, w) =>
      Object.entries(w[map]).reduce(
        (s, [fromCcy, amount]) => s.plus(conv(dec(amount), fromCcy, ccy, rates)),
        sum,
      ), new Decimal(0)),
  }))
  const total = slices.reduce((s, t) => s.plus(t.value), new Decimal(0))
  if (total.lte(0)) return []
  return slices
    .filter((t) => t.value.gt(0))
    .map((t) => ({ name: t.name, value: parseFloat(t.value.div(total).mul(100).toFixed(1)) }))
    .sort((a, b) => b.value - a.value)
}

export function computeGoalsProgress(
  allGoals: YearGoalOut[],
  selectedWallets: WalletListItem[],
  currentYear: number,
  ccy: Currency,
  rates: NullableFxRates,
): GoalsProgressData | null {
  const selectedIds = new Set(selectedWallets.map((w) => w.id))
  const currentGoals = allGoals.filter((g) => g.year === currentYear && selectedIds.has(g.wallet_id))
  if (currentGoals.length === 0) return null

  const monthFraction = (new Date().getMonth() + 1) / 12

  let revTarget = new Decimal(0)
  let expBudget = new Decimal(0)
  let capTarget = new Decimal(0)
  for (const goal of currentGoals) {
    revTarget = revTarget.plus(conv(dec(goal.rev_target_year), goal.currency, ccy, rates))
    expBudget = expBudget.plus(conv(dec(goal.exp_budget_year), goal.currency, ccy, rates))
    capTarget = capTarget.plus(conv(dec(goal.capital_gain_target_year ?? '0'), goal.currency, ccy, rates))
  }

  let revActual = new Decimal(0)
  let expActual = new Decimal(0)
  for (const w of selectedWallets) {
    for (const [cur, amount] of Object.entries(w.income_ytd_by_currency))
      revActual = revActual.plus(conv(dec(amount), cur, ccy, rates))
    for (const [cur, amount] of Object.entries(w.expense_ytd_by_currency))
      expActual = expActual.plus(conv(dec(amount), cur, ccy, rates))
  }

  return {
    revActual: revActual.toNumber(),
    revTarget: revTarget.mul(monthFraction).toNumber(),
    expActual: expActual.abs().toNumber(),
    expBudget: expBudget.mul(monthFraction).toNumber(),
    capActual: computeCapitalGains(selectedWallets, ccy, rates).toNumber(),
    capTarget: capTarget.mul(monthFraction).toNumber(),
    currency: ccy,
  }
}

export function buildPerfRowsFromHoldings(rows: HoldingRawRow[], ccy: Currency, sort: 'asc' | 'desc'): PerfRow[] {
  const matching = rows.filter((position) => {
    if (position.quoteMissing || position.pnlView === null) return false
    return sort === 'desc' ? position.pnlPct > 0 : position.pnlPct < 0
  })
  const sorted = matching.sort((a, b) => {
    const da = a.pnlPct, db = b.pnlPct
    return sort === 'desc' ? db - da : da - db
  }).slice(0, 5)

  return sorted.map((p, i) => {
    const pct = p.pnlPct * 100
    const plAbs = dec(p.pnlView)
    const sign = plAbs.gt(0) ? '+' : plAbs.lt(0) ? '-' : ''
    return {
      rank: i + 1,
      sym: p.symbol,
      pl_pct: pct,
      pl_pct_fmt: `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`,
      pl_abs_fmt: `${sign}${fmtKpi(plAbs.abs(), ccy)}`,
    }
  })
}

function buildDepositTxRows(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates, n = 5): DepositTxRow[] {
  const rows: DepositTxRow[] = []
  for (const w of wallets) {
    for (const a of w.accounts) {
      for (const tx of a.last_transactions ?? []) {
        const amt = conv(dec(tx.amount), a.currency, ccy, rates)
        rows.push({
          id: tx.id,
          date: tx.date_transaction.slice(0, 10),
          description: tx.description.slice(0, 28),
          accountName: a.name,
          amount: amt.toNumber(),
          currency: ccy,
        })
      }
    }
  }
  rows.sort((a, b) => b.date.localeCompare(a.date))
  return rows.slice(0, n)
}

function buildBrokerageTxRows(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates, n = 5): BrokerageTxRow[] {
  const rows: BrokerageTxRow[] = []
  let idx = 0
  for (const w of wallets) {
    for (const ev of w.last_brokerage_events ?? []) {
      const rawVal = ev.value != null ? dec(ev.value) : dec(ev.qty).mul(dec(ev.price))
      const valView = conv(rawVal, ev.ccy, ccy, rates)
      const dateStr = ev.date.slice(0, 10)
      rows.push({
        key: `${ev.sym}-${dateStr}-${idx++}`,
        date: dateStr,
        sym: ev.sym,
        type: ev.type,
        qty: dec(ev.qty).toFixed(4).replace(/\.?0+$/, ''),
        valueFmt: valView.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0'),
        ccy,
      })
    }
  }
  rows.sort((a, b) => b.date.localeCompare(a.date))
  return rows.slice(0, n)
}

function buildRecurringRows(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates, n = 5): RecurringExpenseRow[] {
  const rows: RecurringExpenseRow[] = []
  for (const w of wallets) {
    for (const e of w.recurring_expenses_top ?? []) {
      const amtView = conv(dec(e.amount), e.currency, ccy, rates)
      rows.push({
        id: e.id,
        name: e.name,
        category: e.category,
        amountFmt: fmtKpi(amtView, ccy),
        due_day: e.due_day,
      })
    }
  }
  rows.sort((a, b) => a.due_day - b.due_day)
  return rows.slice(0, n)
}

function computeRecurringTotal(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): string {
  const total = wallets.reduce((sum, w) =>
    (w.recurring_expenses_top ?? []).reduce((s, e) =>
      s.plus(conv(dec(e.amount), e.currency, ccy, rates)),
    sum),
  new Decimal(0))
  return fmtKpi(total, ccy)
}

export function computeAssetsChartData(
  assets8m: { months: string[]; values: (number | null)[] } | null,
  cpi8m: { index_by_month: Record<string, number> } | null,
  currency: string,
): AssetsChartData {
  const empty: AssetsChartData = { months: [], nominal: [], real: [], inflacja: [], mom: [], currency }
  if (!assets8m || assets8m.months.length === 0) return empty

  const months = assets8m.months
  const nominal = assets8m.values

  const mom: (number | null)[] = nominal.map((y, i) => {
    if (i === 0) return 0
    const prev = nominal[i - 1] ?? null
    if (y === null || y === undefined) return null
    if (prev === null || prev === undefined) return y
    return y - prev
  })

  if (!cpi8m || Object.keys(cpi8m.index_by_month).length === 0) {
    return { months, nominal, real: [], inflacja: [], mom, currency }
  }

  const rawCpi = months.map((m) => cpi8m.index_by_month[m] ?? null)

  const cpiVals = rawCpi.filter((v): v is number => v !== null)
  const isYoyRate = cpiVals.length > 0 && Math.max(...cpiVals.map(Math.abs)) < 50

  let inflacja: (number | null)[]
  let cpiIndexList: (number | null)[]

  if (isYoyRate) {
    inflacja = rawCpi
    cpiIndexList = []
    let cur = 100.0
    for (let i = 0; i < months.length; i++) {
      if (i === 0) { cpiIndexList.push(cur); continue }
      const p = rawCpi[i] ?? null
      if (p === null || p === 0) {
        cpiIndexList.push(cpiIndexList[cpiIndexList.length - 1] ?? null)
        continue
      }
      cur *= Math.pow(1 + p / 100, 1 / 12)
      cpiIndexList.push(cur)
    }
  } else {
    cpiIndexList = rawCpi
    const baseCpiIdx = cpiIndexList.find((v) => v !== null && v !== 0) ?? null
    inflacja = baseCpiIdx !== null
      ? cpiIndexList.map((v) => (v === null || v === 0 ? null : ((v / baseCpiIdx) - 1) * 100))
      : rawCpi.map(() => null)
  }

  const baseCpi = isYoyRate ? 100.0 : (cpiIndexList.find((v) => v !== null && v !== 0) ?? null)

  const real = nominal.map((y, i) => {
    if (y === null || y === undefined) return null
    const idx = cpiIndexList[i] ?? null
    if (idx === null || idx === 0 || baseCpi === null) return null
    return y / (idx / baseCpi)
  })

  return { months, nominal, real, inflacja, mom, currency }
}

export function computeDashFlowData(wallets: WalletListItem[], ccy: Currency, rates: NullableFxRates): DashFlowData {
  // Derive month labels from the first wallet that has dash_flow_8m data
  let months: string[] = []
  for (const w of wallets) {
    if (w.dash_flow_8m?.length) {
      months = w.dash_flow_8m.map((x) => x.month)
      break
    }
  }

  if (months.length === 0) {
    const now = new Date()
    for (let i = 7; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
    }
  }

  const inc: number[] = []
  const exp: number[] = []
  const tax: number[] = []
  const cap: number[] = []

  for (const ms of months) {
    let incomeView = new Decimal(0)
    let expenseView = new Decimal(0)
    let taxView = new Decimal(0)
    let capView = new Decimal(0)

    for (const w of wallets) {
      const it = (w.dash_flow_8m ?? []).find((x) => x.month === ms)
      if (!it) continue
      for (const [c, a] of Object.entries(it.income_by_currency))
        incomeView = incomeView.plus(conv(dec(a), c, ccy, rates))
      for (const [c, a] of Object.entries(it.expense_by_currency))
        expenseView = expenseView.plus(conv(dec(a), c, ccy, rates))
      for (const [c, a] of Object.entries(it.tax_by_currency ?? {}))
        taxView = taxView.plus(conv(dec(a), c, ccy, rates))
      for (const [c, a] of Object.entries(it.capital_by_currency))
        capView = capView.plus(conv(dec(a), c, ccy, rates))
    }

    inc.push(incomeView.toNumber())
    exp.push(expenseView.toNumber())
    tax.push(taxView.toNumber())
    cap.push(capView.toNumber())
  }

  return { months, inc, exp, tax, cap, currency: ccy }
}

export default async function WalletPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const headerStore = await headers()
  const username = headerStore.get('x-user') ?? ''
  const first_name = headerStore.get('x-first-name') ?? ''
  const email = headerStore.get('x-email') ?? ''
  const existingUserId = headerStore.get('x-user-id') ?? ''

  const [data, params, rates, stockStatus] = await Promise.all([
    syncUser({ username, first_name, email }),
    searchParams,
    getFxRates(),
    getStockServiceStatus(),
  ])

  const currentYear = new Date().getFullYear()

  logger.info({ existingUserId: existingUserId || '(empty)', username }, 'WalletPage: x-user-id header')

  if (data && !existingUserId) {
    await saveWalletUserId(data.user_id)
  }

  if (!data) {
    return (
      <div className="p-8 text-white">
        <p className="text-red-400">Nie udało się pobrać danych portfela. Spróbuj ponownie.</p>
      </div>
    )
  }

  const { wallets, banks } = data

  const modal = typeof params['modal'] === 'string' ? params['modal'] : ''
  const walletFilter = typeof params['wallet'] === 'string' ? params['wallet'] : 'all'
  const viewCurrency: Currency =
    params['currency'] === 'USD' ? 'USD' : params['currency'] === 'EUR' ? 'EUR' : 'PLN'

  const walletList = wallets.map((w) => ({ id: w.id, name: w.name }))
  const walletNames = wallets.map((w) => w.name)

  const selected =
    walletFilter === 'all' || !walletNames.includes(walletFilter)
      ? wallets
      : wallets.filter((w) => w.name === walletFilter)

  const selectedBrokerageAccountIds = selected.flatMap((wallet) =>
    wallet.brokerage_accounts.map((account) => account.id)
  )
  const performanceHoldings = selectedBrokerageAccountIds.length > 0
    ? (await fetchHoldings({
        userId: data.user_id,
        brokerage_account_id: selectedBrokerageAccountIds,
        group_mode: 'SYMBOL',
        view_ccy: viewCurrency,
      })).rows
    : []

  if (wallets.length === 0) {
    return (
      <>
        <CreateWalletDialogWrapper open={modal === 'create'} />
        <div className="px-4">
          <NoWalletState username={first_name || username} />
        </div>
      </>
    )
  }

  const hasAccounts = wallets.some((w) => w.accounts.length > 0)
  if (!hasAccounts) {
    return (
      <>
        <DeleteWalletDialogWrapper open={modal === 'delete'} wallets={walletList} />
        <CreateAccountDialogWrapper open={modal === 'create-account'} wallets={walletList} banks={banks} />
        <div className="px-4">
          <NoAccountState username={first_name || username} />
        </div>
      </>
    )
  }

  const estatePriceMap = new Map<string, string>()
  {
    const seen = new Set<string>()
    const fetches: Promise<void>[] = []
    for (const w of selected) {
      for (const re of w.real_estates) {
        if (!re.area_m2 || !re.type) continue
        const key = estateKey(re, viewCurrency)
        if (seen.has(key)) continue
        seen.add(key)
        fetches.push(
          getLatestRealEstatePrice({
            type: re.type,
            country: re.country,
            city: re.city,
            currency: re.purchase_currency ?? viewCurrency,
          }).then(p => { if (p) estatePriceMap.set(key, p) })
        )
      }
    }
    await Promise.all(fetches)
  }

  const [allGoals, allRecurringExpenses]: [YearGoalOut[], RecurringExpenseOut[]] = await Promise.all([
    Promise.all(wallets.map((w) => listWalletGoals(data.user_id, w.id)))
      .then((results) => results.flatMap((r) => (r.ok ? r.data : []))),
    Promise.all(wallets.map((w) => listRecurringExpenses(data.user_id, w.id)))
      .then((results) => results.flatMap((r) => (r.ok ? r.data : []))),
  ])

  const allocationSeries = computeAllocationSeries(selected, viewCurrency, rates, estatePriceMap)
  const capitalGainsSeries = computeCapitalGainsSeries(selected, viewCurrency, rates)
  const goalsProgress = computeGoalsProgress(allGoals, selected, currentYear, viewCurrency, rates)

  const depositTxRows = buildDepositTxRows(selected, viewCurrency, rates)
  const brokerageTxRows = buildBrokerageTxRows(selected, viewCurrency, rates)
  const recurringRows = buildRecurringRows(selected, viewCurrency, rates)
  const recurringTotal = computeRecurringTotal(selected, viewCurrency, rates)

  const assetsChartData = computeAssetsChartData(data.assets_8m_total ?? null, data.cpi_8m ?? null, 'PLN')
  const dashFlowData = computeDashFlowData(selected, viewCurrency, rates)
  const hasBrokerageExposure = selected.some((wallet) => wallet.brokerage_accounts.length > 0)
  const showMarketDataNotice = hasBrokerageExposure && !stockStatus.available

  const cash = computeCash(selected, viewCurrency, rates)
  const brokerage = computeBrokerage(selected, viewCurrency, rates)
  const estates = computeEstates(selected, viewCurrency, rates, estatePriceMap)
  const metals = computeMetals(selected, viewCurrency, rates)
  const investments = brokerage.plus(estates).plus(metals)
  const debts = computeDebts(selected, viewCurrency, rates)
  const netWorth = cash.plus(investments).minus(debts)
  const expenses = computeExpensesYtd(selected, viewCurrency, rates)
  const capitalGains = computeCapitalGains(selected, viewCurrency, rates)

  const totalAccounts = selected.reduce((n, w) => n + w.accounts.length, 0)
  const hasDebts = selected.some((w) => w.debts.length > 0)
  const hasInvestments = investments.gt(0)
  const debtCount = selected.flatMap((w) => w.debts).length
  const debtAvgRate = debtCount > 0
    ? selected.flatMap((w) => w.debts).reduce((sum, debt) => sum.plus(dec(debt.interest_rate_pct)), new Decimal(0)).div(debtCount)
    : new Decimal(0)
  const debtMonthlyTotal = selected.reduce((sum, wallet) =>
    wallet.debts.reduce((inner, debt) =>
      inner.plus(conv(dec(debt.monthly_payment), debt.currency, viewCurrency, rates)),
    sum),
  new Decimal(0))

  const invEstates: RealEstateRow[] = selected.flatMap(w =>
    w.real_estates.map(re => ({
      id: re.id,
      walletId: re.wallet_id,
      name: re.name,
      area_m2: re.area_m2 ?? null,
      valueFmt: fmtKpi(conv(estateValue(re, viewCurrency, estatePriceMap), re.purchase_currency ?? viewCurrency, viewCurrency, rates), viewCurrency),
      purchaseCurrency: re.purchase_currency ?? viewCurrency,
    }))
  )

  const invMetals: MetalRow[] = selected.flatMap(w =>
    w.metal_holdings.map(m => {
      const metalVal = m.price && dec(m.price).gt(0)
        ? conv(dec(m.price).mul(dec(m.grams)), m.price_currency ?? viewCurrency, viewCurrency, rates)
        : conv(dec(m.cost_basis), m.cost_currency ?? viewCurrency, viewCurrency, rates)
      return {
        id: m.id,
        walletId: m.wallet_id,
        metal: m.metal,
        grams: m.grams,
        valueFmt: fmtKpi(metalVal, viewCurrency),
      }
    })
  )

  const invWallets: WalletOpt[] = selected.map(w => ({
    id: w.id,
    name: w.name,
    accounts: w.accounts
      .filter(a => a.account_type === 'CURRENT')
      .map(a => ({ id: a.id, name: a.name })),
  }))

  const debtRows: DebtRow[] = selected.flatMap((wallet) =>
    wallet.debts.map((debt) => ({
      id: debt.id,
      walletId: wallet.id,
      walletName: wallet.name,
      name: debt.name,
      lander: debt.lander,
      amount: debt.amount,
      currency: debt.currency,
      interestRatePct: debt.interest_rate_pct,
      monthlyPayment: debt.monthly_payment,
      endDate: debt.end_date,
      amountFmt: fmtKpi(conv(dec(debt.amount), debt.currency, viewCurrency, rates), viewCurrency),
      monthlyFmt: fmtKpi(conv(dec(debt.monthly_payment), debt.currency, viewCurrency, rates), viewCurrency),
    })),
  )

  const debtWallets: DebtWalletOpt[] = selected.map((wallet) => ({
    id: wallet.id,
    name: wallet.name,
  }))

  const transactionAccounts: TransactionAccountOpt[] = wallets.flatMap((wallet) =>
    wallet.accounts.map((account) => {
      const latestTransaction = account.last_transactions?.[0] ?? null
      return {
        id: account.id,
        name: account.name,
        walletName: wallet.name,
        currency: account.currency,
        available: account.available,
        lastTransactionAt: latestTransaction?.date_transaction ?? null,
        lastBalanceAfter: latestTransaction?.balance_after ?? account.available,
      }
    }),
  )

  const transactionBrokerageAccounts: TransactionBrokerageAccountOpt[] = wallets.flatMap((wallet) =>
    wallet.brokerage_accounts.map((account) => ({
      id: account.id,
      name: account.name,
      walletName: wallet.name,
    })),
  )

  const recurringWallets: ExpenseWalletOpt[] = wallets.map((wallet) => ({
    id: wallet.id,
    name: wallet.name,
    accounts: wallet.accounts
      .filter((account) => account.account_type !== 'BROKERAGE')
      .map((account) => ({
        id: account.id,
        name: account.name,
        currency: account.currency,
        accountType: account.account_type,
      })),
  }))

  return (
    <div className="px-4 py-4">
      <CreateWalletDialogWrapper open={modal === 'create'} />
      <DeleteWalletDialogWrapper open={modal === 'delete'} wallets={walletList} />
      <CreateAccountDialogWrapper open={modal === 'create-account'} wallets={walletList} banks={banks} />
      <TransactionsDialogWrapper
        open={modal === 'transaction'}
        accounts={transactionAccounts}
        brokerageAccounts={transactionBrokerageAccounts}
      />
      <NotesDialogWrapper open={modal === 'notes'} />
      <InvestmentsDialogWrapper
        open={modal === 'investments'}
        totalFmt={fmtKpi(investments, viewCurrency)}
        brokerageFmt={fmtKpi(brokerage, viewCurrency)}
        estatesFmt={fmtKpi(estates, viewCurrency)}
        metalsFmt={fmtKpi(metals, viewCurrency)}
        realEstates={invEstates}
        metals={invMetals}
        wallets={invWallets}
        viewCurrency={viewCurrency}
      />
      <DebtsDialogWrapper
        open={modal === 'debts'}
        totalFmt={hasDebts ? `−${fmtKpi(debts, viewCurrency)}` : `0 ${viewCurrency}`}
        subtitle={debtSubtitle(selected)}
        countFmt={String(debtCount)}
        avgRateFmt={`${debtAvgRate.toFixed(1)}%`}
        monthlyFmt={fmtKpi(debtMonthlyTotal, viewCurrency)}
        debts={debtRows}
        wallets={debtWallets}
        viewCurrency={viewCurrency}
      />
      <GoalsDialogWrapper
        open={modal === 'goals'}
        initialGoals={allGoals}
        wallets={wallets.map((w) => ({ id: w.id, name: w.name }))}
        viewCurrency={viewCurrency}
      />
      <RecurringExpensesDialogWrapper
        open={modal === 'recurring'}
        initialExpenses={allRecurringExpenses}
        wallets={recurringWallets}
        viewCurrency={viewCurrency}
      />

      <div className="max-w-screen-2xl mx-auto">

        <WalletToolbar walletNames={walletNames} currencies={['PLN', 'USD', 'EUR']} />

        {showMarketDataNotice && (
          <MarketDataNotice scope="dashboard" />
        )}

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">

          <KpiCard
            title="Wartość netto"
            value={fmtKpi(netWorth, viewCurrency)}
          />

          <KpiCard
            title="Gotówka"
            value={fmtKpi(cash, viewCurrency)}
            sub={`${totalAccounts} kont`}
          />

          <KpiCard
            title="Inwestycje"
            value={hasInvestments ? fmtKpi(investments, viewCurrency) : '—'}
            sub={hasInvestments ? undefined : 'brak pozycji'}
            href="?modal=investments"
          />

          <KpiCard
            title="Zobowiązania"
            value={hasDebts ? `−${fmtKpi(debts, viewCurrency)}` : '—'}
            sub={debtSubtitle(selected)}
            href="?modal=debts"
          />

          <KpiCard
            title="Wydatki (YTD)"
            value={expenses.gt(0) ? fmtKpi(expenses, viewCurrency) : '—'}
            sub={expenses.gt(0) ? undefined : 'brak danych'}
          />

          <KpiCard
            title="Zyski kap. (YTD)"
            value={capitalGains.gt(0) ? fmtKpi(capitalGains, viewCurrency) : '—'}
            sub={capitalGains.gt(0) ? undefined : 'brak danych'}
          />
        </div>

        {(() => {
          const gainers = buildPerfRowsFromHoldings(performanceHoldings, viewCurrency, 'desc')
          const losers  = buildPerfRowsFromHoldings(performanceHoldings, viewCurrency, 'asc')
          return (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mt-3">
              <StockPerfCard
                title="Największe zyski"
                rows={gainers}
                currency={viewCurrency}
              />
              <StockPerfCard
                title="Największe straty"
                rows={losers}
                currency={viewCurrency}
              />
              <ObservedStocksCard
                items={data.last_favorite_items}
                viewCurrency={viewCurrency}
                href="/user/favorites"
              />
              <PriceAlertsCard
                alerts={data.last_price_alerts}
                viewCurrency={viewCurrency}
                href="/user/favorites"
              />
            </div>
          )
        })()}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
          <PieChartCard title="Alokacja portfela" series={allocationSeries} />
          <PieChartCard title="Zyski kapitałowe" series={capitalGainsSeries} />
          <GoalsCard data={goalsProgress} href="?modal=goals" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
          <DepositTransactionsCard rows={depositTxRows} />
          <BrokerageTransactionsCard rows={brokerageTxRows} />
          <RecurringExpensesCard rows={recurringRows} totalFmt={recurringTotal} href="?modal=recurring" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          <AssetsLineCard data={assetsChartData} />
          <DashFlowCard data={dashFlowData} />
        </div>

      </div>
    </div>
  )
}
