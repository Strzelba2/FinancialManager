import Link from 'next/link'
import type { FavoriteItem } from '@/lib/types/wallet'

export type PerfRow = {
  rank: number
  sym: string
  pl_pct: number       // raw float, e.g. 4.23
  pl_pct_fmt: string   // "+4.23%"
  pl_abs_fmt: string   // "+1 234 PLN"
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-6 gap-1.5">
      <div className="w-7 h-7 rounded-full bg-white/5 flex items-center justify-center">
        <svg className="w-3.5 h-3.5 text-white/20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 7h18M3 12h18M3 17h18" />
        </svg>
      </div>
      <p className="text-xs text-white/25">Brak danych</p>
    </div>
  )
}

type PerfCardProps = {
  title: string
  rows: PerfRow[]
  currency: string
}

export function StockPerfCard({ title, rows, currency }: PerfCardProps) {
  return (
    <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full">
      <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
        <p className="text-xs font-medium text-white/50 uppercase tracking-wide">{title}</p>
      </div>

      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/5">
              <th className="px-4 py-2 text-left font-semibold text-white/30 w-8">#</th>
              <th className="px-2 py-2 text-left font-semibold text-white/30">Ticker</th>
              <th className="px-2 py-2 text-right font-semibold text-white/30">P/L %</th>
              <th className="px-4 py-2 text-right font-semibold text-white/30">P/L ({currency})</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const up = r.pl_pct >= 0
              return (
                <tr key={r.sym} className="border-b border-white/5 last:border-0 hover:bg-white/[0.03] transition-colors">
                  <td className="px-4 py-2.5 text-white/30">{r.rank}</td>
                  <td className="px-2 py-2.5 font-medium text-white">{r.sym}</td>
                  <td className={`px-2 py-2.5 text-right tabular-nums font-medium ${up ? 'text-emerald-400' : 'text-red-400'}`}>
                    {r.pl_pct_fmt}
                  </td>
                  <td className={`px-4 py-2.5 text-right tabular-nums ${up ? 'text-emerald-400/70' : 'text-red-400/70'}`}>
                    {r.pl_abs_fmt}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

type ObservedCardProps = {
  items: FavoriteItem[]
  viewCurrency: string
  href: string
}

function fmtObservedPct(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '-' : ''
  const formatted = Math.abs(value).toLocaleString('pl-PL', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return `${sign}${formatted}%`
}

export function ObservedStocksCard({ items, viewCurrency, href }: ObservedCardProps) {
  const rows = items.slice(0, 5)

  return (
    <Link href={href} className="block group h-full">
      <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full group-hover:bg-slate-800/60 transition-colors cursor-pointer">
        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between flex-shrink-0">
          <p className="text-xs font-medium text-white/50 uppercase tracking-wide">Obserwowane</p>
          <svg className="w-3 h-3 text-white/20 group-hover:text-white/40 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>

        {rows.length === 0 ? (
          <EmptyState />
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/5">
                <th className="px-4 py-2 text-left font-semibold text-white/30 w-8">#</th>
                <th className="px-2 py-2 text-left font-semibold text-white/30">Symbol</th>
                <th className="px-2 py-2 text-right font-semibold text-white/30">Zmiana %</th>
                <th className="px-4 py-2 text-right font-semibold text-white/30">Cena ({viewCurrency})</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item, i) => {
                const pct = Number(item.pl_pct)
                const price = Number(item.pl_abs)
                const up  = pct >= 0
                const pctFmt = fmtObservedPct(pct)
                const priceFmt = `${Math.abs(price).toFixed(2)} ${viewCurrency}`
                return (
                  <tr key={item.sym} className="border-b border-white/5 last:border-0 hover:bg-white/[0.03] transition-colors">
                    <td className="px-4 py-2.5 text-white/30">{i + 1}</td>
                    <td className="px-2 py-2.5 font-medium text-white">{item.sym}</td>
                    <td className={`px-2 py-2.5 text-right tabular-nums font-medium ${up ? 'text-emerald-400' : 'text-red-400'}`}>
                      {pctFmt}
                    </td>
                    <td className={`px-4 py-2.5 text-right tabular-nums ${up ? 'text-emerald-400/70' : 'text-red-400/70'}`}>
                      {priceFmt}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </Link>
  )
}
