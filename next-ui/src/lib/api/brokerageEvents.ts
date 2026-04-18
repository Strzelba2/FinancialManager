import { listBrokerageEvents } from '@/lib/api/wallet'
import { getFxRates, convertCurrency } from '@/lib/api/nbp'
import type { FxRates } from '@/lib/api/nbp'

export type { FxRates }

export type EventRow = {
  id: string
  tradeAt: string
  accountId: string
  accountName: string
  symbol: string
  instrumentName: string
  kind: string
  quantity: number
  priceNative: number   
  priceView: number     
  currency: string      
  notionalView: number
  notionalFmt: string
  splitRatio: number
}

export type EventsPageResult = {
  rows: EventRow[]
  total: number
  page: number
  pageNotional: number  
  allNotional: number  
  viewCcy: string
  fxRates: FxRates
}

export type EventsParams = {
  userId: string
  page?: number
  size?: number
  brokerage_account_id?: string[]
  kind?: string[]
  currency?: string[]
  date_from?: string
  date_to?: string
  q?: string
  view_ccy?: string
}

const FALLBACK_FX: FxRates = {
  'USD/PLN': 4,
  'EUR/PLN': 4.2,
  'PLN/USD': 0.25,
  'PLN/EUR': 0.238,
  'USD/EUR': 0.95,
  'EUR/USD': 1.05,
}

function fmtMoney(v: number, ccy: string): string {
  return v.toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '\u00a0' + ccy
}

function fmtTradeAt(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('pl-PL', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso.slice(0, 16).replace('T', ' ')
  }
}

export async function fetchEventsPage(params: EventsParams): Promise<EventsPageResult> {
  const viewCcy = params.view_ccy ?? 'PLN'

  const [pageResult, fxRates] = await Promise.all([
    listBrokerageEvents(params.userId, {
      page: params.page ?? 1,
      size: params.size ?? 40,
      brokerage_account_id: params.brokerage_account_id?.length ? params.brokerage_account_id : undefined,
      kind: params.kind?.length ? params.kind : undefined,
      currency: params.currency?.length ? params.currency : undefined,
      date_from: params.date_from,
      date_to: params.date_to,
      q: params.q,
    }),
    getFxRates(),
  ])

  const fx = fxRates ?? FALLBACK_FX

  if (!pageResult.ok) {
    return {
      rows: [],
      total: 0,
      page: params.page ?? 1,
      pageNotional: 0,
      allNotional: 0,
      viewCcy,
      fxRates: fx,
    }
  }

  const pd = pageResult.data

  const rows: EventRow[] = pd.items.map((r) => {
    const qty = Number(r.quantity)
    const priceNative = Number(r.price)
    const ccy = r.currency
    const priceView = convertCurrency(priceNative, ccy, viewCcy, fx)
    const notionalView = convertCurrency(qty * priceNative, ccy, viewCcy, fx)
    return {
      id: r.id,
      tradeAt: fmtTradeAt(r.trade_at),
      accountId: r.brokerage_account_id,
      accountName: r.brokerage_account_name,
      symbol: r.instrument_symbol,
      instrumentName: r.instrument_name ?? '',
      kind: r.kind,
      quantity: qty,
      priceNative,
      priceView,
      currency: ccy,
      notionalView,
      notionalFmt: fmtMoney(notionalView, viewCcy),
      splitRatio: Number(r.split_ratio),
    }
  })

  const pageNotional = rows.reduce((s, r) => s + r.notionalView, 0)
  const allNotional = Object.entries(pd.sum_by_ccy).reduce((s, [ccy, amt]) => {
    return s + convertCurrency(Number(amt), ccy, viewCcy, fx)
  }, 0)

  return {
    rows,
    total: pd.total,
    page: pd.page,
    pageNotional,
    allNotional,
    viewCcy,
    fxRates: fx,
  }
}
