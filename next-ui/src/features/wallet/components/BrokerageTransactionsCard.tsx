export type BrokerageTxRow = {
  key: string   // unique row key (sym+date+index)
  date: string  // YYYY-MM-DD
  sym: string
  type: string  // BUY | SELL | DIV | FEE | SPLIT …
  qty: string
  valueFmt: string  // formatted value in view ccy
  ccy: string
}

type Props = {
  rows: BrokerageTxRow[]
}

// ── type badge colours ────────────────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  BUY:   'bg-emerald-500/20 text-emerald-300',
  SELL:  'bg-red-500/20 text-red-300',
  DIV:   'bg-blue-500/20 text-blue-300',
  FEE:   'bg-orange-500/20 text-orange-300',
  SPLIT: 'bg-purple-500/20 text-purple-300',
}

function typeBadge(t: string) {
  return TYPE_COLORS[t.toUpperCase()] ?? 'bg-white/10 text-white/50'
}

// ── shared empty state ────────────────────────────────────────────────────────

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
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
      <p className="text-xs text-white/25">Brak transakcji maklerskich</p>
    </div>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export function BrokerageTransactionsCard({ rows }: Props) {
  return (
    <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden flex flex-col h-full">
      <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
        <p className="text-xs font-medium text-white/50 uppercase tracking-wide">
          Ostatnie transakcje — maklerskie
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="flex-1 overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={row.key}
                  className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}
                >
                  <td className="px-3 py-1.5 align-middle w-[78px] flex-shrink-0">
                    <span className="text-[10px] text-white/35 tabular-nums">{row.date}</span>
                  </td>
                  <td className="px-2 py-1.5 align-middle">
                    <p className="text-xs font-medium text-white/80 leading-tight">{row.sym}</p>
                    <p className="text-[10px] text-white/30 leading-tight tabular-nums">
                      {Number(row.qty) !== 0 ? `${row.qty} szt.` : ''}
                    </p>
                  </td>
                  <td className="px-2 py-1.5 align-middle">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${typeBadge(row.type)}`}
                    >
                      {row.type}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 align-middle text-right w-[100px] flex-shrink-0">
                    <span className="text-xs text-white/70 tabular-nums">
                      {row.valueFmt}{' '}
                      <span className="text-white/30">{row.ccy}</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
