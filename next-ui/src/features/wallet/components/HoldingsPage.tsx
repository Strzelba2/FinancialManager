'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { RefreshCw, Search, TrendingUp, TrendingDown, ChevronUp, ChevronDown as ChevronDownIcon, Minus } from 'lucide-react'
import type { HoldingRawRow, HoldingsResult } from '@/lib/api/holdings'
import type { FxRates } from '@/lib/api/nbp'

type ViewCcy = string  // PLN | USD | EUR

function fmtNum(v: number, decimals = 2): string {
  return v.toLocaleString('pl-PL', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function fmtMoney(v: number | null, ccy: string): string {
  if (v === null) return '—'
  return fmtNum(v) + '\u00a0' + ccy
}

function fmtPct(v: number, unit = true): string {
  const val = unit ? v * 100 : v
  return (val >= 0 ? '+' : '') + fmtNum(Math.abs(val)) + '%'
}

type SortField = 'symbol' | 'quantity' | 'value' | 'pnl_pct' | 'name'
type SortDir = 'asc' | 'desc'

function sortRows(rows: HoldingRawRow[], field: SortField, dir: SortDir): HoldingRawRow[] {
  return [...rows].sort((a, b) => {
    let av: number | string, bv: number | string
    switch (field) {
      case 'symbol': av = a.symbol; bv = b.symbol; break
      case 'name': av = a.name; bv = b.name; break
      case 'quantity': av = a.quantity; bv = b.quantity; break
      case 'value': av = a.valueView ?? a.valueRaw; bv = b.valueView ?? b.valueRaw; break
      case 'pnl_pct': av = a.pnlPct; bv = b.pnlPct; break
    }
    if (typeof av === 'string') {
      return dir === 'asc' ? av.localeCompare(bv as string) : (bv as string).localeCompare(av)
    }
    return dir === 'asc' ? (av - (bv as number)) : ((bv as number) - av)
  })
}

function PnlBadge({ pct, unit = true }: { pct: number; unit?: boolean }) {
  const val = unit ? pct * 100 : pct
  const positive = val >= 0
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded tabular-nums ${
      positive ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
    }`}>
      {positive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {fmtPct(pct, unit)}
    </span>
  )
}

function SortIcon({ field, current, dir }: { field: SortField; current: SortField; dir: SortDir }) {
  if (field !== current) return <Minus className="w-3 h-3 text-white/20" />
  return dir === 'asc'
    ? <ChevronUp className="w-3 h-3 text-blue-400" />
    : <ChevronDownIcon className="w-3 h-3 text-blue-400" />
}

function ThButton({ label, field, sort, dir, onSort }: {
  label: string; field: SortField; sort: SortField; dir: SortDir; onSort: (f: SortField) => void
}) {
  return (
    <button
      onClick={() => onSort(field)}
      className="flex items-center gap-1 text-xs text-white/40 uppercase tracking-wide hover:text-white/70 transition-colors"
    >
      {label}
      <SortIcon field={field} current={sort} dir={dir} />
    </button>
  )
}

type Props = {
  initialRows: HoldingRawRow[]
  initialTotalValue: number
  initialTotalCost: number
  initialViewCcy: string
  fxRates: FxRates | null
  brokerageAccounts: { id: string; name: string }[]
}

type GroupMode = 'SYMBOL' | 'ACCOUNT'

export function HoldingsPage({
  initialRows,
  initialTotalValue,
  initialTotalCost,
  initialViewCcy,
  brokerageAccounts,
}: Props) {
  const [rows, setRows] = useState<HoldingRawRow[]>(initialRows)
  const [totalValue, setTotalValue] = useState(initialTotalValue)
  const [totalCost, setTotalCost] = useState(initialTotalCost)

  const [viewCcy, setViewCcy] = useState<ViewCcy>(initialViewCcy)
  const [accountIds, setAccountIds] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [groupMode, setGroupMode] = useState<GroupMode>('SYMBOL')
  const [sortField, setSortField] = useState<SortField>('value')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchData = useCallback(async (
    ccy: ViewCcy, accs: string[], q: string, mode: GroupMode
  ) => {
    setLoading(true)
    setError(null)
    try {
      const qs = new URLSearchParams({ view_ccy: ccy, group_mode: mode })
      if (q) qs.set('q', q)
      accs.forEach((id) => qs.append('account_id', id))

      const res = await fetch(`/api/wallet/holdings?${qs}`)
      if (!res.ok) { setError('Błąd pobierania danych'); return }
      const data = await res.json() as HoldingsResult
      setRows(data.rows)
      setTotalValue(data.totalValueView)
      setTotalCost(data.totalCostView)
    } catch {
      setError('Błąd połączenia')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      fetchData(viewCcy, accountIds, query, groupMode)
    }, query ? 500 : 0)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [viewCcy, accountIds, query, groupMode, fetchData])

  const handleSort = (field: SortField) => {
    if (field === sortField) setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDir('desc') }
  }

  const sorted = sortRows(rows, sortField, sortDir)
  const totalPnl = totalValue - totalCost
  const totalPnlPct = totalCost > 0 ? totalPnl / totalCost : 0

  const priced = rows.filter((r) => r.priceRaw > 0)
  const topGainers = [...priced].sort((a, b) => b.pnlPct - a.pnlPct).slice(0, 5)
  const topLosers = [...priced].sort((a, b) => a.pnlPct - b.pnlPct).slice(0, 5)

  const toggleAccount = (id: string) => {
    setAccountIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  return (
    <div className="px-4 py-4">
      <div className="max-w-screen-2xl mx-auto">

        {/* ── Header KPIs ── */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl px-5 py-4 mb-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h1 className="text-xl font-semibold text-white">Pozycje maklerskie</h1>
            <div className="flex flex-wrap gap-3 items-center">
              {/* Total value pill */}
              <div className="bg-slate-700/60 border border-white/10 rounded-lg px-3 py-1.5 text-sm">
                <span className="text-white/40 mr-1.5">Wartość</span>
                <span className="font-semibold text-white tabular-nums">
                  {fmtMoney(totalValue || null, viewCcy)}
                </span>
              </div>
              {/* PnL pill */}
              {totalCost > 0 && (
                <div className={`border rounded-lg px-3 py-1.5 text-sm flex items-center gap-2 ${
                  totalPnl >= 0
                    ? 'bg-emerald-500/10 border-emerald-500/20'
                    : 'bg-red-500/10 border-red-500/20'
                }`}>
                  <span className="text-white/40">PnL</span>
                  <span className={`font-semibold tabular-nums ${totalPnl >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                    {fmtMoney(totalPnl, viewCcy)}
                  </span>
                  <PnlBadge pct={totalPnlPct} unit={false} />
                </div>
              )}
            </div>
          </div>

          {/* Gainers / losers */}
          {(topGainers.length > 0 || topLosers.length > 0) && (
            <div className="flex flex-wrap gap-4 mt-3 pt-3 border-t border-white/5">
              {topLosers.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs text-white/30">Tracące:</span>
                  {topLosers.map((r) => (
                    <span key={r.id} className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 font-medium tabular-nums">
                      {r.symbol} {fmtPct(r.pnlPct)}
                    </span>
                  ))}
                </div>
              )}
              {topGainers.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs text-white/30">Zyskujące:</span>
                  {topGainers.map((r) => (
                    <span key={r.id} className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-medium tabular-nums">
                      {r.symbol} {fmtPct(r.pnlPct)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Filters ── */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl px-4 py-3 mb-4 flex flex-wrap gap-3 items-center">
          {/* Search */}
          <div className="relative flex-1 min-w-[180px] max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/30" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Szukaj instrumentu…"
              className="w-full pl-7 pr-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
            />
          </div>

          {/* Account filter */}
          {brokerageAccounts.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {brokerageAccounts.map((acc) => {
                const active = accountIds.includes(acc.id)
                return (
                  <button
                    key={acc.id}
                    onClick={() => toggleAccount(acc.id)}
                    className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                      active
                        ? 'bg-blue-600 border-blue-500 text-white'
                        : 'bg-slate-900/40 border-white/10 text-white/50 hover:text-white hover:border-white/20'
                    }`}
                  >
                    {acc.name}
                  </button>
                )
              })}
            </div>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Grouping */}
          <div className="flex rounded-lg overflow-hidden border border-white/10">
            {(['SYMBOL', 'ACCOUNT'] as GroupMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setGroupMode(m)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  groupMode === m ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'
                }`}
              >
                {m === 'SYMBOL' ? 'Symbol' : 'Rachunek'}
              </button>
            ))}
          </div>

          {/* Currency */}
          <div className="flex rounded-lg overflow-hidden border border-white/10">
            {['PLN', 'USD', 'EUR'].map((ccy) => (
              <button
                key={ccy}
                onClick={() => setViewCcy(ccy)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  viewCcy === ccy ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'
                }`}
              >
                {ccy}
              </button>
            ))}
          </div>

          {/* Refresh */}
          <button
            onClick={() => fetchData(viewCcy, accountIds, query, groupMode)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-700/60 border border-white/10 text-white/60 hover:text-white transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Odśwież
          </button>
        </div>

        {/* ── Error ── */}
        {error && (
          <div className="mb-4 px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-sm flex items-center justify-between">
            {error}
            <button onClick={() => setError(null)} className="text-white/30 hover:text-white/60 ml-3">×</button>
          </div>
        )}

        {/* ── Table ── */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
          {loading && (
            <div className="flex items-center justify-center py-12 text-white/40 text-sm gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Ładowanie…
            </div>
          )}

          {!loading && sorted.length === 0 && (
            <div className="flex items-center justify-center py-16 text-white/30 text-sm">
              Brak pozycji dla wybranych filtrów.
            </div>
          )}

          {!loading && sorted.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left px-4 py-3">
                      <ThButton label="Symbol" field="symbol" sort={sortField} dir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-left px-4 py-3 hidden md:table-cell">
                      <ThButton label="Nazwa" field="name" sort={sortField} dir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-right px-4 py-3">
                      <ThButton label="Ilość" field="quantity" sort={sortField} dir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-right px-4 py-3 hidden sm:table-cell">
                      <span className="text-xs text-white/40 uppercase tracking-wide">Śr. zakup</span>
                    </th>
                    <th className="text-right px-4 py-3 hidden sm:table-cell">
                      <span className="text-xs text-white/40 uppercase tracking-wide">Cena</span>
                    </th>
                    <th className="text-right px-4 py-3">
                      <ThButton label="Wartość" field="value" sort={sortField} dir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-right px-4 py-3">
                      <ThButton label="PnL %" field="pnl_pct" sort={sortField} dir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-center px-4 py-3 hidden lg:table-cell">
                      <span className="text-xs text-white/40 uppercase tracking-wide">Rachunek</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((row, i) => {
                    const displayValue = row.valueView !== null ? row.valueView : row.valueRaw
                    const displayCcy = row.valueView !== null ? viewCcy : row.currency
                    const displayAvgCost = row.costView !== null && row.quantity > 0
                      ? row.costView / row.quantity
                      : row.avgCostRaw
                    const displayAvgCcy = row.costView !== null ? viewCcy : row.currency
                    const displayPrice = row.valueView !== null && row.quantity > 0
                      ? row.valueView / row.quantity
                      : row.priceRaw
                    const displayPriceCcy = row.valueView !== null ? viewCcy : row.currency

                    return (
                      <tr
                        key={row.id}
                        className={`border-b border-white/5 last:border-0 hover:bg-white/3 transition-colors ${
                          i % 2 === 0 ? '' : 'bg-white/[0.01]'
                        }`}
                      >
                        {/* Symbol */}
                        <td className="px-4 py-3">
                          <div>
                            <span className="font-semibold text-white">{row.symbol}</span>
                            {row.changePct !== 0 && (
                              <span className={`ml-1.5 text-xs ${row.changePct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {row.changePct >= 0 ? '+' : ''}{fmtNum(row.changePct * 100, 2)}%
                              </span>
                            )}
                            <p className="text-xs text-white/30 mt-0.5">{row.currency}</p>
                          </div>
                        </td>

                        {/* Name */}
                        <td className="px-4 py-3 hidden md:table-cell">
                          <span className="text-white/70 text-xs line-clamp-2 max-w-xs">{row.name}</span>
                        </td>

                        {/* Qty */}
                        <td className="px-4 py-3 text-right tabular-nums text-white/70">
                          {fmtNum(row.quantity, row.quantity % 1 === 0 ? 0 : 4)}
                        </td>

                        {/* Avg buy */}
                        <td className="px-4 py-3 text-right tabular-nums text-white/50 hidden sm:table-cell text-xs">
                          {fmtNum(displayAvgCost, 4)}&nbsp;{displayAvgCcy}
                        </td>

                        {/* Price */}
                        <td className="px-4 py-3 text-right tabular-nums hidden sm:table-cell">
                          <span className={`text-xs font-medium ${
                            row.changePct > 0 ? 'text-emerald-400' : row.changePct < 0 ? 'text-red-400' : 'text-white/60'
                          }`}>
                            {fmtNum(displayPrice, 4)}&nbsp;{displayPriceCcy}
                          </span>
                        </td>

                        {/* Value */}
                        <td className="px-4 py-3 text-right tabular-nums font-semibold text-white">
                          {fmtMoney(displayValue, displayCcy)}
                        </td>

                        {/* PnL % */}
                        <td className="px-4 py-3 text-right">
                          {row.priceRaw > 0 ? (
                            <PnlBadge pct={row.pnlPct} />
                          ) : (
                            <span className="text-white/20 text-xs">—</span>
                          )}
                        </td>

                        {/* Account */}
                        <td className="px-4 py-3 text-center hidden lg:table-cell">
                          <span className="text-xs text-white/40">{row.accountsDisp}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Row count */}
        {sorted.length > 0 && (
          <p className="text-xs text-white/25 mt-2 text-right">
            {sorted.length} pozycj{sorted.length === 1 ? 'a' : sorted.length <= 4 ? 'e' : 'i'}
          </p>
        )}

      </div>
    </div>
  )
}
