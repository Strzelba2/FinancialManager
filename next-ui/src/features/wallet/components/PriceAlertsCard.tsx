import Link from 'next/link'
import type { PriceAlert } from '@/lib/types/wallet'

function fmtPrice(val: string | null, ccy: string): string {
  if (val == null) return '—'
  const n = Number(val)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(2)} ${ccy}`.trim()
}

function fmtLevel(val: string | null): string {
  if (val == null) return '—'
  const n = Number(val)
  return Number.isFinite(n) ? n.toFixed(2) : '—'
}

function isFired(a: PriceAlert): boolean {
  const cur = Number(a.current_price)
  if (!Number.isFinite(cur)) return false
  if (a.below_price != null && cur <= Number(a.below_price)) return true
  if (a.above_price != null && cur >= Number(a.above_price)) return true
  return false
}

type Props = {
  alerts: PriceAlert[]
  viewCurrency: string
  href: string
}

export function PriceAlertsCard({ alerts, viewCurrency, href }: Props) {
  const rows = [...alerts]
    .filter((a) => a.enabled)
    .sort((a, b) => {
      const aFired = isFired(a) ? 0 : 1
      const bFired = isFired(b) ? 0 : 1
      return aFired - bFired || a.sym.localeCompare(b.sym)
    })
    .slice(0, 5)

  return (
    <Link href={href} className="block group h-full">
      <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full group-hover:bg-slate-800/60 transition-colors cursor-pointer">
        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between flex-shrink-0">
          <p className="text-xs font-medium text-white/50 uppercase tracking-wide">Price Alerts</p>
          <svg className="w-3 h-3 text-white/20 group-hover:text-white/40 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>

        {rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-6 gap-1.5">
            <svg className="w-5 h-5 text-white/15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            <p className="text-xs text-white/25">Brak alertów</p>
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/5">
                <th className="px-4 py-2 text-left font-semibold text-white/30 w-8">#</th>
                <th className="px-2 py-2 text-left font-semibold text-white/30">Symbol</th>
                <th className="px-2 py-2 text-right font-semibold text-white/30">Below</th>
                <th className="px-2 py-2 text-right font-semibold text-white/30">Above</th>
                <th className="px-4 py-2 text-right font-semibold text-white/30">Now ({viewCurrency})</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a, i) => {
                const fired = isFired(a)
                return (
                  <tr key={a.sym} className="border-b border-white/5 last:border-0 hover:bg-white/[0.03] transition-colors">
                    <td className="px-4 py-2.5 text-white/30">{i + 1}</td>
                    <td className="px-2 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={{ backgroundColor: fired ? '#ef4444' : '#22c55e' }}
                        />
                        <span className="font-medium text-white">{a.sym}</span>
                      </div>
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-blue-400/80">{fmtLevel(a.below_price)}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-blue-400/80">{fmtLevel(a.above_price)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-white/70">
                      {fmtPrice(a.current_price, viewCurrency)}
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
