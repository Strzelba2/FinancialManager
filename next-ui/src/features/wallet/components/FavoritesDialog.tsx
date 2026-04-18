'use client'

import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import { Star, Plus, Trash2, Bell, X, ChevronDown, ChevronUp, Check } from 'lucide-react'

type FavoriteList = {
  id: string
  name: string
  description?: string | null
}

type Alert = {
  id?: string
  below_price: string | null
  above_price: string | null
  enabled: boolean
  one_shot: boolean
  expires_at: string | null
}

type ListItem = {
  symbol: string
  name: string
  mic: string
  alert: Alert | null
}

type ListWithItems = {
  list: FavoriteList
  items: ListItem[]
}

function AlertDialog({
  symbol,
  name,
  initialAlert,
  onClose,
  onSaved,
}: {
  symbol: string
  name: string
  initialAlert: Alert | null
  onClose: () => void
  onSaved: () => void
}) {
  const [enabled, setEnabled] = useState(initialAlert?.enabled ?? true)
  const [oneShot, setOneShot] = useState(initialAlert?.one_shot ?? false)
  const [below, setBelow] = useState(initialAlert?.below_price ?? '')
  const [above, setAbove] = useState(initialAlert?.above_price ?? '')
  const [expiresAt, setExpiresAt] = useState(initialAlert?.expires_at ?? '')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function save() {
    const belowN = below.trim() ? Number(below.replace(',', '.')) : null
    const aboveN = above.trim() ? Number(above.replace(',', '.')) : null

    if (belowN === null && aboveN === null) {
      toast.warning('Podaj przynajmniej cenę poniżej lub powyżej')
      return
    }
    if (belowN !== null && belowN < 0) { toast.warning('Cena poniżej musi być >= 0'); return }
    if (aboveN !== null && aboveN < 0) { toast.warning('Cena powyżej musi być >= 0'); return }
    if (belowN !== null && aboveN !== null && belowN >= aboveN) {
      toast.warning('Cena poniżej musi być mniejsza od ceny powyżej')
      return
    }

    setSaving(true)
    try {
      const res = await fetch('/api/wallet/alerts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          below_price: below.trim() || null,
          above_price: above.trim() || null,
          enabled,
          one_shot: oneShot,
          expires_at: expiresAt.trim() || null,
        }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({})) as { error?: string }
        toast.error(d.error ?? 'Nie udało się zapisać alertu')
        return
      }
      toast.success('Alert zapisany')
      onSaved()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  async function deleteAlert() {
    setDeleting(true)
    try {
      const res = await fetch(`/api/wallet/alerts/${encodeURIComponent(symbol)}`, { method: 'DELETE' })
      if (!res.ok) { toast.error('Nie udało się usunąć alertu'); return }
      toast.success('Alert usunięty')
      onSaved()
      onClose()
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-slate-900 border border-white/10 rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <div>
          <h3 className="text-base font-semibold text-white">Alert cenowy</h3>
          <p className="text-xs text-white/40 mt-0.5">{symbol} — {name || '—'}</p>
        </div>

        <div className="border-t border-white/5" />

        {/* Enabled / one-shot toggles */}
        <div className="space-y-2">
          <label className="flex items-center gap-2.5 cursor-pointer">
            <button
              type="button"
              onClick={() => setEnabled((v) => !v)}
              className={`w-8 h-4.5 rounded-full border transition-colors relative ${
                enabled ? 'bg-blue-600 border-blue-500' : 'bg-slate-700 border-white/10'
              }`}
            >
              <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${
                enabled ? 'translate-x-4' : 'translate-x-0.5'
              }`} />
            </button>
            <span className="text-sm text-white/70">Aktywny</span>
          </label>
          <label className="flex items-center gap-2.5 cursor-pointer">
            <button
              type="button"
              onClick={() => setOneShot((v) => !v)}
              className={`w-8 h-4.5 rounded-full border transition-colors relative ${
                oneShot ? 'bg-blue-600 border-blue-500' : 'bg-slate-700 border-white/10'
              }`}
            >
              <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${
                oneShot ? 'translate-x-4' : 'translate-x-0.5'
              }`} />
            </button>
            <span className="text-sm text-white/70">Jednorazowy (wyłącz po wyzwoleniu)</span>
          </label>
        </div>

        {/* Price inputs */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-white/40 mb-1">Cena poniżej</label>
            <input
              value={below}
              onChange={(e) => setBelow(e.target.value)}
              placeholder="np. 100.00"
              className="w-full px-3 py-1.5 text-sm bg-slate-800/60 border border-white/10 rounded-lg text-white placeholder-white/20 focus:outline-none focus:border-blue-500/50"
            />
          </div>
          <div>
            <label className="block text-xs text-white/40 mb-1">Cena powyżej</label>
            <input
              value={above}
              onChange={(e) => setAbove(e.target.value)}
              placeholder="np. 120.00"
              className="w-full px-3 py-1.5 text-sm bg-slate-800/60 border border-white/10 rounded-lg text-white placeholder-white/20 focus:outline-none focus:border-blue-500/50"
            />
          </div>
        </div>

        {/* Expiry */}
        <div>
          <label className="block text-xs text-white/40 mb-1">Wygasa (opcjonalnie, ISO datetime)</label>
          <input
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            placeholder="np. 2025-12-31T23:59"
            className="w-full px-3 py-1.5 text-sm bg-slate-800/60 border border-white/10 rounded-lg text-white placeholder-white/20 focus:outline-none focus:border-blue-500/50"
          />
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between pt-1">
          <div>
            {initialAlert && (
              <button
                onClick={deleteAlert}
                disabled={deleting}
                className="text-xs px-3 py-1.5 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
              >
                {deleting ? 'Usuwanie…' : 'Usuń alert'}
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="text-xs px-3 py-1.5 rounded-lg text-white/50 hover:text-white transition-colors"
            >
              Anuluj
            </button>
            <button
              onClick={save}
              disabled={saving}
              className="text-xs px-4 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {saving ? 'Zapisywanie…' : 'Zapisz'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function ConfirmDeleteList({
  listName,
  onCancel,
  onConfirm,
}: {
  listName: string
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-slate-900 border border-white/10 rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-4">
        <h3 className="text-base font-semibold text-white">Usuń listę?</h3>
        <p className="text-sm text-white/50">Zostanie usunięta lista: <span className="text-white/80 font-medium">{listName}</span></p>
        <div className="border-t border-white/5" />
        <div className="flex items-center justify-end gap-2">
          <button onClick={onCancel} className="text-xs px-3 py-1.5 rounded-lg text-white/50 hover:text-white transition-colors">
            Anuluj
          </button>
          <button
            onClick={onConfirm}
            className="text-xs px-4 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
          >
            Usuń
          </button>
        </div>
      </div>
    </div>
  )
}

function AlertBadge({ alert }: { alert: Alert | null }) {
  if (!alert) {
    return <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/30">Brak alertu</span>
  }
  const parts: string[] = []
  if (alert.below_price) parts.push(`< ${alert.below_price}`)
  if (alert.above_price) parts.push(`> ${alert.above_price}`)
  const label = parts.join(' | ') || 'Alert'
  const suffix = alert.enabled ? ' (ON)' : ' (OFF)'
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
      alert.enabled
        ? 'bg-emerald-500/20 text-emerald-300'
        : 'bg-white/5 text-white/40'
    }`}>
      {label}{suffix}
    </span>
  )
}

type Props = {
  symbol: string
  name: string | null
  mic: string
  onClose: () => void
}

export function FavoritesDialog({ symbol, name, mic, onClose }: Props) {
  const [listsWithItems, setListsWithItems] = useState<ListWithItems[]>([])
  const [activeTab, setActiveTab] = useState<string | null>(null)
  const [loadingLists, setLoadingLists] = useState(true)

  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [creating, setCreating] = useState(false)

  const [alertTarget, setAlertTarget] = useState<{ symbol: string; alert: Alert | null } | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null)

  const refresh = useCallback(async () => {
    setLoadingLists(true)
    try {
      const listsRes = await fetch('/api/wallet/favorites')
      if (!listsRes.ok) { toast.error('Nie udało się pobrać list ulubionych'); return }
      const lists = await listsRes.json() as FavoriteList[]

      const withItems = await Promise.all(
        lists.map(async (lst) => {
          const itemsRes = await fetch(`/api/wallet/favorites/${lst.id}`)
          if (!itemsRes.ok) return { list: lst, items: [] as ListItem[] }
          const items = await itemsRes.json() as ListItem[]
          return { list: lst, items }
        })
      )

      setListsWithItems(withItems)

      setActiveTab((prev) => {
        const ids = withItems.map((l) => l.list.id)
        if (prev && ids.includes(prev)) return prev
        return ids[0] ?? null
      })
    } finally {
      setLoadingLists(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  async function createList() {
    const nm = newName.trim()
    if (!nm) { toast.warning('Nazwa listy jest wymagana'); return }
    setCreating(true)
    try {
      const res = await fetch('/api/wallet/favorites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: nm, description: newDesc.trim() || null }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({})) as { error?: string }
        toast.error(d.error ?? 'Nie udało się utworzyć listy')
        return
      }
      const created = await res.json() as FavoriteList
      toast.success('Lista utworzona')
      setNewName('')
      setNewDesc('')
      setShowCreateForm(false)
      setActiveTab(created.id)
      await refresh()
    } finally {
      setCreating(false)
    }
  }

  async function addToList(listId: string) {
    const res = await fetch(`/api/wallet/favorites/${listId}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, mic, name: name ?? symbol }),
    })
    if (!res.ok) {
      const d = await res.json().catch(() => ({})) as { error?: string }
      toast.error(d.error ?? 'Nie udało się dodać do listy')
      return
    }
    toast.success('Dodano do ulubionych')
    await refresh()
  }

  async function removeFromList(listId: string, sym: string) {
    const res = await fetch(
      `/api/wallet/favorites/${listId}/items/${encodeURIComponent(sym)}?with_alert=true`,
      { method: 'DELETE' },
    )
    if (!res.ok) { toast.error('Nie udało się usunąć z listy'); return }
    toast.success('Usunięto (i alert jeśli istniał)')
    await refresh()
  }

  async function deleteList(listId: string) {
    const res = await fetch(`/api/wallet/favorites/${listId}`, { method: 'DELETE' })
    if (!res.ok) { toast.error('Nie udało się usunąć listy'); return }
    toast.success('Lista usunięta')
    setDeleteTarget(null)
    await refresh()
  }

  const activeData = listsWithItems.find((l) => l.list.id === activeTab)

  return (
    <>
      {/* Sub-dialogs rendered on top */}
      {alertTarget && (
        <AlertDialog
          symbol={alertTarget.symbol}
          name={name ?? ''}
          initialAlert={alertTarget.alert}
          onClose={() => setAlertTarget(null)}
          onSaved={refresh}
        />
      )}
      {deleteTarget && (
        <ConfirmDeleteList
          listName={deleteTarget.name}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteList(deleteTarget.id)}
        />
      )}

      {/* Backdrop */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

        {/* Dialog card */}
        <div className="relative bg-slate-900 border border-white/10 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">

          {/* Header */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-white/10">
            <div className="flex-shrink-0 w-9 h-9 rounded-full bg-amber-500/20 flex items-center justify-center">
              <Star className="w-4.5 h-4.5 text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold text-white">Ulubione i alerty</h2>
              <p className="text-xs text-white/40 truncate">{symbol} — {name || '—'}</p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg text-white/30 hover:text-white hover:bg-white/5 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">

            {loadingLists ? (
              <div className="flex items-center justify-center py-10 text-white/30 text-sm">
                Ładowanie list…
              </div>
            ) : listsWithItems.length === 0 ? (
              /* ── No lists yet ── */
              <div className="space-y-4">
                <div className="flex flex-col items-center justify-center py-8 gap-2 text-white/30">
                  <Star className="w-8 h-8 text-white/10" />
                  <p className="text-sm">Brak list ulubionych</p>
                  <p className="text-xs">Utwórz pierwszą listę, aby zapisywać instrumenty.</p>
                </div>

                <div className="bg-slate-800/40 border border-white/10 rounded-xl p-4 space-y-3">
                  <p className="text-sm font-medium text-white">Utwórz listę</p>
                  <input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Nazwa listy *"
                    className="w-full px-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
                  />
                  <input
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                    placeholder="Opis (opcjonalnie)"
                    className="w-full px-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
                  />
                  <div className="flex justify-end">
                    <button
                      onClick={createList}
                      disabled={creating}
                      className="text-xs px-4 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
                    >
                      {creating ? 'Tworzenie…' : 'Utwórz'}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              /* ── Lists exist ── */
              <div className="space-y-3">

                {/* Create new list — collapsible */}
                <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
                  <button
                    onClick={() => setShowCreateForm((v) => !v)}
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Dodaj nową listę
                    {showCreateForm
                      ? <ChevronUp className="w-3.5 h-3.5 ml-auto" />
                      : <ChevronDown className="w-3.5 h-3.5 ml-auto" />}
                  </button>
                  {showCreateForm && (
                    <div className="px-4 pb-4 space-y-2 border-t border-white/5">
                      <input
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        placeholder="Nazwa listy *"
                        className="w-full mt-3 px-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
                      />
                      <input
                        value={newDesc}
                        onChange={(e) => setNewDesc(e.target.value)}
                        placeholder="Opis (opcjonalnie)"
                        className="w-full px-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
                      />
                      <div className="flex justify-end">
                        <button
                          onClick={createList}
                          disabled={creating}
                          className="text-xs px-4 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
                        >
                          {creating ? 'Tworzenie…' : 'Utwórz listę'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Tabs */}
                <div className="flex flex-wrap gap-1.5">
                  {listsWithItems.map(({ list, items }) => (
                    <button
                      key={list.id}
                      onClick={() => setActiveTab(list.id)}
                      className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                        activeTab === list.id
                          ? 'bg-blue-600 border-blue-500 text-white'
                          : 'bg-slate-900/40 border-white/10 text-white/50 hover:text-white hover:border-white/20'
                      }`}
                    >
                      {list.name} ({items.length})
                    </button>
                  ))}
                </div>

                {/* Active list content */}
                {activeData && (
                  <div className="space-y-3">

                    {/* List header card */}
                    <div className="bg-slate-800/40 border border-white/10 rounded-xl p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-white">{activeData.list.name}</p>
                          {activeData.list.description && (
                            <p className="text-xs text-white/40 mt-0.5">{activeData.list.description}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {/* Add/Remove current instrument */}
                          {(() => {
                            const inList = activeData.items.some(
                              (it) => it.symbol.toUpperCase() === symbol.toUpperCase()
                            )
                            return inList ? (
                              <button
                                onClick={() => removeFromList(activeData.list.id, symbol)}
                                className="text-xs px-3 py-1.5 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors"
                              >
                                Usuń bieżący
                              </button>
                            ) : (
                              <button
                                onClick={() => addToList(activeData.list.id)}
                                className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
                              >
                                Dodaj bieżący
                              </button>
                            )
                          })()}

                          {/* Delete list */}
                          <button
                            onClick={() => setDeleteTarget({ id: activeData.list.id, name: activeData.list.name })}
                            className="p-1.5 rounded-lg text-white/20 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                            title="Usuń listę"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Items */}
                    {activeData.items.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-6 text-white/30 gap-1">
                        <Star className="w-6 h-6 text-white/10" />
                        <p className="text-xs">Lista jest pusta</p>
                      </div>
                    ) : (
                      <div className="space-y-2 max-h-64 overflow-y-auto pr-0.5">
                        {activeData.items.map((it) => (
                          <div
                            key={it.symbol}
                            className={`flex items-center justify-between gap-3 px-4 py-2.5 rounded-xl border ${
                              it.symbol.toUpperCase() === symbol.toUpperCase()
                                ? 'bg-blue-500/5 border-blue-500/20'
                                : 'bg-slate-800/30 border-white/5'
                            }`}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium text-white">{it.symbol}</span>
                                {it.symbol.toUpperCase() === symbol.toUpperCase() && (
                                  <Check className="w-3 h-3 text-blue-400" />
                                )}
                              </div>
                              <p className="text-xs text-white/40 truncate">{it.name || '—'}</p>
                              <div className="mt-1">
                                <AlertBadge alert={it.alert} />
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                              <button
                                onClick={() => setAlertTarget({ symbol: it.symbol, alert: it.alert })}
                                className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg text-blue-400 hover:bg-blue-500/10 border border-blue-500/20 transition-colors"
                              >
                                <Bell className="w-3 h-3" />
                                Alert
                              </button>
                              <button
                                onClick={() => removeFromList(activeData.list.id, it.symbol)}
                                className="text-xs px-2 py-1 rounded-lg text-red-400 hover:bg-red-500/10 border border-red-500/20 transition-colors"
                              >
                                Usuń
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end px-5 py-3 border-t border-white/10">
            <button
              onClick={onClose}
              className="text-xs px-4 py-1.5 rounded-lg bg-slate-700/60 border border-white/10 text-white/60 hover:text-white transition-colors"
            >
              Zamknij
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
