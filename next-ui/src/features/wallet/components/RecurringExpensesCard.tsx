'use client'
import Link from 'next/link'

export type RecurringExpenseRow = {
  id: string
  name: string
  category: string | null
  amountFmt: string   // formatted in view ccy, e.g. "1 800 PLN"
  due_day: number
}

type Props = {
  rows: RecurringExpenseRow[]
  totalFmt: string    // total monthly sum in view ccy, e.g. "4 500 PLN"
  href: string        // e.g. "?modal=recurring"
}

function CardShell({
  href,
  children,
}: {
  href: string
  children: React.ReactNode
}) {
  return (
    <Link href={href} className="block group h-full">
      <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full group-hover:bg-slate-800/60 transition-colors cursor-pointer">
        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between flex-shrink-0">
          <p className="text-xs font-medium text-white/50 uppercase tracking-wide">
            Stałe miesięczne wydatki
          </p>
          <svg
            className="w-3 h-3 text-white/20 group-hover:text-white/40 transition-colors"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>
        {children}
      </div>
    </Link>
  )
}

export function RecurringExpensesCard({ rows, totalFmt, href }: Props) {
  if (rows.length === 0) {
    return (
      <CardShell href={href}>
        <div className="flex flex-col items-center justify-center py-8 gap-1.5 flex-1 min-h-[200px]">
          <svg
            className="w-5 h-5 text-white/15"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z" />
          </svg>
          <p className="text-xs text-white/25">Brak stałych wydatków</p>
          <p className="text-[10px] text-white/15">Kliknij aby dodać</p>
        </div>
      </CardShell>
    )
  }

  return (
    <CardShell href={href}>
      {/* Summary strip */}
      <div className="px-4 py-2 border-b border-white/5 flex items-center justify-between flex-shrink-0">
        <span className="text-[10px] text-white/30 uppercase tracking-wide">Suma / mies.</span>
        <span className="text-sm font-semibold text-white/90 tabular-nums">{totalFmt}</span>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5">
              <th className="px-3 py-1.5 text-left text-[10px] text-white/30 font-medium">Nazwa</th>
              <th className="px-2 py-1.5 text-left text-[10px] text-white/30 font-medium hidden sm:table-cell">Kategoria</th>
              <th className="px-2 py-1.5 text-center text-[10px] text-white/30 font-medium w-[40px]">Dzień</th>
              <th className="px-3 py-1.5 text-right text-[10px] text-white/30 font-medium">Kwota</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={row.id}
                className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}
              >
                <td className="px-3 py-1.5 align-middle min-w-0">
                  <p className="text-xs text-white/80 truncate leading-tight">{row.name}</p>
                </td>
                <td className="px-2 py-1.5 align-middle hidden sm:table-cell">
                  <p className="text-[10px] text-white/35 truncate leading-tight">{row.category ?? '—'}</p>
                </td>
                <td className="px-2 py-1.5 align-middle text-center">
                  <span className="text-[10px] text-white/40 tabular-nums">{row.due_day}</span>
                </td>
                <td className="px-3 py-1.5 align-middle text-right">
                  <span className="text-xs text-white/70 tabular-nums">{row.amountFmt}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CardShell>
  )
}
