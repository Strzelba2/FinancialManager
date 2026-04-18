'use client'

import { useState, useRef, useEffect } from 'react'
import { Plus, Save, Trash2, ChevronLeft, ChevronRight, Search, RefreshCw, ChevronDown, Check } from 'lucide-react'
import { convertCurrency } from '@/lib/api/nbp'
import type { EventRow, EventsPageResult } from '@/lib/api/brokerageEvents'
import { DateTimePicker } from '@/components/ui/date-time-picker'
import { TransactionsDialog } from '@/features/wallet/components/TransactionsDialog'
import type { TransactionBrokerageAccountOpt } from '@/features/wallet/components/TransactionsDialog'

// ── Constants ─────────────────────────────────────────────────────────────────

const KIND_LABELS: Record<string, string> = {
  BUY: 'Kupno',
  SELL: 'Sprzedaż',
  SPLIT: 'Split',
  DIV: 'Dywidenda',
  FEE: 'Opłata',
  TAX: 'Podatek',
}

const KIND_COLORS: Record<string, string> = {
  BUY: 'bg-blue-500/20 text-blue-300',
  SELL: 'bg-red-500/20 text-red-300',
  DIV: 'bg-emerald-500/20 text-emerald-300',
  SPLIT: 'bg-cyan-500/20 text-cyan-300',
  FEE: 'bg-amber-500/20 text-amber-300',
  TAX: 'bg-amber-500/20 text-amber-300',
}

const ALL_KINDS = ['BUY', 'SELL', 'DIV', 'SPLIT', 'FEE', 'TAX']
const ALL_CCYS = ['PLN', 'USD', 'EUR']
const PAGE_SIZES = [20, 40, 80, 120]

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtNum(v: number, d = 2): string {
  return v.toLocaleString('pl-PL', { minimumFractionDigits: d, maximumFractionDigits: d })
}

function fmtMoney(v: number, ccy: string): string {
  return fmtNum(v) + '\u00a0' + ccy
}

// ── Sub-components ────────────────────────────────────────────────────────────

function KindChip({ kind }: { kind: string }) {
  const label = KIND_LABELS[kind] ?? kind
  const cls = KIND_COLORS[kind] ?? 'bg-white/5 text-white/50'
  return (
    <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded ${cls}`}>
      {label}
    </span>
  )
}

function FilterPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
        active
          ? 'bg-blue-600 border-blue-500 text-white'
          : 'bg-slate-900/40 border-white/10 text-white/50 hover:text-white hover:border-white/20'
      }`}
    >
      {label}
    </button>
  )
}

// Multi-select dropdown for kinds
function KindMultiSelect({
  selected,
  onChange,
}: {
  selected: string[]
  onChange: (next: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  function toggle(k: string) {
    const next = selected.includes(k) ? selected.filter((x) => x !== k) : [...selected, k]
    onChange(next)
  }

  const label =
    selected.length === 0
      ? 'Wszystkie typy'
      : selected.map((k) => KIND_LABELS[k] ?? k).join(', ')

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
          selected.length > 0
            ? 'bg-blue-600/20 border-blue-500/40 text-blue-300'
            : 'bg-slate-900/40 border-white/10 text-white/50 hover:text-white hover:border-white/20'
        }`}
      >
        <span className="max-w-[160px] truncate">{label}</span>
        <ChevronDown size={12} className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 z-20 bg-slate-900 border border-white/10 rounded-xl shadow-2xl min-w-[170px] py-1.5 backdrop-blur-md">
          {ALL_KINDS.map((k) => {
            const active = selected.includes(k)
            return (
              <button
                key={k}
                onClick={() => toggle(k)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-white/5 transition-colors text-left"
              >
                <span className={`flex items-center justify-center w-3.5 h-3.5 rounded border ${
                  active ? 'bg-blue-600 border-blue-600' : 'border-white/20'
                }`}>
                  {active && <Check size={9} className="text-white" />}
                </span>
                <KindChip kind={k} />
              </button>
            )
          })}
          {selected.length > 0 && (
            <>
              <div className="my-1 border-t border-white/5" />
              <button
                onClick={() => onChange([])}
                className="w-full px-3 py-1.5 text-xs text-white/30 hover:text-white/60 hover:bg-white/5 text-left transition-colors"
              >
                Wyczyść
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  brokerageAccounts: { id: string; name: string; walletName?: string }[]
  initialData: EventsPageResult
}

type OrigRow = { quantity: number; priceNative: number }

export function BrokerageEventsPage({ brokerageAccounts, initialData }: Props) {
  // ── Filter state ────────────────────────────────────────────────────────────
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([])
  const [selectedKinds, setSelectedKinds] = useState<string[]>([])
  const [q, setQ] = useState('')
  const [viewCcy, setViewCcy] = useState(initialData.viewCcy)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(40)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  // ── Data state ──────────────────────────────────────────────────────────────
  const [data, setData] = useState<EventsPageResult>(initialData)
  const [rows, setRows] = useState<EventRow[]>(initialData.rows)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  // ── Dirty tracking ──────────────────────────────────────────────────────────
  const [dirty, setDirty] = useState<Record<string, Record<string, string>>>({})
  const origRef = useRef<Record<string, OrigRow>>({})

  useEffect(() => {
    const orig: Record<string, OrigRow> = {}
    for (const r of initialData.rows) {
      orig[r.id] = { quantity: r.quantity, priceNative: r.priceNative }
    }
    origRef.current = orig
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Inline editing ──────────────────────────────────────────────────────────
  const [editingCell, setEditingCell] = useState<{ rowId: string; field: 'quantity' | 'price' } | null>(null)
  const [editValue, setEditValue] = useState('')

  // ── Toast ───────────────────────────────────────────────────────────────────
  const [toast, setToast] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function showToast(msg: string, type: 'ok' | 'err' = 'ok') {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ msg, type })
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }

  // ── Add event dialog ────────────────────────────────────────────────────────
  const [dialogOpen, setDialogOpen] = useState(false)

  // ── Delete modal ────────────────────────────────────────────────────────────
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  // ── Debounce ────────────────────────────────────────────────────────────────
  const qTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Fetch ───────────────────────────────────────────────────────────────────

  type LoadOverrides = Partial<{
    page: number; size: number; viewCcy: string; q: string
    dateFrom: string; dateTo: string; accounts: string[]; kinds: string[]
  }>

  async function loadPage(overrides: LoadOverrides = {}) {
    setLoading(true)
    const p   = overrides.page    ?? page
    const sz  = overrides.size    ?? pageSize
    const vc  = overrides.viewCcy ?? viewCcy
    const qv  = overrides.q       ?? q
    const df  = overrides.dateFrom ?? dateOnly(dateFrom)
    const dt  = overrides.dateTo   ?? dateOnly(dateTo)
    const acc = overrides.accounts ?? selectedAccounts
    const kds = overrides.kinds    ?? selectedKinds

    const sp = new URLSearchParams()
    sp.set('page', String(p))
    sp.set('size', String(sz))
    sp.set('view_ccy', vc)
    if (qv) sp.set('q', qv)
    if (df) sp.set('date_from', df)
    if (dt) sp.set('date_to', dt)
    acc.forEach((id) => sp.append('account_id', id))
    kds.forEach((k)  => sp.append('kind', k))

    try {
      const res = await fetch(`/api/wallet/events?${sp}`)
      if (!res.ok) throw new Error('fetch failed')
      const d = await res.json() as EventsPageResult
      setData(d)
      setRows(d.rows)
      setDirty({})
      const orig: Record<string, OrigRow> = {}
      for (const r of d.rows) orig[r.id] = { quantity: r.quantity, priceNative: r.priceNative }
      origRef.current = orig
    } catch {
      showToast('Błąd podczas ładowania danych', 'err')
    } finally {
      setLoading(false)
    }
  }

  // ── Handlers ─────────────────────────────────────────────────────────────────

  function toggleAccount(id: string) {
    const next = selectedAccounts.includes(id)
      ? selectedAccounts.filter((a) => a !== id)
      : [...selectedAccounts, id]
    setSelectedAccounts(next)
    setPage(1)
    loadPage({ page: 1, accounts: next })
  }

  function handleKindsChange(next: string[]) {
    setSelectedKinds(next)
    setPage(1)
    loadPage({ page: 1, kinds: next })
  }

  function handleQChange(value: string) {
    setQ(value)
    if (qTimerRef.current) clearTimeout(qTimerRef.current)
    qTimerRef.current = setTimeout(() => { setPage(1); loadPage({ page: 1, q: value }) }, 500)
  }

  function handleViewCcyChange(ccy: string) {
    setViewCcy(ccy); setPage(1); loadPage({ page: 1, viewCcy: ccy })
  }

  function handlePageChange(newPage: number) { setPage(newPage); loadPage({ page: newPage }) }

  function handleSizeChange(size: number) { setPageSize(size); setPage(1); loadPage({ page: 1, size }) }

  // DateTimePicker returns "yyyy-MM-dd'T'HH:mm" — we only send the date part to the API
  function dateOnly(dt: string) { return dt ? dt.slice(0, 10) : '' }

  function setDateRange(range: string) {
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    function toLocal(d: Date) {
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T00:00`
    }
    const to = range === 'ALL' ? '' : toLocal(now)
    let from = ''
    if (range === '1M') { const d = new Date(now); d.setMonth(d.getMonth() - 1); from = toLocal(d) }
    else if (range === '3M') { const d = new Date(now); d.setMonth(d.getMonth() - 3); from = toLocal(d) }
    else if (range === '1Y') { const d = new Date(now); d.setFullYear(d.getFullYear() - 1); from = toLocal(d) }
    setDateFrom(from); setDateTo(to); setPage(1)
    loadPage({ page: 1, dateFrom: dateOnly(from), dateTo: dateOnly(to) })
  }

  // ── Inline editing ──────────────────────────────────────────────────────────

  function startEdit(rowId: string, field: 'quantity' | 'price') {
    const row = rows.find((r) => r.id === rowId)
    if (!row) return
    setEditingCell({ rowId, field })
    setEditValue(String(field === 'quantity' ? row.quantity : row.priceView))
  }

  function commitEdit() {
    if (!editingCell) return
    const { rowId, field } = editingCell
    setEditingCell(null)
    const numValue = parseFloat(editValue.replace(',', '.'))
    if (isNaN(numValue) || numValue < 0) return

    setRows((prev) => prev.map((r) => {
      if (r.id !== rowId) return r
      const updated = { ...r }
      if (field === 'quantity') {
        updated.quantity = numValue
        updated.notionalView = numValue * r.priceView
        updated.notionalFmt = fmtMoney(updated.notionalView, viewCcy)
      } else {
        updated.priceView = numValue
        updated.priceNative = convertCurrency(numValue, viewCcy, r.currency, data.fxRates)
        updated.notionalView = r.quantity * numValue
        updated.notionalFmt = fmtMoney(updated.notionalView, viewCcy)
      }
      return updated
    }))

    setDirty((prev) => {
      const orig = origRef.current[rowId]
      if (!orig) return prev
      const rowPatch = { ...(prev[rowId] ?? {}) }
      if (field === 'quantity') {
        if (Math.abs(numValue - orig.quantity) > 0.000001) rowPatch.quantity = String(numValue)
        else delete rowPatch.quantity
      } else {
        const rowCcy = rows.find((r) => r.id === rowId)?.currency ?? viewCcy
        const newNative = convertCurrency(numValue, viewCcy, rowCcy, data.fxRates)
        if (Math.abs(newNative - orig.priceNative) > 0.000001) rowPatch.price = String(newNative)
        else delete rowPatch.price
      }
      if (Object.keys(rowPatch).length === 0) {
        const next = { ...prev }
        delete next[rowId]
        return next
      }
      return { ...prev, [rowId]: rowPatch }
    })
  }

  // ── Save / Delete ────────────────────────────────────────────────────────────

  async function handleSave() {
    const items = Object.entries(dirty).map(([id, patch]) => ({ id, ...patch }))
    if (!items.length) return
    setSaving(true)
    try {
      const res = await fetch('/api/wallet/events', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      })
      if (!res.ok) throw new Error()
      showToast('Zapisano zmiany')
      await loadPage()
    } catch { showToast('Błąd podczas zapisywania', 'err') }
    finally { setSaving(false) }
  }

  async function handleDelete(id: string) {
    setDeleteTarget(null)
    try {
      const res = await fetch(`/api/wallet/events/${id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error()
      showToast('Usunięto operację')
      await loadPage()
    } catch { showToast('Błąd podczas usuwania', 'err') }
  }

  // ── Computed ─────────────────────────────────────────────────────────────────

  const dirtyCount = Object.keys(dirty).length
  const totalPages = Math.max(1, Math.ceil(data.total / pageSize))
  const showAllNotional = Math.abs(data.allNotional - data.pageNotional) > 0.01

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="px-4 py-4">
      <div className="max-w-screen-2xl mx-auto">

        {/* Header */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl px-5 py-4 mb-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h1 className="text-xl font-semibold text-white">Operacje maklerskie</h1>
            <div className="flex flex-wrap items-center gap-3">
              {/* Notionals */}
              <div className="bg-slate-700/60 border border-white/10 rounded-lg px-3 py-1.5 text-sm flex items-center gap-1.5">
                <span className="text-white/40">Strona</span>
                <span className="font-semibold text-white tabular-nums">{fmtMoney(data.pageNotional, viewCcy)}</span>
              </div>
              {showAllNotional && (
                <div className="bg-slate-700/60 border border-white/10 rounded-lg px-3 py-1.5 text-sm flex items-center gap-1.5">
                  <span className="text-white/40">Wszystkie</span>
                  <span className="font-semibold text-white tabular-nums">{fmtMoney(data.allNotional, viewCcy)}</span>
                </div>
              )}
              {/* Add event button */}
              <button
                onClick={() => setDialogOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border bg-slate-700/60 border-white/10 text-white/70 hover:text-white hover:bg-slate-600/60 transition-colors"
              >
                <Plus size={14} />
                Dodaj operację
              </button>
              {/* Save button */}
              <button
                onClick={handleSave}
                disabled={dirtyCount === 0 || saving}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                  dirtyCount > 0 && !saving
                    ? 'bg-blue-600 border-blue-500 text-white hover:bg-blue-500'
                    : 'bg-slate-700/60 border-white/10 text-white/30 cursor-not-allowed'
                }`}
              >
                <Save size={14} />
                {saving ? 'Zapisuję…' : dirtyCount > 0 ? `Zapisz (${dirtyCount})` : 'Zapisz'}
              </button>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl px-4 py-3 mb-4 space-y-3">

          {/* Row 1: accounts · kind multi-select */}
          <div className="flex flex-wrap gap-2 items-center">
            {brokerageAccounts.length > 0 && (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {brokerageAccounts.map((a) => (
                    <FilterPill
                      key={a.id}
                      label={a.name}
                      active={selectedAccounts.includes(a.id)}
                      onClick={() => toggleAccount(a.id)}
                    />
                  ))}
                </div>
                <div className="w-px h-4 bg-white/10 self-center" />
              </>
            )}
            <KindMultiSelect selected={selectedKinds} onChange={handleKindsChange} />
          </div>

          {/* Row 2: search + currency (left) | presets + pickers + refresh (right) */}
          <div className="flex flex-wrap items-center justify-between gap-2">

            {/* Left */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/30 pointer-events-none" />
                <input
                  type="text"
                  value={q}
                  onChange={(e) => handleQChange(e.target.value)}
                  placeholder="Szukaj instrumentu…"
                  className="w-52 pl-8 pr-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
                />
              </div>
              <div className="flex rounded-lg overflow-hidden border border-white/10">
                {ALL_CCYS.map((c) => (
                  <button
                    key={c}
                    onClick={() => handleViewCcyChange(c)}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                      viewCcy === c ? 'bg-blue-600 text-white' : 'text-white/50 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>

            {/* Right: date presets + pickers + refresh */}
            <div className="flex flex-wrap items-center gap-1.5">
              {(['1M', '3M', '1Y', 'ALL'] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => setDateRange(r)}
                  className="h-8 px-3 rounded-lg text-xs font-medium transition-colors border bg-transparent border-white/10 text-white/50 hover:text-white hover:border-white/20"
                >
                  {r === 'ALL' ? 'Wszystkie' : r}
                </button>
              ))}
              <div className="w-px h-4 bg-white/10 self-center" />
              <DateTimePicker
                value={dateFrom}
                onChange={(v) => { setDateFrom(v); setPage(1); loadPage({ page: 1, dateFrom: dateOnly(v) }) }}
                placeholder="Od daty"
                className="w-36"
              />
              <span className="text-white/20 text-xs">–</span>
              <DateTimePicker
                value={dateTo}
                onChange={(v) => { setDateTo(v); setPage(1); loadPage({ page: 1, dateTo: dateOnly(v) }) }}
                placeholder="Do daty"
                className="w-36"
              />
              <button
                onClick={() => loadPage()}
                disabled={loading}
                title="Odśwież"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-700/60 border border-white/10 text-white/60 hover:text-white transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                Odśwież
              </button>
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden mb-4">
          {loading && (
            <div className="flex items-center justify-center py-12 text-white/40 text-sm gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" /> Ładowanie…
            </div>
          )}
          {!loading && rows.length === 0 && (
            <div className="flex items-center justify-center py-16 text-white/30 text-sm">
              Brak operacji spełniających kryteria
            </div>
          )}
          {!loading && rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left px-4 py-3 text-xs text-white/40 uppercase tracking-wide font-medium whitespace-nowrap">Data</th>
                    <th className="text-left px-4 py-3 text-xs text-white/40 uppercase tracking-wide font-medium whitespace-nowrap">Konto</th>
                    <th className="text-left px-4 py-3 text-xs text-white/40 uppercase tracking-wide font-medium">Instrument</th>
                    <th className="text-center px-4 py-3 text-xs text-white/40 uppercase tracking-wide font-medium">Typ</th>
                    <th className="text-right px-4 py-3 text-xs text-white/40 uppercase tracking-wide font-medium whitespace-nowrap">Ilość</th>
                    <th className="text-right px-4 py-3 text-xs text-white/40 uppercase tracking-wide font-medium whitespace-nowrap">Cena&nbsp;({viewCcy})</th>
                    <th className="text-right px-4 py-3 text-xs text-white/40 uppercase tracking-wide font-medium whitespace-nowrap">Wartość&nbsp;({viewCcy})</th>
                    <th className="px-4 py-3 w-8" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const isDirty = !!dirty[row.id]
                    const editingQty   = editingCell?.rowId === row.id && editingCell.field === 'quantity'
                    const editingPrice = editingCell?.rowId === row.id && editingCell.field === 'price'
                    return (
                      <tr
                        key={row.id}
                        className={`border-b border-white/5 transition-colors ${
                          isDirty ? 'bg-amber-500/5 hover:bg-amber-500/10' : 'hover:bg-white/[0.02]'
                        }`}
                      >
                        <td className="px-4 py-2.5 whitespace-nowrap text-white/50 text-xs font-mono">{row.tradeAt}</td>
                        <td className="px-4 py-2.5 whitespace-nowrap text-white/40 text-xs">{row.accountName}</td>
                        <td className="px-4 py-2.5">
                          <span className="font-medium text-white">{row.symbol}</span>
                          {row.instrumentName && (
                            <span className="text-white/30 text-xs ml-1.5">— {row.instrumentName}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-center"><KindChip kind={row.kind} /></td>

                        {/* Quantity — click to edit */}
                        <td className="px-4 py-2.5 text-right tabular-nums">
                          {editingQty ? (
                            <input type="number" step="0.0001" value={editValue} autoFocus
                              onChange={(e) => setEditValue(e.target.value)}
                              onBlur={commitEdit}
                              onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditingCell(null) }}
                              className="w-24 bg-slate-900/80 border border-blue-500/60 rounded-lg px-2 py-0.5 text-sm text-right text-white focus:outline-none"
                            />
                          ) : (
                            <span className="text-white/70 cursor-pointer hover:text-blue-300 transition-colors" title="Kliknij aby edytować"
                              onClick={() => startEdit(row.id, 'quantity')}>
                              {fmtNum(row.quantity, 4)}
                            </span>
                          )}
                        </td>

                        {/* Price */}
                        <td className="px-4 py-2.5 text-right tabular-nums">
                          {editingPrice ? (
                            <input type="number" step="0.01" value={editValue} autoFocus
                              onChange={(e) => setEditValue(e.target.value)}
                              onBlur={commitEdit}
                              onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditingCell(null) }}
                              className="w-28 bg-slate-900/80 border border-blue-500/60 rounded-lg px-2 py-0.5 text-sm text-right text-white focus:outline-none"
                            />
                          ) : (
                            <span className="text-white/70 cursor-pointer hover:text-blue-300 transition-colors"
                              title={`Oryg. waluta: ${row.currency} · kliknij aby edytować`}
                              onClick={() => startEdit(row.id, 'price')}>
                              {fmtNum(row.priceView, 2)}
                              {row.currency !== viewCcy && (
                                <span className="text-white/20 text-xs ml-1">{row.currency}</span>
                              )}
                            </span>
                          )}
                        </td>

                        <td className="px-4 py-2.5 text-right tabular-nums text-white/60">{row.notionalFmt}</td>

                        <td className="px-4 py-2.5 text-center">
                          <button onClick={() => setDeleteTarget(row.id)}
                            className="p-1 rounded-md hover:bg-red-500/10 text-white/20 hover:text-red-400 transition-colors"
                            title="Usuń operację">
                            <Trash2 size={13} />
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

        {/* Pagination */}
        <div className="flex items-center justify-center gap-4 text-sm">
          <select value={pageSize} onChange={(e) => handleSizeChange(Number(e.target.value))}
            className="bg-slate-800/60 border border-white/10 rounded-lg px-2 py-1.5 text-white/60 text-xs">
            {PAGE_SIZES.map((s) => <option key={s} value={s}>{s} / stronę</option>)}
          </select>
          <span className="text-white/30 text-xs tabular-nums">
            Strona {page} / {totalPages}&nbsp;({data.total} wierszy)
          </span>
          <button onClick={() => handlePageChange(page - 1)} disabled={page <= 1 || loading}
            className="p-1.5 rounded-lg hover:bg-white/5 text-white/40 hover:text-white disabled:opacity-20 transition-colors">
            <ChevronLeft size={16} />
          </button>
          <button onClick={() => handlePageChange(page + 1)} disabled={page >= totalPages || loading}
            className="p-1.5 rounded-lg hover:bg-white/5 text-white/40 hover:text-white disabled:opacity-20 transition-colors">
            <ChevronRight size={16} />
          </button>
        </div>

      </div>

      {/* Delete confirm modal */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="bg-slate-900 border border-white/10 rounded-xl p-6 w-full max-w-sm mx-4 space-y-4 shadow-2xl">
            <h3 className="font-semibold text-white text-lg">Usunąć operację?</h3>
            <p className="text-white/40 text-sm leading-relaxed">
              Ta czynność ma wpływ na stan posiadania. Pamiętaj aby usunąć powiązaną transakcję.
            </p>
            <div className="flex justify-end gap-2 pt-1">
              <button onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 rounded-lg text-xs font-medium text-white/50 hover:text-white transition-colors">
                Anuluj
              </button>
              <button onClick={() => handleDelete(deleteTarget)}
                className="px-4 py-2 rounded-lg text-xs font-medium bg-red-600 hover:bg-red-500 text-white transition-colors">
                Usuń
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-5 right-5 px-4 py-2.5 rounded-xl text-sm font-medium shadow-2xl z-50 border ${
          toast.type === 'ok'
            ? 'bg-emerald-900/80 border-emerald-500/30 text-emerald-300'
            : 'bg-red-900/80 border-red-500/30 text-red-300'
        }`}>
          {toast.msg}
        </div>
      )}

      {/* Add brokerage event dialog */}
      <TransactionsDialog
        open={dialogOpen}
        onOpenChange={(o) => {
          setDialogOpen(o)
          if (!o) void loadPage()
        }}
        accounts={[]}
        brokerageAccounts={brokerageAccounts.map<TransactionBrokerageAccountOpt>((a) => ({
          id: a.id,
          name: a.name,
          walletName: a.walletName ?? '',
        }))}
        initialTab="brokerage"
      />
    </div>
  )
}
