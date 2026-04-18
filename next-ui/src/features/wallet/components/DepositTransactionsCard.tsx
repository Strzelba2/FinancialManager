export type DepositTxRow = {
  id: string
  date: string        // YYYY-MM-DD
  description: string // truncated to ~28 chars
  accountName: string
  amount: number      // signed; converted to view currency
  currency: string
}

type Props = {
  rows: DepositTxRow[]
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8 gap-1.5 flex-1 min-h-[200px]">
      <svg
        className="w-5 h-5 text-white/15"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
      </svg>
      <p className="text-xs text-white/25">Brak transakcji</p>
    </div>
  )
}

export function DepositTransactionsCard({ rows }: Props) {
  return (
    <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full">
      <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
        <p className="text-xs font-medium text-white/50 uppercase tracking-wide">
          Ostatnie transakcje — rachunki
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="flex-1 overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {rows.map((row, i) => {
                const positive = row.amount >= 0
                return (
                  <tr
                    key={row.id}
                    className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}
                  >
                    <td className="px-3 py-1.5 align-middle w-[82px] flex-shrink-0">
                      <span className="text-[10px] text-white/35 tabular-nums">{row.date}</span>
                    </td>
                    <td className="px-2 py-1.5 align-middle min-w-0">
                      <p className="text-xs text-white/75 truncate leading-tight">{row.description}</p>
                      <p className="text-[10px] text-white/30 truncate leading-tight">{row.accountName}</p>
                    </td>
                    <td className="px-3 py-1.5 align-middle text-right w-[100px] flex-shrink-0">
                      <span
                        className={`text-xs font-medium tabular-nums ${
                          positive ? 'text-emerald-400' : 'text-red-400'
                        }`}
                      >
                        {positive ? '+' : ''}
                        {row.amount.toLocaleString('pl-PL', {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}{' '}
                        <span className="text-white/35 font-normal">{row.currency}</span>
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
