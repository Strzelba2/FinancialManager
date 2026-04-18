'use client'

import { useState } from 'react'
import { X } from 'lucide-react'

export type PriceAlertModalData = {
  id?: string
  below_price: string | null
  above_price: string | null
  enabled: boolean
  one_shot: boolean
  expires_at: string | null
}

export function PriceAlertModal({
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
  const [below, setBelow] = useState(initial?.below_price ?? '')
  const [above, setAbove] = useState(initial?.above_price ?? '')
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)
  const [oneShot, setOneShot] = useState(initial?.one_shot ?? false)
  const [expiresAt, setExpiresAt] = useState(initial?.expires_at ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    if (!below.trim() && !above.trim()) {
      setError('Podaj below_price lub above_price')
      return
    }
    setSaving(true)
    setError(null)
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
      const json = await res.json().catch(() => ({})) as { error?: string }
      if (!res.ok) {
        setError(json.error ?? 'Błąd zapisu')
        return
      }
      onSaved()
    } catch {
      setError('Błąd połączenia')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`/api/wallet/alerts/${encodeURIComponent(symbol)}`, { method: 'DELETE' })
      const json = await res.json().catch(() => ({})) as { error?: string }
      if (!res.ok) {
        setError(json.error ?? 'Błąd usuwania')
        return
      }
      onDeleted()
    } catch {
      setError('Błąd połączenia')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-slate-900 border border-white/10 rounded-xl p-5 w-full max-w-sm mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold text-white">Alert cenowy</h3>
          <button onClick={onClose} className="text-white/40 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-xs text-white/40 mb-4">{symbol} — {name}</p>

        {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

        <div className="grid grid-cols-2 gap-3 mb-3">
          <label className="text-xs text-white/50">
            Below price
            <input
              value={below}
              onChange={(e) => setBelow(e.target.value)}
              placeholder="np. 100.00"
              className="mt-1 w-full px-2.5 py-1.5 text-sm bg-slate-800 border border-white/10 rounded-lg text-white placeholder-white/20 focus:outline-none focus:border-blue-500/50"
            />
          </label>
          <label className="text-xs text-white/50">
            Above price
            <input
              value={above}
              onChange={(e) => setAbove(e.target.value)}
              placeholder="np. 120.00"
              className="mt-1 w-full px-2.5 py-1.5 text-sm bg-slate-800 border border-white/10 rounded-lg text-white placeholder-white/20 focus:outline-none focus:border-blue-500/50"
            />
          </label>
        </div>

        <label className="text-xs text-white/50 block mb-3">
          Wygasa (opcjonalnie)
          <input
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            placeholder="np. 2025-12-31T23:59"
            className="mt-1 w-full px-2.5 py-1.5 text-sm bg-slate-800 border border-white/10 rounded-lg text-white placeholder-white/20 focus:outline-none focus:border-blue-500/50"
          />
        </label>

        <div className="flex gap-4 mb-4 text-sm">
          <label className="flex items-center gap-2 cursor-pointer text-white/60">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="accent-blue-500" />
            Aktywny
          </label>
          <label className="flex items-center gap-2 cursor-pointer text-white/60">
            <input type="checkbox" checked={oneShot} onChange={(e) => setOneShot(e.target.checked)} className="accent-blue-500" />
            Jednorazowy
          </label>
        </div>

        <div className="flex gap-2 justify-end">
          {initial && (
            <button
              onClick={handleDelete}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-red-400 border border-red-500/20 hover:bg-red-500/10 disabled:opacity-50 transition-colors"
            >
              Usuń alert
            </button>
          )}
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-xs text-white/50 hover:text-white transition-colors">
            Anuluj
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-1.5 rounded-lg text-xs font-medium bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Zapisuję…' : 'Zapisz'}
          </button>
        </div>
      </div>
    </div>
  )
}
