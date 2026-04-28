'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Search, RefreshCw, Plus, Trash2, Bell, BellOff,
  TrendingUp, TrendingDown, MoreVertical, X, AlertCircle,
  ChevronUp, ChevronDown as ChevdownIcon, Minus, FileText,
} from 'lucide-react'
import type { FavoriteItemRow } from '@/app/api/wallet/favorites/[id]/route'
import type { FavoriteList } from '@/lib/api/wallet'
import { PriceAlertModal, type PriceAlertModalData } from './PriceAlertModal'

type SortField = 'symbol' | 'changePct'
type SortDir = 'asc' | 'desc'

function sortRows(rows: FavoriteItemRow[], field: SortField, dir: SortDir): FavoriteItemRow[] {
  return [...rows].sort((a, b) => {
    if (field === 'symbol') {
      return dir === 'asc'
        ? a.symbol.localeCompare(b.symbol)
        : b.symbol.localeCompare(a.symbol)
    }

    const av = a.changePct ?? Number.NEGATIVE_INFINITY
    const bv = b.changePct ?? Number.NEGATIVE_INFINITY
    return dir === 'asc' ? av - bv : bv - av
  })
}

function SortIcon({ field, current, dir }: { field: SortField; current: SortField; dir: SortDir }) {
  if (field !== current) return <Minus className="w-3 h-3 text-white/20" />
  return dir === 'asc'
    ? <ChevronUp className="w-3 h-3 text-blue-400" />
    : <ChevdownIcon className="w-3 h-3 text-blue-400" />
}

function formatAlertSummary(alert: PriceAlertModalData): string {
  const parts: string[] = []
  if (alert.below_price) parts.push(`< ${alert.below_price}`)
  if (alert.above_price) parts.push(`> ${alert.above_price}`)
  return parts.join(' | ') || 'Alert'
}

function ThButton({
  label,
  field,
  sort,
  dir,
  onSort,
  className = 'text-left',
}: {
  label: string
  field: SortField
  sort: SortField
  dir: SortDir
  onSort: (field: SortField) => void
  className?: string
}) {
  return (
    <button
      onClick={() => onSort(field)}
      className={`flex items-center gap-1 text-xs text-white/40 uppercase tracking-wide hover:text-white/70 transition-colors ${className}`}
    >
      {label}
      <SortIcon field={field} current={sort} dir={dir} />
    </button>
  )
}

function AlertModal({
  symbol,
  name,
  initial,
  onClose,
  onSaved,
  onDeleted,
}: {
  symbol: string
  name: string
  initial: PriceAlertModalData | null
  onClose: () => void
  onSaved: () => void
  onDeleted: () => void
}) {
  return <PriceAlertModal symbol={symbol} name={name} initial={initial} onClose={onClose} onSaved={onSaved} onDeleted={onDeleted} />
}

function CreateListModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (list: FavoriteList) => void
}) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCreate = async () => {
    if (!name.trim()) { setError('Podaj nazwę'); return }
    setSaving(true)
    setError(null)
    try {
      const res = await fetch('/api/wallet/favorites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), description: desc.trim() || null }),
      })
      const json = await res.json() as FavoriteList & { error?: string }
      if (!res.ok) { setError(json.error ?? 'Błąd tworzenia'); return }
      onCreated(json)
    } catch {
      setError('Błąd połączenia')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-slate-900 border border-white/10 rounded-xl p-5 w-full max-w-sm mx-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-white">Nowa lista</h3>
          <button onClick={onClose} className="text-white/40 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        {error && <p className="text-xs text-red-400 mb-3">{error}</p>}
        <label className="text-xs text-white/50 block mb-3">
          Nazwa *
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full px-2.5 py-1.5 text-sm bg-slate-800 border border-white/10 rounded-lg text-white focus:outline-none focus:border-blue-500/50"
          />
        </label>
        <label className="text-xs text-white/50 block mb-4">
          Opis
          <input
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            className="mt-1 w-full px-2.5 py-1.5 text-sm bg-slate-800 border border-white/10 rounded-lg text-white focus:outline-none focus:border-blue-500/50"
          />
        </label>
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-xs text-white/50 hover:text-white transition-colors">Anuluj</button>
          <button onClick={handleCreate} disabled={saving} className="px-4 py-1.5 rounded-lg text-xs font-medium bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 transition-colors">
            {saving ? 'Tworzę…' : 'Utwórz'}
          </button>
        </div>
      </div>
    </div>
  )
}

type Props = {
  initialLists: FavoriteList[]
  initialListId: string | null
  initialItems: FavoriteItemRow[]
}

type ActionMenu = {
  symbol: string
  name: string
  mic: string
  alert: PriceAlertModalData | null
  x: number
  y: number
}

export function FavoritesPage({ initialLists, initialListId, initialItems }: Props) {
  const router = useRouter()
  const [lists, setLists] = useState<FavoriteList[]>(initialLists)
  const [selectedListId, setSelectedListId] = useState<string | null>(initialListId)
  const [items, setItems] = useState<FavoriteItemRow[]>(initialItems)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('symbol')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [alertModal, setAlertModal] = useState<{ symbol: string; name: string; alert: PriceAlertModalData | null } | null>(null)
  const [createListOpen, setCreateListOpen] = useState(false)
  const [deleteListConfirm, setDeleteListConfirm] = useState(false)
  const [actionMenu, setActionMenu] = useState<ActionMenu | null>(null)

  const menuRef = useRef<HTMLDivElement | null>(null)

  // Close action menu on outside click
  useEffect(() => {
    if (!actionMenu) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setActionMenu(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [actionMenu])

  const loadItems = useCallback(async (listId: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/wallet/favorites/${listId}`)
      if (!res.ok) { setError('Błąd pobierania danych'); return }
      const data = await res.json() as FavoriteItemRow[]
      setItems(data)
    } catch {
      setError('Błąd połączenia')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleListSelect = (id: string) => {
    setSelectedListId(id)
    loadItems(id)
  }

  const handleRemove = async (row: FavoriteItemRow) => {
    if (!selectedListId) return
    setActionMenu(null)
    const res = await fetch(`/api/wallet/favorites/${selectedListId}/items/${encodeURIComponent(row.symbol)}`, {
      method: 'DELETE',
    })
    if (res.ok && selectedListId) loadItems(selectedListId)
  }

  const handleDeleteList = async () => {
    if (!selectedListId) return
    setDeleteListConfirm(false)
    const res = await fetch(`/api/wallet/favorites/${selectedListId}`, { method: 'DELETE' })
    if (res.ok) {
      const newLists = lists.filter((l) => l.id !== selectedListId)
      setLists(newLists)
      const next = newLists[0] ?? null
      setSelectedListId(next?.id ?? null)
      setItems([])
      if (next) loadItems(next.id)
    }
  }

  const handleAlertSaved = () => {
    setAlertModal(null)
    if (selectedListId) loadItems(selectedListId)
  }

  const handleAlertDeleted = () => {
    setAlertModal(null)
    if (selectedListId) loadItems(selectedListId)
  }

  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortDir((current) => current === 'asc' ? 'desc' : 'asc')
      return
    }
    setSortField(field)
    setSortDir(field === 'changePct' ? 'desc' : 'asc')
  }

  const filtered = items.filter((it) => {
    if (!search) return true
    const s = search.toLowerCase()
    return it.symbol.toLowerCase().includes(s) || it.name.toLowerCase().includes(s)
  })
  const sorted = sortRows(filtered, sortField, sortDir)

  const selectedList = lists.find((l) => l.id === selectedListId)

  return (
    <div className="px-4 py-4">
      <div className="max-w-screen-2xl mx-auto">

        {/* Modals */}
        {alertModal && (
          <AlertModal
            symbol={alertModal.symbol}
            name={alertModal.name}
            initial={alertModal.alert}
            onClose={() => setAlertModal(null)}
            onSaved={handleAlertSaved}
            onDeleted={handleAlertDeleted}
          />
        )}
        {createListOpen && (
          <CreateListModal
            onClose={() => setCreateListOpen(false)}
            onCreated={(list) => {
              const newLists = [...lists, list]
              setLists(newLists)
              setSelectedListId(list.id)
              setItems([])
              setCreateListOpen(false)
            }}
          />
        )}
        {deleteListConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-slate-900 border border-white/10 rounded-xl p-5 w-full max-w-xs mx-4 shadow-xl">
              <h3 className="font-semibold text-white mb-1">Usuń listę?</h3>
              <p className="text-xs text-white/40 mb-4">„{selectedList?.name}&quot; zostanie trwale usunięta.</p>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setDeleteListConfirm(false)} className="px-3 py-1.5 text-xs text-white/50 hover:text-white transition-colors">Anuluj</button>
                <button onClick={handleDeleteList} className="px-4 py-1.5 rounded-lg text-xs font-medium bg-red-600 text-white hover:bg-red-500 transition-colors">Usuń</button>
              </div>
            </div>
          </div>
        )}

        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h1 className="text-xl font-semibold text-white">Ulubione &amp; Alerty</h1>
          <div className="flex items-center gap-2">
            <button onClick={() => setCreateListOpen(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-700/60 border border-white/10 text-white/60 hover:text-white transition-colors">
              <Plus className="w-3.5 h-3.5" /> Dodaj listę
            </button>
            {selectedListId && (
              <button onClick={() => setDeleteListConfirm(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-red-500/20 text-red-400/60 hover:text-red-300 hover:bg-red-500/5 transition-colors">
                <Trash2 className="w-3.5 h-3.5" /> Usuń listę
              </button>
            )}
          </div>
        </div>

        {/* List tabs */}
        {lists.length > 0 && (
          <div className="flex gap-1 mb-4 flex-wrap">
            {lists.map((lst) => (
              <button
                key={lst.id}
                onClick={() => handleListSelect(lst.id)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  selectedListId === lst.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-800/60 border border-white/10 text-white/50 hover:text-white'
                }`}
              >
                {lst.name}
              </button>
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-3 items-center mb-4">
          <div className="relative flex-1 min-w-[180px] max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/30" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Szukaj symbol / nazwa…"
              className="w-full pl-7 pr-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
            />
          </div>
          {selectedListId && (
            <button
              onClick={() => loadItems(selectedListId)}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-700/60 border border-white/10 text-white/60 hover:text-white disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Odśwież
            </button>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-sm flex justify-between">
            {error}
            <button onClick={() => setError(null)} className="text-white/30 hover:text-white/60 ml-3">×</button>
          </div>
        )}

        {/* Empty states */}
        {lists.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Bell className="w-8 h-8 text-white/20 mb-3" />
            <p className="text-white/40 text-sm">Brak list ulubionych.</p>
            <button onClick={() => setCreateListOpen(true)} className="mt-3 text-xs text-blue-400 hover:text-blue-300 underline">Utwórz pierwszą listę</button>
          </div>
        )}

        {lists.length > 0 && !selectedListId && (
          <p className="text-white/30 text-sm py-10 text-center">Wybierz listę.</p>
        )}

        {/* Table */}
        {selectedListId && (
          <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
            {loading && (
              <div className="flex items-center justify-center py-12 gap-2 text-white/40 text-sm">
                <RefreshCw className="w-4 h-4 animate-spin" /> Ładowanie…
              </div>
            )}

            {!loading && sorted.length === 0 && (
              <p className="text-center py-16 text-white/30 text-sm">Brak instrumentów na tej liście.</p>
            )}

            {!loading && sorted.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left px-4 py-3">
                        <ThButton
                          label="Symbol"
                          field="symbol"
                          sort={sortField}
                          dir={sortDir}
                          onSort={handleSort}
                        />
                      </th>
                      <th className="text-left px-4 py-3 text-xs text-white/40 uppercase tracking-wide hidden md:table-cell">Nazwa</th>
                      <th className="text-right px-4 py-3 text-xs text-white/40 uppercase tracking-wide">Kurs</th>
                      <th className="text-right px-4 py-3">
                        <ThButton
                          label="Zmiana %"
                          field="changePct"
                          sort={sortField}
                          dir={sortDir}
                          onSort={handleSort}
                          className="justify-end ml-auto"
                        />
                      </th>
                      <th className="text-right px-4 py-3 text-xs text-white/40 uppercase tracking-wide hidden sm:table-cell">Wolumen</th>
                      <th className="text-left px-4 py-3 text-xs text-white/40 uppercase tracking-wide hidden lg:table-cell">Ostatni handel</th>
                      <th className="text-center px-4 py-3 text-xs text-white/40 uppercase tracking-wide">Alert</th>
                      <th className="px-3 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((row) => {
                      const hasAlert = !!row.alert
                      const alertOn = hasAlert && row.alert!.enabled
                      const positive = (row.changePct ?? 0) >= 0

                      return (
                        <tr key={row.symbol} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02] transition-colors">
                          {/* Symbol */}
                          <td className="px-4 py-3">
                            <span className="font-semibold text-white">{row.symbol}</span>
                            <p className="text-xs text-white/30 mt-0.5">{row.mic}</p>
                          </td>

                          {/* Name */}
                          <td className="px-4 py-3 hidden md:table-cell">
                            <span className="text-xs text-white/60 line-clamp-1 max-w-xs">{row.name}</span>
                          </td>

                          {/* Price + change */}
                          <td className="px-4 py-3 text-right">
                            <span className="font-medium text-white tabular-nums">{row.price ?? '—'}</span>
                          </td>

                          {/* Change % */}
                          <td className="px-4 py-3 text-right">
                            {row.changePct !== null ? (
                              <div className={`inline-flex items-center justify-end gap-0.5 text-xs ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                                {positive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                                {row.changePctFmt ?? `${row.changePct >= 0 ? '+' : ''}${row.changePct.toFixed(2)}%`}
                              </div>
                            ) : (
                              <span className="text-white/20 text-xs">—</span>
                            )}
                          </td>

                          {/* Volume */}
                          <td className="px-4 py-3 text-right tabular-nums text-white/40 text-xs hidden sm:table-cell">
                            {row.volume != null ? row.volume.toLocaleString('pl-PL') : '—'}
                          </td>

                          {/* Last trade */}
                          <td className="px-4 py-3 hidden lg:table-cell">
                            {row.lastTradeDateFmt ? (
                              <div className="text-xs">
                                <span className="text-white/40">{row.lastTradeDateFmt}</span>
                                {row.lastTradeTimeFmt && <span className="text-blue-400 ml-1.5 font-medium">{row.lastTradeTimeFmt}</span>}
                              </div>
                            ) : (
                              <span className="text-white/20 text-xs">—</span>
                            )}
                          </td>

                          {/* Alert status */}
                          <td className="px-4 py-3 text-center">
                            {hasAlert ? (
                              <span
                                className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-medium ${
                                  alertOn
                                    ? 'bg-emerald-500/20 text-emerald-300'
                                    : 'bg-slate-700/60 text-white/40'
                                }`}
                                title={alertOn ? 'Alert aktywny' : 'Alert wyłączony'}
                              >
                                {alertOn ? <Bell className="w-3 h-3" /> : <BellOff className="w-3 h-3" />}
                                {formatAlertSummary(row.alert!)}
                              </span>
                            ) : (
                              <span className="text-xs text-white/20">Brak</span>
                            )}
                          </td>

                          {/* Actions */}
                          <td className="px-3 py-3 text-right relative">
                            <button
                              onClick={(e) => {
                                const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect()
                                setActionMenu({
                                  symbol: row.symbol,
                                  name: row.name,
                                  mic: row.mic,
                                  alert: row.alert,
                                  x: rect.left,
                                  y: rect.bottom,
                                })
                              }}
                              className="text-white/30 hover:text-white transition-colors p-1 rounded hover:bg-white/10"
                            >
                              <MoreVertical className="w-4 h-4" />
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
        )}

        {sorted.length > 0 && (
          <p className="text-xs text-white/25 mt-2 text-right">
            {sorted.length} instrument{sorted.length === 1 ? '' : 'ów'}
          </p>
        )}
      </div>

      {/* Action menu */}
      {actionMenu && (
        <div
          ref={menuRef}
          style={{ position: 'fixed', top: actionMenu.y + 4, left: Math.max(0, actionMenu.x - 160) }}
          className="z-50 bg-slate-900 border border-white/10 rounded-xl shadow-xl py-1 min-w-[180px]"
        >
          <button
            onClick={() => { setAlertModal({ symbol: actionMenu.symbol, name: actionMenu.name, alert: actionMenu.alert }); setActionMenu(null) }}
            className="w-full flex items-center gap-2 px-4 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
          >
            {actionMenu.alert ? (
              actionMenu.alert.enabled ? <Bell className="w-3.5 h-3.5" /> : <BellOff className="w-3.5 h-3.5" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5" />
            )}
            {actionMenu.alert ? 'Edytuj alert' : 'Dodaj alert'}
          </button>
          {actionMenu.mic !== 'STCM' && (
            <button
              onClick={() => {
                router.push(`/stock/${encodeURIComponent(actionMenu.mic)}/${encodeURIComponent(actionMenu.symbol)}/report`)
                setActionMenu(null)
              }}
              className="w-full flex items-center gap-2 px-4 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
            >
              <FileText className="w-3.5 h-3.5" />
              Raport AI
            </button>
          )}
          {actionMenu.alert && (
            <button
              onClick={async () => { await fetch(`/api/wallet/alerts/${encodeURIComponent(actionMenu.symbol)}`, { method: 'DELETE' }); setActionMenu(null); if (selectedListId) loadItems(selectedListId) }}
              className="w-full flex items-center gap-2 px-4 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
            >
              <BellOff className="w-3.5 h-3.5" />
              Usuń alert
            </button>
          )}
          <div className="border-t border-white/5 my-1" />
          <button
            onClick={() => handleRemove({ symbol: actionMenu.symbol, name: actionMenu.name, mic: '', price: null, changePct: null, changePctFmt: null, volume: null, lastTradeDateFmt: null, lastTradeTimeFmt: null, alert: actionMenu.alert })}
            className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-400/70 hover:text-red-300 hover:bg-red-500/5 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Usuń z listy
          </button>
        </div>
      )}
    </div>
  )
}
