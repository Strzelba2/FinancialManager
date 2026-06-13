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
  note: string | null
}

export type EventsPageResult = {
  rows: EventRow[]
  total: number
  page: number
  pageNotional: number  
  allNotional: number  
  viewCcy: string
  fxRates: FxRates | null
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

function convertWithRates(amount: number, from: string, to: string, rates: FxRates | null): number {
  if (from === to || !rates) return amount
  return convertCurrency(amount, from, to, rates)
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

  if (!pageResult.ok) {
    return {
      rows: [],
      total: 0,
      page: params.page ?? 1,
      pageNotional: 0,
      allNotional: 0,
      viewCcy,
      fxRates,
    }
  }

  const pd = pageResult.data

  const rows: EventRow[] = pd.items.map((r) => {
    const qty = Number(r.quantity)
    const priceNative = Number(r.price)
    const ccy = r.currency
    const priceView = convertWithRates(priceNative, ccy, viewCcy, fxRates)
    const notionalView = convertWithRates(qty * priceNative, ccy, viewCcy, fxRates)
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
      note: r.note ?? null,
    }
  })

  const pageNotional = rows.reduce((s, r) => s + r.notionalView, 0)
  const allNotional = Object.entries(pd.sum_by_ccy).reduce((s, [ccy, amt]) => {
    return s + convertWithRates(Number(amt), ccy, viewCcy, fxRates)
  }, 0)

  return {
    rows,
    total: pd.total,
    page: pd.page,
    pageNotional,
    allNotional,
    viewCcy,
    fxRates,
  }
}
