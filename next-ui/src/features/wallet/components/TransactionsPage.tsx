'use client'

import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, ChevronsRight, Loader2, Minus, Plus, Save, Search, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DateTimePicker } from '@/components/ui/date-time-picker'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { TransactionsDialog } from '@/features/wallet/components/TransactionsDialog'
import type { TransactionAccountOpt, TransactionBrokerageAccountOpt } from '@/features/wallet/components/TransactionsDialog'
import type { TransactionItemOut, TransactionPageOut } from '@/lib/api/wallet'

const CATEGORY_MAP: Record<string, string> = {
  FOOD: 'Żywność',
  FUEL: 'Paliwo',
  ENTERTAINMENT: 'Rozrywka',
  CAR: 'Samochód',
  HOME: 'Mieszkanie',
  BILLS: 'Rachunki',
  HEALTH: 'Zdrowie',
  CLOTHES: 'Ubrania',
  EDUCATION: 'Edukacja',
  TRAVEL: 'Podróże',
  SUBSCRIPTIONS: 'Subskrypcje',
  GIFTS: 'Prezenty',
  CHILDREN: 'Dzieci',
  SPORT: 'Sport',
  INVESTMENTS: 'Inwestycje',
  ZUS_TAXES: 'ZUS i podatki',
  MEDICINES: 'Lekarstwa',
  PHONE: 'Telefony',
  BEAUTY: 'Uroda',
  INTEREST: 'Odsetki',
  ANIMALS: 'Zwierzęta',
  OTHER: 'Inne',
}

const STATUS_MAP: Record<string, string> = {
  INCOME: 'Przychód',
  EXPENSE: 'Wydatek',
  INTERNAL: 'Wewnętrzny',
  TAXES: 'Podatki',
}

const STATUS_BADGE: Record<string, string> = {
  INCOME: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  EXPENSE: 'bg-red-500/20 text-red-300 border-red-500/30',
  INTERNAL: 'bg-sky-500/20 text-sky-300 border-sky-500/30',
  TAXES: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
}

const CATEGORY_BADGE: Record<string, string> = {
  FOOD: 'bg-orange-500/20 text-orange-300',
  FUEL: 'bg-yellow-500/20 text-yellow-300',
  ENTERTAINMENT: 'bg-purple-500/20 text-purple-300',
  CAR: 'bg-blue-500/20 text-blue-300',
  HOME: 'bg-teal-500/20 text-teal-300',
  BILLS: 'bg-red-500/20 text-red-300',
  HEALTH: 'bg-rose-500/20 text-rose-300',
  CLOTHES: 'bg-pink-500/20 text-pink-300',
  EDUCATION: 'bg-cyan-500/20 text-cyan-300',
  TRAVEL: 'bg-indigo-500/20 text-indigo-300',
  SUBSCRIPTIONS: 'bg-slate-500/20 text-slate-300',
  GIFTS: 'bg-fuchsia-500/20 text-fuchsia-300',
  CHILDREN: 'bg-sky-500/20 text-sky-300',
  SPORT: 'bg-green-500/20 text-green-300',
  INVESTMENTS: 'bg-lime-500/20 text-lime-300',
  ZUS_TAXES: 'bg-amber-500/20 text-amber-300',
  MEDICINES: 'bg-red-500/20 text-red-300',
  PHONE: 'bg-violet-500/20 text-violet-300',
  BEAUTY: 'bg-pink-500/20 text-pink-300',
  OTHER: 'bg-gray-500/20 text-gray-300',
}

type DateRange = 'ALL' | '1M' | '3M' | '1Y' | 'CUSTOM'

export type SortField = 'date' | 'account' | 'category' | 'status'
export type SortDir = 'asc' | 'desc'

export type TxRow = {
  id: string
  dateFmt: string
  dateRaw: string
  description: string
  accountName: string
  accountId: string
  category: string | null
  status: string | null
  amount: string
  balanceBefore: string
  balanceAfter: string
  ccy: string
}

function SortIcon({ field, current, dir }: { field: SortField; current: SortField | null; dir: SortDir }) {
  if (field !== current) return <Minus className="w-3 h-3 text-white/20" />
  return dir === 'asc'
    ? <ChevronUp className="w-3 h-3 text-blue-400" />
    : <ChevronDown className="w-3 h-3 text-blue-400" />
}

function ThSortButton({ label, field, sort, dir, onSort }: {
  label: string; field: SortField; sort: SortField | null; dir: SortDir; onSort: (f: SortField) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onSort(field)}
      aria-label={`Sortuj po: ${label}`}
      className="flex items-center gap-1 text-xs text-white/40 font-medium hover:text-white/70 transition-colors whitespace-nowrap"
    >
      {label}
      <SortIcon field={field} current={sort} dir={dir} />
    </button>
  )
}

type TxPatch = {
  description?: string
  category?: string | null
  status?: string | null
}

type EditableTxField = keyof TxPatch

function fmtAmount(value: number | string): string {
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (Number.isNaN(n)) return String(value)
  return n.toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function itemToRow(item: TransactionItemOut): TxRow {
  const date = new Date(item.date_transaction)
  const dateFmt = Number.isNaN(date.getTime())
    ? item.date_transaction
    : new Intl.DateTimeFormat('pl-PL', { dateStyle: 'short', timeStyle: 'short' }).format(date)

  return {
    id: item.id,
    dateFmt,
    dateRaw: item.date_transaction,
    description: item.description,
    accountName: item.account_name,
    accountId: item.account_id,
    category: item.category,
    status: item.status,
    amount: String(item.amount),
    balanceBefore: String(item.balance_before),
    balanceAfter: String(item.balance_after),
    ccy: item.ccy,
  }
}

function getDateRange(range: DateRange): { from?: string; to?: string } {
  const today = new Date()
  const fmt = (d: Date) => d.toISOString().slice(0, 10)

  if (range === '1M') {
    const from = new Date(today)
    from.setMonth(from.getMonth() - 1)
    return { from: fmt(from), to: fmt(today) }
  }
  if (range === '3M') {
    const from = new Date(today)
    from.setMonth(from.getMonth() - 3)
    return { from: fmt(from), to: fmt(today) }
  }
  if (range === '1Y') {
    const from = new Date(today)
    from.setFullYear(from.getFullYear() - 1)
    return { from: fmt(from), to: fmt(today) }
  }
  return {}
}

async function apiFetch<T>(url: string, init?: RequestInit): Promise<{ ok: boolean; data: T | null; error?: string }> {
  const res = await fetch(url, init)
  let data: unknown = null
  try { data = await res.json() } catch { /* empty body */ }
  if (!res.ok) {
    const error =
      data && typeof data === 'object' && 'error' in data && typeof data.error === 'string'
        ? data.error : 'Wystąpił błąd'
    return { ok: false, data: null, error }
  }
  return { ok: true, data: data as T }
}

function MultiSelectFilter<T extends string>({
  label,
  options,
  selected,
  onChange,
  renderLabel,
  wide = false,
}: {
  label: string
  options: T[]
  selected: T[]
  onChange: (next: T[]) => void
  renderLabel?: (key: T) => string
  wide?: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const toggle = (key: T) => {
    onChange(selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key])
  }

  const first = selected[0]
  const label_ = selected.length === 0
    ? label
    : selected.length === 1 && first !== undefined
    ? (renderLabel ? renderLabel(first) : first)
    : `${label} (${selected.length})`

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={[
          'flex items-center gap-1.5 h-8 px-3 rounded-lg border text-sm transition-colors',
          wide ? 'min-w-[96px] justify-between' : '',
          open || selected.length > 0
            ? 'bg-emerald-600/20 border-emerald-500/30 text-white'
            : 'bg-slate-800/60 border-white/10 text-white/60 hover:text-white hover:border-white/20',
        ].join(' ')}
      >
        {label_}
        <svg className="w-3 h-3 opacity-50" viewBox="0 0 10 6" fill="none">
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {open && (
        <div className={[
          'fm-menu-scrollbar absolute top-full left-0 mt-1 z-50 max-h-64 overflow-y-auto rounded-xl border border-white/10 bg-slate-900 py-1 shadow-2xl',
          wide ? 'min-w-[240px] max-w-[calc(100vw-2rem)]' : 'min-w-[180px]',
        ].join(' ')}>
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => toggle(opt)}
              className="w-full text-left flex items-center gap-2 px-3 py-2 text-sm hover:bg-white/5 focus:bg-white/5 transition-colors"
            >
              <span className={[
                'w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center',
                selected.includes(opt)
                  ? 'bg-emerald-500 border-emerald-500 text-white'
                  : 'border-white/20',
              ].join(' ')}>
                {selected.includes(opt) && (
                  <svg viewBox="0 0 12 10" fill="none" className="w-3 h-3">
                    <path d="M1.5 5l3 3 6-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </span>
              <span className="text-white/80">{renderLabel ? renderLabel(opt) : opt}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

type Props = {
  accounts: TransactionAccountOpt[]
  brokerageAccounts: TransactionBrokerageAccountOpt[]
}

export function TransactionsPage({ accounts, brokerageAccounts }: Props) {
  // Filters
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([])
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([])
  const [dateRange, setDateRange] = useState<DateRange>('ALL')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(40)

  const [rows, setRows] = useState<TxRow[]>([])
  const [originals, setOriginals] = useState<Map<string, TxRow>>(new Map())
  const [totalRows, setTotalRows] = useState(0)
  const [sumByCcy, setSumByCcy] = useState<Record<string, number>>({})
  const [pageSumByCcy, setPageSumByCcy] = useState<Record<string, number>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [loadError, setLoadError] = useState<string>()

  const [dialogOpen, setDialogOpen] = useState(false)

  const [sortField, setSortField] = useState<SortField | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const [editCell, setEditCell] = useState<{ id: string; field: EditableTxField } | null>(null)
  const [dirty, setDirty] = useState<Map<string, TxPatch>>(new Map())
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [isSaving, startSave] = useTransition()
  const [isDeleting, startDelete] = useTransition()

  const allAccountIds = useMemo(() => accounts.map((a) => a.id), [accounts])
  const allCategoryKeys = Object.keys(CATEGORY_MAP) as string[]
  const allStatusKeys = Object.keys(STATUS_MAP) as string[]

  const sortedRows = rows

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
    setPage(1)
  }

  const load = useCallback(async () => {
    setIsLoading(true)
    setLoadError(undefined)
    setEditCell(null)
    setDeletingId(null)

    const qs = new URLSearchParams()
    qs.set('page', String(page))
    qs.set('size', String(size))
    if (selectedAccountIds.length) selectedAccountIds.forEach((id) => qs.append('account_id', id))
    if (selectedCategories.length) selectedCategories.forEach((c) => qs.append('category', c))
    if (selectedStatuses.length) selectedStatuses.forEach((s) => qs.append('status', s))
    if (q.trim()) qs.set('q', q.trim())
    if (sortField) qs.set('sort_by', sortField)
    if (sortField) qs.set('sort_dir', sortDir)

    const dates = dateRange === 'CUSTOM'
      ? { from: customFrom ? customFrom.slice(0, 10) : undefined, to: customTo ? customTo.slice(0, 10) : undefined }
      : getDateRange(dateRange)
    if (dates.from) qs.set('date_from', dates.from)
    if (dates.to) qs.set('date_to', dates.to)

    const { ok, data, error } = await apiFetch<TransactionPageOut>(`/api/wallet/transactions?${qs}`)
    setIsLoading(false)

    if (!ok || !data) {
      setLoadError(error ?? 'Nie udało się pobrać transakcji')
      return
    }

    const newRows = data.items.map(itemToRow)
    const newOriginals = new Map(newRows.map((r) => [r.id, { ...r }]))
    setRows(newRows)
    setOriginals(newOriginals)
    setDirty(new Map())
    setTotalRows(data.total)
    setSumByCcy(data.sum_by_ccy)

    const ps: Record<string, number> = {}
    for (const row of newRows) {
      const val = parseFloat(row.amount)
      if (!Number.isNaN(val)) {
        ps[row.ccy] = (ps[row.ccy] ?? 0) + val
      }
    }
    setPageSumByCcy(ps)
  }, [page, size, selectedAccountIds, selectedCategories, selectedStatuses, dateRange, customFrom, customTo, q, sortField, sortDir])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load()
    }, 0)

    return () => window.clearTimeout(timer)
  }, [load])

  function patchRow(id: string, field: EditableTxField, value: string | null) {
    setRows((prev) => prev.map((r) => r.id === id ? { ...r, [field]: value } : r))

    const orig = originals.get(id)
    if (!orig) return

    const backendField = field

    const isOriginalValue = value === (orig[field] as string | null)

    setDirty((prev) => {
      const next = new Map(prev)
      const patch = { ...(next.get(id) ?? {}) }
      if (isOriginalValue) {
        delete patch[backendField]
      } else {
        patch[backendField] = value as string
      }
      if (Object.keys(patch).length === 0) next.delete(id)
      else next.set(id, patch)
      return next
    })
  }

  function openEdit(id: string, field: EditableTxField) {
    setEditCell({ id, field })
  }

  function closeEdit() {
    setEditCell(null)
  }

  function handleSave() {
    if (dirty.size === 0) return

    const items = Array.from(dirty.entries()).map(([id, patch]) => ({ id, ...patch }))

    startSave(async () => {
      const { ok, error } = await apiFetch<{ updated: number }>('/api/wallet/transactions', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      })

      if (!ok) {
        toast.error(error ?? 'Nie udało się zapisać zmian')
        return
      }

      toast.success(`Zapisano zmiany (${items.length})`)
      void load()
    })
  }

  function confirmDelete(id: string) {
    setDeletingId(id)
  }

  function cancelDelete() {
    setDeletingId(null)
  }

  function handleDelete(id: string) {
    startDelete(async () => {
      const { ok, error } = await apiFetch<{ success: boolean }>(`/api/wallet/transactions/${id}`, { method: 'DELETE' })
      if (!ok) {
        toast.error(error ?? 'Nie udało się usunąć transakcji')
        setDeletingId(null)
        return
      }
      toast.success('Transakcja usunięta')
      void load()
    })
  }

  const totalPages = Math.max(1, Math.ceil(totalRows / size))

  function goPage(next: number) {
    setPage(Math.max(1, Math.min(next, totalPages)))
  }

  // When filter changes, reset to page 1
  function applyFilter<T>(setter: (v: T) => void): (v: T) => void {
    return (v: T) => { setter(v); setPage(1) }
  }

  const dirtyCount = dirty.size
  const hasDirty = dirtyCount > 0

  return (
    <div className="px-4 py-4 max-w-screen-2xl mx-auto">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-white">Transakcje</h1>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Page sum pills */}
          {Object.entries(pageSumByCcy).map(([ccy, val]) => (
            <span
              key={ccy}
              className={[
                'px-3 py-1 rounded-full text-sm font-medium border',
                val >= 0
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                  : 'bg-red-500/10 text-red-300 border-red-500/20',
              ].join(' ')}
            >
              {val >= 0 ? '+' : ''}{fmtAmount(val)} {ccy}
            </span>
          ))}

          {/* All-pages sum (if different from page sum) */}
          {Object.keys(sumByCcy).some((ccy) => {
            const pageVal = pageSumByCcy[ccy] ?? 0
            return Math.abs((sumByCcy[ccy] ?? 0) - pageVal) > 0.005
          }) && (
            <span className="text-white/40 text-xs">
              Suma wszystkich:{' '}
              {Object.entries(sumByCcy).map(([ccy, val]) => (
                `${fmtAmount(val)} ${ccy}`
              )).join(' | ')}
            </span>
          )}

          <Button
            size="sm"
            onClick={() => setDialogOpen(true)}
            className="bg-slate-700 hover:bg-slate-600 text-white gap-1.5 h-8"
          >
            <Plus className="w-3.5 h-3.5" />
            Dodaj transakcję
          </Button>

          <Button
            size="sm"
            disabled={!hasDirty || isSaving}
            onClick={handleSave}
            className="bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40 gap-1.5 h-8"
          >
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {hasDirty ? `Zapisz (${dirtyCount})` : 'Zapisz'}
          </Button>
        </div>
      </div>

      {/* ── Filter bar ── */}
      <div className="bg-slate-800/40 border border-white/10 rounded-xl p-3 mb-4 flex flex-wrap gap-2 items-center">

        {/* Account filter */}
        <MultiSelectFilter
          label="Konta"
          options={allAccountIds}
          selected={selectedAccountIds}
          onChange={applyFilter(setSelectedAccountIds)}
          wide
          renderLabel={(id) => {
            const acc = accounts.find((a) => a.id === id)
            return acc ? `${acc.walletName} · ${acc.name}` : id
          }}
        />

        {/* Category filter */}
        <MultiSelectFilter
          label="Kategorie"
          options={allCategoryKeys}
          selected={selectedCategories}
          onChange={applyFilter(setSelectedCategories)}
          renderLabel={(k) => CATEGORY_MAP[k] ?? k}
        />

        {/* Status filter */}
        <MultiSelectFilter
          label="Status"
          options={allStatusKeys}
          selected={selectedStatuses}
          onChange={applyFilter(setSelectedStatuses)}
          renderLabel={(k) => STATUS_MAP[k] ?? k}
        />

        {/* Date range */}
        <div className="flex items-center gap-1 ml-auto">
          {(['ALL', '1M', '3M', '1Y', 'CUSTOM'] as DateRange[]).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => { applyFilter(setDateRange)(r) }}
              className={[
                'h-8 px-3 rounded-lg text-xs font-medium transition-colors border',
                dateRange === r
                  ? 'bg-emerald-600/20 border-emerald-500/30 text-white'
                  : 'bg-transparent border-white/10 text-white/50 hover:text-white hover:border-white/20',
              ].join(' ')}
            >
              {r === 'ALL' ? 'Wszystkie' : r === 'CUSTOM' ? 'Zakres' : r}
            </button>
          ))}
        </div>

        {/* Custom date inputs */}
        {dateRange === 'CUSTOM' && (
          <div className="flex justify-center items-center gap-2 w-full pt-1">
            <DateTimePicker
              value={customFrom}
              onChange={(v) => { setCustomFrom(v); setPage(1) }}
              placeholder="Od daty"
              className="w-36"
            />
            <span className="text-white/30 text-xs">–</span>
            <DateTimePicker
              value={customTo}
              onChange={(v) => { setCustomTo(v); setPage(1) }}
              placeholder="Do daty"
              className="w-36"
            />
          </div>
        )}

        {/* Search */}
        <div className="flex items-center gap-1.5 ml-auto bg-slate-800/60 border border-white/10 rounded-lg px-2 h-8">
          <Search className="w-3.5 h-3.5 text-white/40 flex-shrink-0" />
          <input
            type="text"
            value={q}
            onChange={(e) => { setQ(e.target.value); setPage(1) }}
            placeholder="Szukaj…"
            className="bg-transparent text-white text-sm outline-none placeholder:text-white/30 w-36"
          />
        </div>
      </div>

      {/* ── Table ── */}
      {loadError ? (
        <div className="bg-red-900/20 border border-red-500/30 rounded-xl p-4 text-red-300 text-sm">{loadError}</div>
      ) : isLoading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 text-white/30 animate-spin" />
        </div>
      ) : rows.length === 0 ? (
        <div className="bg-slate-800/40 border border-white/10 rounded-xl p-8 text-center">
          <p className="text-white/40 text-sm">Brak transakcji spełniających kryteria</p>
        </div>
      ) : (
        <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden overflow-x-auto">
          <table className="w-full text-sm min-w-[860px]">
            <thead>
              <tr className="border-b border-white/10 bg-slate-800/60">
                <th className="text-left px-3 py-2 whitespace-nowrap w-[130px]">
                  <ThSortButton label="Data" field="date" sort={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="text-left px-3 py-2 text-xs text-white/40 font-medium">Opis</th>
                <th className="text-left px-3 py-2 whitespace-nowrap w-[150px]">
                  <ThSortButton label="Konto" field="account" sort={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="text-center px-2 py-2 whitespace-nowrap w-[130px]">
                  <ThSortButton label="Kategoria" field="category" sort={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="text-center px-2 py-2 whitespace-nowrap w-[100px]">
                  <ThSortButton label="Status" field="status" sort={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="text-right px-3 py-2 text-xs text-white/40 font-medium whitespace-nowrap w-[110px]">Kwota</th>
                <th className="text-right px-3 py-2 text-xs text-white/40 font-medium whitespace-nowrap w-[110px]">Saldo przed</th>
                <th className="text-right px-3 py-2 text-xs text-white/40 font-medium whitespace-nowrap w-[110px]">Saldo po</th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row, i) => {
                const isDirty = dirty.has(row.id)
                const isDeleting_ = deletingId === row.id
                const amt = parseFloat(row.amount)
                const amtColor = Number.isNaN(amt) ? '' : amt >= 0 ? 'text-emerald-300' : 'text-red-300'

                return (
                  <tr
                    key={row.id}
                    className={[
                      'border-b border-white/5 last:border-0',
                      i % 2 !== 0 ? 'bg-white/[0.015]' : '',
                      isDirty ? 'bg-amber-500/5' : '',
                    ].join(' ')}
                  >
                    {/* Date */}
                    <td className="px-3 py-1.5 text-white/50 text-xs whitespace-nowrap align-middle">
                      {row.dateFmt}
                    </td>

                    {/* Description — click to edit */}
                    <td className="px-3 py-1.5 align-middle max-w-[300px]">
                      {isDeleting_ ? (
                        <span className="text-red-400 text-xs">Czy na pewno usunąć?</span>
                      ) : editCell?.id === row.id && editCell.field === 'description' ? (
                        <input
                          autoFocus
                          type="text"
                          value={row.description}
                          onChange={(e) => patchRow(row.id, 'description', e.target.value)}
                          onBlur={closeEdit}
                          onKeyDown={(e) => { if (e.key === 'Enter') closeEdit() }}
                          className="w-full bg-slate-700/60 border border-white/20 rounded px-2 py-0.5 text-sm text-white outline-none"
                        />
                      ) : (
                        <span
                          onClick={() => openEdit(row.id, 'description')}
                          className="cursor-text text-white/80 break-words block hover:text-white transition-colors"
                        >
                          {row.description || <span className="text-white/20 italic">—</span>}
                        </span>
                      )}
                    </td>

                    {/* Account */}
                    <td className="px-3 py-1.5 text-white/50 text-xs whitespace-nowrap align-middle">
                      {row.accountName}
                    </td>

                    {/* Category — click to edit */}
                    <td className="px-2 py-1.5 text-center align-middle">
                      {editCell?.id === row.id && editCell.field === 'category' ? (
                        <Select
                          value={row.category ?? '__none__'}
                          onValueChange={(v) => {
                            patchRow(row.id, 'category', v === '__none__' ? null : v)
                            closeEdit()
                          }}
                          open
                          onOpenChange={(o) => { if (!o) closeEdit() }}
                        >
                          <SelectTrigger className="h-7 bg-slate-700 border-white/20 text-white text-xs w-[120px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-slate-900 border-white/10 text-white text-xs">
                            <SelectItem value="__none__">—</SelectItem>
                            {allCategoryKeys.map((k) => (
                              <SelectItem key={k} value={k}>{CATEGORY_MAP[k]}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <span
                          onClick={() => openEdit(row.id, 'category')}
                          className={[
                            'cursor-pointer inline-block px-2 py-0.5 rounded text-xs font-medium transition-opacity hover:opacity-80',
                            row.category ? (CATEGORY_BADGE[row.category] ?? 'bg-gray-500/20 text-gray-300') : 'text-white/25',
                          ].join(' ')}
                        >
                          {row.category ? (CATEGORY_MAP[row.category] ?? row.category) : '—'}
                        </span>
                      )}
                    </td>

                    {/* Status — click to edit */}
                    <td className="px-2 py-1.5 text-center align-middle">
                      {editCell?.id === row.id && editCell.field === 'status' ? (
                        <Select
                          value={row.status ?? '__none__'}
                          onValueChange={(v) => {
                            patchRow(row.id, 'status', v === '__none__' ? null : v)
                            closeEdit()
                          }}
                          open
                          onOpenChange={(o) => { if (!o) closeEdit() }}
                        >
                          <SelectTrigger className="h-7 bg-slate-700 border-white/20 text-white text-xs w-[110px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-slate-900 border-white/10 text-white text-xs">
                            <SelectItem value="__none__">—</SelectItem>
                            {allStatusKeys.map((k) => (
                              <SelectItem key={k} value={k}>{STATUS_MAP[k]}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <span
                          onClick={() => openEdit(row.id, 'status')}
                          className={[
                            'cursor-pointer inline-block px-2 py-0.5 rounded text-xs font-medium border transition-opacity hover:opacity-80',
                            row.status
                              ? (STATUS_BADGE[row.status] ?? 'bg-gray-500/20 text-gray-300 border-gray-500/30')
                              : 'text-white/25 border-transparent',
                          ].join(' ')}
                        >
                          {row.status ? (STATUS_MAP[row.status] ?? row.status) : '—'}
                        </span>
                      )}
                    </td>

                    {/* Amount */}
                    <td className="px-3 py-1.5 text-right align-middle">
                      <span className={`font-mono text-xs ${amtColor}`}>
                        {fmtAmount(row.amount)} <span className="text-white/30">{row.ccy}</span>
                      </span>
                    </td>

                    {/* Balance before */}
                    <td className="px-3 py-1.5 text-right align-middle">
                      <span className="font-mono text-xs text-white/50">
                        {fmtAmount(row.balanceBefore)}
                      </span>
                    </td>

                    {/* Balance after */}
                    <td className="px-3 py-1.5 text-right align-middle">
                      <span className="font-mono text-xs text-white/50">
                        {fmtAmount(row.balanceAfter)}
                      </span>
                    </td>

                    {/* Actions */}
                    <td className="px-2 py-1.5 align-middle">
                      {isDeleting_ ? (
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => handleDelete(row.id)}
                            disabled={isDeleting}
                            className="h-6 w-6 rounded flex items-center justify-center text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={cancelDelete}
                            className="h-6 w-6 rounded flex items-center justify-center text-white/40 hover:text-white hover:bg-white/10 transition-colors"
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => confirmDelete(row.id)}
                          className="h-6 w-6 rounded flex items-center justify-center text-white/20 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Pager ── */}
      {totalRows > 0 && (
        <div className="flex items-center justify-between mt-4 gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-white/40">Wierszy na stronę:</span>
            <Select value={String(size)} onValueChange={(v) => { setSize(Number(v)); setPage(1) }}>
              <SelectTrigger className="h-7 w-[70px] bg-slate-800 border-white/10 text-white text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-900 border-white/10 text-white">
                {[20, 40, 80, 120].map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-white/40">
              {totalRows} wierszy
            </span>
            <button
              type="button"
              onClick={() => goPage(page - 1)}
              disabled={page <= 1}
              aria-label="Poprzednia strona"
              className="h-7 w-7 rounded-lg flex items-center justify-center text-white/40 hover:text-white hover:bg-white/10 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-1 text-xs text-white/40">
              <span>Strona</span>
              <input
                key={page}
                type="text"
                inputMode="numeric"
                defaultValue={page}
                onFocus={(e) => e.target.select()}
                onBlur={(e) => {
                  const n = parseInt(e.target.value, 10)
                  goPage(!Number.isNaN(n) ? n : page)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const n = parseInt((e.target as HTMLInputElement).value, 10)
                    goPage(!Number.isNaN(n) ? n : page)
                  }
                }}
                aria-label="Numer strony"
                className="w-10 text-center bg-slate-800/60 border border-white/10 rounded px-1 py-0.5 text-xs text-white outline-none focus:border-white/30"
              />
              <span>/ {totalPages}</span>
            </div>
            <button
              type="button"
              onClick={() => goPage(page + 1)}
              disabled={page >= totalPages}
              aria-label="Następna strona"
              className="h-7 w-7 rounded-lg flex items-center justify-center text-white/40 hover:text-white hover:bg-white/10 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => goPage(totalPages)}
              disabled={page >= totalPages}
              aria-label="Ostatnia strona"
              className="h-7 w-7 rounded-lg flex items-center justify-center text-white/40 hover:text-white hover:bg-white/10 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronsRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <TransactionsDialog
        open={dialogOpen}
        onOpenChange={(o) => {
          setDialogOpen(o)
          if (!o) void load()
        }}
        accounts={accounts}
        brokerageAccounts={brokerageAccounts}
      />
    </div>
  )
}
