'use client'

import { useState, useEffect, useRef, useCallback, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { RefreshCw, Search, TrendingUp, TrendingDown, ChevronUp, ChevronDown as ChevronDownIcon, Minus, SlidersHorizontal, LoaderCircle, BarChart2, FileText } from 'lucide-react'
import type { HoldingRawRow, HoldingsResult } from '@/lib/api/holdings'
import type { FxRates } from '@/lib/api/nbp'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

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
  const sign = val > 0 ? '+' : val < 0 ? '-' : ''
  return sign + fmtNum(Math.abs(val)) + '%'
}

type SortField = 'symbol' | 'quantity' | 'value' | 'pnl_pct' | 'pnl_amount' | 'name'
type SortDir = 'asc' | 'desc'
type HoldingActionKind = 'SPLIT' | 'ADJUSTMENT' | 'CONVERSION'

function sortRows(rows: HoldingRawRow[], field: SortField, dir: SortDir): HoldingRawRow[] {
  return [...rows].sort((a, b) => {
    let av: number | string, bv: number | string
    switch (field) {
      case 'symbol': av = a.symbol; bv = b.symbol; break
      case 'name': av = a.name; bv = b.name; break
      case 'quantity': av = a.quantity; bv = b.quantity; break
      case 'value': av = a.valueView ?? a.valueRaw; bv = b.valueView ?? b.valueRaw; break
      case 'pnl_pct': av = a.pnlPct; bv = b.pnlPct; break
      case 'pnl_amount': av = a.pnlView ?? a.pnlAmountRaw; bv = b.pnlView ?? b.pnlAmountRaw; break
      default: av = 0; bv = 0
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

function normalizeDecimalInput(value: string): string {
  return value.trim().replace(',', '.')
}

function toDateTimeLocal(value: Date): string {
  const offsetMs = value.getTimezoneOffset() * 60_000
  return new Date(value.getTime() - offsetMs).toISOString().slice(0, 16)
}

function toIsoString(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toISOString()
}

function HoldingContextMenu({
  symbol, mic, top, left, onClose,
}: {
  symbol: string; mic: string; top: number; left: number
  onClose: () => void
}) {
  const router = useRouter()
  return (
    <div
      style={{ position: 'fixed', top, left, zIndex: 9999 }}
      className="bg-slate-900 border border-white/10 rounded-xl shadow-xl py-1 min-w-[160px] backdrop-blur-md"
      data-holding-context-menu
      onClick={(e) => e.stopPropagation()}
    >
      <button
        className="w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
        onClick={() => {
          onClose()
          router.push(`/stock/charts/${mic}?${new URLSearchParams({ symbol }).toString()}`)
        }}
      >
        <BarChart2 className="w-4 h-4" />
        Wykresy
      </button>
      {mic !== 'STCM' && (
        <button
          className="w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
          onClick={() => {
            onClose()
            router.push(`/stock/${encodeURIComponent(mic)}/${encodeURIComponent(symbol)}/report`)
          }}
        >
          <FileText className="w-4 h-4" />
          Raport AI
        </button>
      )}
    </div>
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
  const [actionRow, setActionRow] = useState<HoldingRawRow | null>(null)
  const [actionKind, setActionKind] = useState<HoldingActionKind>('SPLIT')
  const [actionAccountId, setActionAccountId] = useState('')
  const [splitRatio, setSplitRatio] = useState('2')
  const [adjustQuantity, setAdjustQuantity] = useState('')
  const [adjustAvgCost, setAdjustAvgCost] = useState('')
  const [conversionQuantity, setConversionQuantity] = useState('')
  const [targetSymbol, setTargetSymbol] = useState('')
  const [targetMic, setTargetMic] = useState('XWAR')
  const [targetName, setTargetName] = useState('')
  const [actionNote, setActionNote] = useState('')
  const [actionDate, setActionDate] = useState(() => toDateTimeLocal(new Date()))
  const [actionError, setActionError] = useState<string | null>(null)
  const [isActionPending, startActionTransition] = useTransition()
  const [contextMenu, setContextMenu] = useState<{ symbol: string; mic: string; top: number; left: number } | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!contextMenu) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Element
      if (!target.closest('[data-holding-context-menu]')) setContextMenu(null)
    }
    const keyHandler = (e: KeyboardEvent) => { if (e.key === 'Escape') setContextMenu(null) }
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', keyHandler)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('keydown', keyHandler)
    }
  }, [contextMenu])

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

  const priced = rows.filter((r) => !r.quoteMissing && r.priceRaw > 0)
  const topGainers = priced.filter((r) => r.pnlPct > 0).sort((a, b) => b.pnlPct - a.pnlPct).slice(0, 5)
  const topLosers = priced.filter((r) => r.pnlPct < 0).sort((a, b) => a.pnlPct - b.pnlPct).slice(0, 5)
  const posCount = priced.filter((r) => r.pnlPct > 0).length
  const negCount = priced.filter((r) => r.pnlPct < 0).length

  function openHoldingAction(row: HoldingRawRow) {
    setActionRow(row)
    setActionKind(row.quoteMissing ? 'ADJUSTMENT' : 'SPLIT')
    setActionAccountId(row.accountId || brokerageAccounts[0]?.id || '')
    setSplitRatio('2')
    setAdjustQuantity(String(row.quantity))
    setAdjustAvgCost(String(row.avgCostRaw))
    setConversionQuantity(String(row.quantity))
    setTargetSymbol('')
    setTargetMic(row.instrumentMic || 'XWAR')
    setTargetName('')
    setActionNote(row.quoteMissing ? `Korekta holdingu, stary symbol/nazwa: ${row.symbol}${row.name ? ` ${row.name}` : ''}` : '')
    setActionDate(toDateTimeLocal(new Date()))
    setActionError(null)
  }

  function closeHoldingAction() {
    if (isActionPending) return
    setActionRow(null)
    setActionError(null)
  }

  function submitHoldingAction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!actionRow) return
    if (!actionAccountId) { setActionError('Wybierz rachunek maklerski'); return }
    if (!actionRow.instrumentMic) { setActionError('Brak kodu rynku instrumentu'); return }
    if (!actionDate) { setActionError('Podaj datę operacji'); return }

    const ratio = Number(normalizeDecimalInput(splitRatio))
    const qty = Number(normalizeDecimalInput(adjustQuantity))
    const avg = Number(normalizeDecimalInput(adjustAvgCost))
    const conversionQty = Number(normalizeDecimalInput(conversionQuantity))
    if ((actionKind === 'SPLIT' || actionKind === 'CONVERSION') && (!Number.isFinite(ratio) || ratio <= 0)) {
      setActionError(actionKind === 'SPLIT' ? 'Podaj dodatni współczynnik splitu' : 'Podaj dodatni współczynnik konwersji')
      return
    }
    if (actionKind === 'ADJUSTMENT') {
      if (!Number.isFinite(qty) || qty < 0) { setActionError('Podaj nieujemną ilość po korekcie'); return }
      if (!Number.isFinite(avg) || avg < 0) { setActionError('Podaj nieujemną średnią cenę po korekcie'); return }
      if (!actionNote.trim()) { setActionError('Podaj notatkę korekty'); return }
    }
    if (actionKind === 'CONVERSION') {
      if (!Number.isFinite(conversionQty) || conversionQty <= 0) { setActionError('Podaj dodatnią ilość do konwersji'); return }
      if (conversionQty > actionRow.quantity) { setActionError('Ilość do konwersji nie może przekraczać posiadanej ilości'); return }
      if (!targetSymbol.trim()) { setActionError('Podaj symbol instrumentu docelowego'); return }
      if (!targetMic.trim()) { setActionError('Podaj rynek instrumentu docelowego'); return }
      if (!actionNote.trim()) { setActionError('Podaj notatkę konwersji'); return }
    }

    setActionError(null)
    startActionTransition(async () => {
      const response = await fetch('/api/wallet/brokerage/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brokerage_account_id: actionAccountId,
          instrument_symbol: actionRow.symbol,
          instrument_mic: actionRow.instrumentMic,
          instrument_name: actionRow.name || actionRow.symbol,
          kind: actionKind,
          quantity: actionKind === 'SPLIT'
            ? '0'
            : actionKind === 'CONVERSION'
              ? normalizeDecimalInput(conversionQuantity)
              : normalizeDecimalInput(adjustQuantity),
          price: actionKind === 'ADJUSTMENT' ? normalizeDecimalInput(adjustAvgCost) : '0',
          currency: actionRow.currency,
          split_ratio: actionKind === 'SPLIT' || actionKind === 'CONVERSION' ? normalizeDecimalInput(splitRatio) : '0',
          note: actionKind === 'ADJUSTMENT' || actionKind === 'CONVERSION' ? actionNote.trim() : null,
          target_instrument_symbol: actionKind === 'CONVERSION' ? targetSymbol.trim().toUpperCase() : undefined,
          target_instrument_mic: actionKind === 'CONVERSION' ? targetMic.trim().toUpperCase() : undefined,
          target_instrument_name: actionKind === 'CONVERSION' ? (targetName.trim() || targetSymbol.trim().toUpperCase()) : undefined,
          trade_at: toIsoString(actionDate),
        }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null) as { error?: string } | null
        setActionError(body?.error ?? 'Nie udało się zapisać operacji maklerskiej')
        return
      }

      setActionRow(null)
      await fetchData(viewCcy, accountIds, query, groupMode)
    })
  }

  return (
    <div className="px-4 py-4">
      <div className="max-w-screen-2xl mx-auto">

        {/* ── Header KPIs ── */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl px-5 py-4 mb-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h1 className="text-xl font-semibold text-white">Pozycje maklerskie</h1>
            <div className="flex flex-wrap gap-3 items-center">
              {/* Pos/neg position count chips */}
              {priced.length > 0 && (
                <>
                  <span className="inline-flex items-center gap-1 text-sm px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 tabular-nums">
                    <TrendingUp className="w-3.5 h-3.5" />
                    +{posCount}
                  </span>
                  <span className="inline-flex items-center gap-1 text-sm px-2.5 py-1 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 tabular-nums">
                    <TrendingDown className="w-3.5 h-3.5" />
                    −{negCount}
                  </span>
                </>
              )}
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
                  <PnlBadge pct={totalPnlPct} />
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
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-white/10 bg-slate-900/40 text-white/60 hover:text-white hover:border-white/20 transition-colors">
                  {accountIds.length === 0
                    ? 'Wszystkie rachunki'
                    : accountIds.length === 1
                      ? brokerageAccounts.find((a) => a.id === accountIds[0])?.name ?? '1 rachunek'
                      : `${accountIds.length} rachunki`}
                  <ChevronDownIcon className="w-3 h-3 opacity-50" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="bg-slate-900 border-white/10 text-white min-w-[200px]">
                {brokerageAccounts.map((acc) => (
                  <DropdownMenuCheckboxItem
                    key={acc.id}
                    checked={accountIds.includes(acc.id)}
                    onCheckedChange={(checked) =>
                      setAccountIds((prev) =>
                        checked ? [...prev, acc.id] : prev.filter((x) => x !== acc.id)
                      )
                    }
                    className="text-xs text-white/80 focus:bg-white/10 focus:text-white"
                  >
                    {acc.name}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
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
                    <th className="text-right px-4 py-3 hidden sm:table-cell">
                      <ThButton label="Zysk/Strata" field="pnl_amount" sort={sortField} dir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-right px-4 py-3">
                      <ThButton label="PnL %" field="pnl_pct" sort={sortField} dir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-center px-4 py-3 hidden lg:table-cell">
                      <span className="text-xs text-white/40 uppercase tracking-wide">Rachunek</span>
                    </th>
                    <th className="text-center px-4 py-3">
                      <span className="text-xs text-white/40 uppercase tracking-wide">Akcje</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((row, i) => {
                    const displayValue = row.quoteMissing ? null : row.valueView !== null ? row.valueView : row.valueRaw
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
                        onContextMenu={(e) => {
                          e.preventDefault()
                          setContextMenu({ symbol: row.symbol, mic: row.instrumentMic, top: e.clientY, left: e.clientX })
                        }}
                      >
                        {/* Symbol */}
                        <td className="px-4 py-3">
                          <div>
                            <span className="font-semibold text-white">{row.symbol}</span>
                            {!row.quoteMissing && row.changePct !== 0 && (
                              <span className={`ml-1.5 text-xs ${row.changePct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {fmtPct(row.changePct, false)}
                              </span>
                            )}
                            <p className="text-xs text-white/30 mt-0.5">{row.currency}</p>
                            {row.quoteMissing && (
                              <span className="mt-1 inline-flex text-[11px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                                Brak notowań
                              </span>
                            )}
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
                          {row.quoteMissing ? (
                            <span className="text-xs text-amber-300">Brak notowań</span>
                          ) : (
                            <span className={`text-xs font-medium ${
                              row.changePct > 0 ? 'text-emerald-400' : row.changePct < 0 ? 'text-red-400' : 'text-white/60'
                            }`}>
                              {fmtNum(displayPrice, 4)}&nbsp;{displayPriceCcy}
                            </span>
                          )}
                        </td>

                        {/* Value */}
                        <td className="px-4 py-3 text-right tabular-nums font-semibold text-white">
                          {fmtMoney(displayValue, displayCcy)}
                        </td>

                        {/* Zysk/Strata */}
                        <td className="px-4 py-3 text-right tabular-nums hidden sm:table-cell">
                          {!row.quoteMissing && row.priceRaw > 0 ? (() => {
                            const pnl = row.pnlView ?? row.pnlAmountRaw
                            const pnlCcy = row.pnlView !== null ? viewCcy : row.currency
                            return (
                              <span className={`text-sm font-medium ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {pnl >= 0 ? '+' : ''}{fmtMoney(pnl, pnlCcy)}
                              </span>
                            )
                          })() : (
                            <span className="text-white/20 text-xs">—</span>
                          )}
                        </td>

                        {/* PnL % */}
                        <td className="px-4 py-3 text-right">
                          {!row.quoteMissing && row.priceRaw > 0 ? (
                            <PnlBadge pct={row.pnlPct} />
                          ) : (
                            <span className="text-white/20 text-xs">—</span>
                          )}
                        </td>

                        {/* Account */}
                        <td className="px-4 py-3 text-center hidden lg:table-cell">
                          <span className="text-xs text-white/40">{row.accountsDisp}</span>
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3 text-center">
                          <button
                            type="button"
                            aria-label={`Split lub korekta ${row.symbol}`}
                            title="Split lub korekta holdingu"
                            onClick={() => openHoldingAction(row)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-slate-900/50 text-white/45 hover:border-emerald-500/40 hover:text-emerald-300 hover:bg-emerald-500/10 transition-colors"
                          >
                            <SlidersHorizontal className="w-4 h-4" />
                          </button>
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
      <Dialog open={!!actionRow} onOpenChange={(open) => { if (!open) closeHoldingAction() }}>
        <DialogContent className="bg-slate-900 border-white/10 text-white sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">Split lub korekta holdingu</DialogTitle>
            <DialogDescription className="text-white/50 text-sm">
              {actionRow ? `${actionRow.symbol}${actionRow.name ? ` · ${actionRow.name}` : ''}` : ''}
            </DialogDescription>
          </DialogHeader>

          {actionRow && (
            <form onSubmit={submitHoldingAction} className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-white/70 text-xs">Rachunek maklerski *</Label>
                  <Select value={actionAccountId} onValueChange={setActionAccountId}>
                    <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
                      <SelectValue placeholder="Wybierz rachunek" />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-900 border-white/10 text-white">
                      {brokerageAccounts.map((account) => (
                        <SelectItem key={account.id} value={account.id}>{account.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label className="text-white/70 text-xs">Typ operacji *</Label>
                  <Select value={actionKind} onValueChange={(value: HoldingActionKind) => setActionKind(value)}>
                    <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-900 border-white/10 text-white">
                      <SelectItem value="SPLIT">SPLIT</SelectItem>
                      <SelectItem value="ADJUSTMENT">Korekta</SelectItem>
                      <SelectItem value="CONVERSION">Konwersja</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {actionKind === 'SPLIT' && (
                <div className="space-y-1">
                  <Label htmlFor="holding-action-split-ratio" className="text-white/70 text-xs">Współczynnik splitu *</Label>
                  <Input
                    id="holding-action-split-ratio"
                    value={splitRatio}
                    onChange={(event) => setSplitRatio(event.target.value)}
                    inputMode="decimal"
                    placeholder="2 lub 0.1"
                    className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
                  />
                </div>
              )}

              {actionKind === 'CONVERSION' && (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label htmlFor="holding-action-conversion-quantity" className="text-white/70 text-xs">Ilość do konwersji *</Label>
                      <Input
                        id="holding-action-conversion-quantity"
                        value={conversionQuantity}
                        onChange={(event) => setConversionQuantity(event.target.value)}
                        inputMode="decimal"
                        className="bg-slate-800 border-white/10 text-white h-8 text-sm"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="holding-action-conversion-ratio" className="text-white/70 text-xs">Współczynnik konwersji *</Label>
                      <Input
                        id="holding-action-conversion-ratio"
                        value={splitRatio}
                        onChange={(event) => setSplitRatio(event.target.value)}
                        inputMode="decimal"
                        placeholder="np. 1, 0.2 albo 2"
                        className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div className="space-y-1">
                      <Label htmlFor="holding-action-target-symbol" className="text-white/70 text-xs">Nowy symbol *</Label>
                      <Input
                        id="holding-action-target-symbol"
                        value={targetSymbol}
                        onChange={(event) => setTargetSymbol(event.target.value)}
                        placeholder="GIG"
                        className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm uppercase"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="holding-action-target-mic" className="text-white/70 text-xs">Rynek *</Label>
                      <Input
                        id="holding-action-target-mic"
                        value={targetMic}
                        onChange={(event) => setTargetMic(event.target.value)}
                        placeholder="XWAR"
                        className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm uppercase"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="holding-action-target-name" className="text-white/70 text-xs">Nazwa</Label>
                      <Input
                        id="holding-action-target-name"
                        value={targetName}
                        onChange={(event) => setTargetName(event.target.value)}
                        placeholder="GIGROUP"
                        className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
                      />
                    </div>
                  </div>
                </div>
              )}

              {actionKind === 'ADJUSTMENT' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <Label htmlFor="holding-action-quantity" className="text-white/70 text-xs">Ilość po korekcie *</Label>
                    <Input
                      id="holding-action-quantity"
                      value={adjustQuantity}
                      onChange={(event) => setAdjustQuantity(event.target.value)}
                      inputMode="decimal"
                      className="bg-slate-800 border-white/10 text-white h-8 text-sm"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="holding-action-avg-cost" className="text-white/70 text-xs">Śr. cena po korekcie *</Label>
                    <Input
                      id="holding-action-avg-cost"
                      value={adjustAvgCost}
                      onChange={(event) => setAdjustAvgCost(event.target.value)}
                      inputMode="decimal"
                      className="bg-slate-800 border-white/10 text-white h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              <div className="space-y-1">
                <Label htmlFor="holding-action-date" className="text-white/70 text-xs">Data operacji *</Label>
                <Input
                  id="holding-action-date"
                  type="datetime-local"
                  value={actionDate}
                  onChange={(event) => setActionDate(event.target.value)}
                  className="bg-slate-800 border-white/10 text-white h-8 text-sm"
                />
              </div>

              {(actionKind === 'ADJUSTMENT' || actionKind === 'CONVERSION') && (
                <div className="space-y-1">
                  <Label htmlFor="holding-action-note" className="text-white/70 text-xs">
                    {actionKind === 'CONVERSION' ? 'Notatka konwersji *' : 'Notatka korekty *'}
                  </Label>
                  <Input
                    id="holding-action-note"
                    value={actionNote}
                    onChange={(event) => setActionNote(event.target.value)}
                    maxLength={500}
                    placeholder={actionKind === 'CONVERSION' ? 'np. WORKSERV -> GIGROUP' : 'np. stara nazwa: WORKSERV'}
                    className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
                  />
                </div>
              )}

              {actionError && <p className="text-sm text-red-400">{actionError}</p>}

              <div className="flex justify-end gap-2 pt-1">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={closeHoldingAction}
                  disabled={isActionPending}
                  className="text-white/60 hover:text-white hover:bg-white/10"
                >
                  Anuluj
                </Button>
                <Button
                  type="submit"
                  disabled={isActionPending}
                  className="bg-emerald-700 hover:bg-emerald-600 text-white gap-2"
                >
                  {isActionPending && <LoaderCircle className="w-4 h-4 animate-spin" />}
                  Zapisz
                </Button>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {contextMenu && (
        <HoldingContextMenu
          symbol={contextMenu.symbol}
          mic={contextMenu.mic}
          top={contextMenu.top}
          left={contextMenu.left}
          onClose={() => setContextMenu(null)}
        />
      )}
    </div>
  )
}
