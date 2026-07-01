import { listHoldings, listBrokerageAccounts } from '@/lib/api/wallet'
import { getQuotesBySymbols } from '@/lib/api/stock'
import { getFxRates } from '@/lib/api/nbp'
import type { FxRates } from '@/lib/api/nbp'

function toNum(v: string | number | null | undefined): number {
  if (v === null || v === undefined) return 0
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  return isNaN(n) ? 0 : n
}

function conv(amount: number, from: string, to: string, rates: FxRates | null): number {
  if (from === to || !rates || !from || from === '—') return amount
  const key = `${from}/${to}` as keyof FxRates
  if (rates[key]) return amount * rates[key]
  const inv = `${to}/${from}` as keyof FxRates
  if (rates[inv]) return amount / rates[inv]
  return amount
}

export type HoldingAccountBreakdown = {
  accountId: string
  accountName: string
  quantity: number
  costRaw: number
}

export type HoldingRawRow = {
  id: string
  accountId: string
  symbol: string
  instrumentMic: string
  name: string
  currency: string          
  accountsDisp: string      
  accountBreakdown: HoldingAccountBreakdown[]
  quantity: number
  avgCostRaw: number        
  priceRaw: number         
  costRaw: number           
  valueRaw: number          
  pnlAmountRaw: number     
  pnlPct: number            
  costView: number | null   
  valueView: number | null  
  pnlView: number | null    
  changePct: number         
  quoteMissing: boolean
}

export type HoldingsResult = {
  rows: HoldingRawRow[]
  totalValueView: number
  totalCostView: number
  viewCcy: string
  fxRates: FxRates | null
  brokerageAccounts: { id: string; name: string }[]
}

export type HoldingsParams = {
  userId: string
  q?: string
  brokerage_account_id?: string[]
  group_mode?: 'SYMBOL' | 'ACCOUNT'
  view_ccy?: string
}

export async function fetchHoldings(params: HoldingsParams): Promise<HoldingsResult> {
  const viewCcy = params.view_ccy ?? 'PLN'
  const groupMode = params.group_mode ?? 'SYMBOL'

  const [holdings, brokerageAccounts, rates] = await Promise.all([
    listHoldings(params.userId, {
      q: params.q,
      brokerage_account_id: params.brokerage_account_id,
    }),
    listBrokerageAccounts(params.userId),
    getFxRates(),
  ])

  const agg = new Map<string, {
    key: string
    symbol: string
    name: string
    currency: string
    accounts: Map<string, HoldingAccountBreakdown>
    accountId: string
    instrumentMic: string
    totalQty: number
    totalCost: number   
  }>()

  for (const h of holdings) {
    const symbol = (h.instrument_symbol ?? '').trim()
    if (!symbol) continue

    const accountName = h.account_name ?? 'Account'
    const accountId = h.account_id
    const ccy = (h.instrument_currency ?? '').trim() || '—'
    const qty = toNum(h.quantity)
    const avgCost = toNum(h.avg_cost)
    const costRaw = qty * avgCost

    const key = groupMode === 'ACCOUNT' ? `${accountId}::${symbol}` : symbol

    const rec = agg.get(key)
    if (!rec) {
      agg.set(key, {
        key,
        symbol,
        name: h.instrument_name ?? '',
        currency: ccy,
        accounts: new Map([[accountId, {
          accountId,
          accountName,
          quantity: qty,
          costRaw,
        }]]),
        accountId,
        instrumentMic: h.instrument_mic ?? '',
        totalQty: qty,
        totalCost: costRaw,
      })
    } else {
      const account = rec.accounts.get(accountId)
      if (account) {
        account.quantity += qty
        account.costRaw += costRaw
      } else {
        rec.accounts.set(accountId, {
          accountId,
          accountName,
          quantity: qty,
          costRaw,
        })
      }
      rec.totalQty += qty
      rec.totalCost += costRaw
    }
  }

  const symbols = [...new Set([...agg.values()].map((r) => r.symbol))]
  const quotesMap = await getQuotesBySymbols(symbols)

  const rows: HoldingRawRow[] = []
  let totalValueView = 0
  let totalCostView = 0

  for (const rec of agg.values()) {
    const { symbol, name, accounts } = rec
    const qty = rec.totalQty
    const cost = rec.totalCost

    const quote = quotesMap[symbol]
    const quoteMissing = !quote
    const quoteCcy = quote?.currency ?? rec.currency
    const ccy = quoteCcy || rec.currency
    const priceRaw = quoteMissing ? 0 : toNum(quote?.price)
    const changePct = quoteMissing ? 0 : toNum(quote?.change_pct)

    const avgCostRaw = qty > 0 ? cost / qty : 0
    const valueRaw = quoteMissing ? 0 : qty * priceRaw
    const pnlAmountRaw = quoteMissing ? 0 : valueRaw - cost
    const pnlPct = !quoteMissing && cost > 0 ? pnlAmountRaw / cost : 0

    const costView = !quoteMissing && ccy && ccy !== '—' ? conv(cost, ccy, viewCcy, rates) : null
    const valueView = !quoteMissing && ccy && ccy !== '—' ? conv(valueRaw, ccy, viewCcy, rates) : null
    const pnlView = !quoteMissing && ccy && ccy !== '—' ? conv(pnlAmountRaw, ccy, viewCcy, rates) : null

    if (valueView !== null) totalValueView += valueView
    if (costView !== null) totalCostView += costView

    const accountBreakdown = [...accounts.values()].sort((a, b) =>
      a.accountName.localeCompare(b.accountName)
    )
    const accountsArr = accountBreakdown.map((account) => account.accountName)
    const accountsDisp = accountsArr.length === 1
      ? accountsArr[0]!
      : `${accountsArr.length} rachunki`

    rows.push({
      id: rec.key,
      accountId: rec.accountId,
      symbol,
      instrumentMic: rec.instrumentMic,
      name,
      currency: ccy,
      accountsDisp,
      accountBreakdown,
      quantity: qty,
      avgCostRaw,
      priceRaw,
      costRaw: cost,
      valueRaw,
      pnlAmountRaw,
      pnlPct,
      costView,
      valueView,
      pnlView,
      changePct,
      quoteMissing,
    })
  }

  rows.sort((a, b) => (b.valueView ?? b.valueRaw) - (a.valueView ?? a.valueRaw))

  return { rows, totalValueView, totalCostView, viewCcy, fxRates: rates, brokerageAccounts }
}
