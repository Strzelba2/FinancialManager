'use client'

import { useEffect, useState, useTransition } from 'react'
import { AlignLeft, Clock3, LoaderCircle, Save, StickyNote } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { UserNote } from '@/lib/types/wallet'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type ApiResult<T> = {
  ok: boolean
  data: T | null
  error?: string
}

async function apiFetch<T>(url: string, method: string, body?: unknown): Promise<ApiResult<T>> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    data = null
  }

  if (!res.ok) {
    const error =
      data && typeof data === 'object' && 'error' in data && typeof data.error === 'string'
        ? data.error
        : 'Wystąpił błąd'
    return { ok: false, data: null, error }
  }

  return { ok: true, data: data as T }
}

function formatTimestamp(value?: string): string {
  if (!value) return 'Jeszcze nie zapisano'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Jeszcze nie zapisano'

  return new Intl.DateTimeFormat('pl-PL', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function NotesDialog({ open, onOpenChange }: Props) {
  const [text, setText] = useState('')
  const [savedText, setSavedText] = useState('')
  const [note, setNote] = useState<UserNote | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [loadError, setLoadError] = useState<string>()
  const [saveError, setSaveError] = useState<string>()
  const [reloadKey, setReloadKey] = useState(0)
  const [isSaving, startTransition] = useTransition()

  const isDirty = text !== savedText

  useEffect(() => {
    if (!open) return

    let cancelled = false

    async function loadNote() {
      setIsLoading(true)
      setLoadError(undefined)
      setSaveError(undefined)
      setNote(null)
      setText('')
      setSavedText('')

      const { ok, data, error } = await apiFetch<UserNote | null>('/api/wallet/notes', 'GET')
      if (cancelled) return

      if (!ok) {
        setLoadError(error || 'Nie udało się wczytać notatki')
        setIsLoading(false)
        return
      }

      const nextText = data?.text ?? ''
      setText(nextText)
      setSavedText(nextText)
      setNote(data)
      setIsLoading(false)
    }

    void loadNote()

    return () => {
      cancelled = true
    }
  }, [open, reloadKey])

  function handleClose(next: boolean) {
    if (!next) {
      setLoadError(undefined)
      setSaveError(undefined)
    }
    onOpenChange(next)
  }

  function handleSave() {
    setSaveError(undefined)

    startTransition(async () => {
      const { ok, data, error } = await apiFetch<UserNote>('/api/wallet/notes', 'PUT', { text })

      if (!ok || !data) {
        setSaveError(error || 'Nie udało się zapisać notatki')
        return
      }

      setText(data.text)
      setSavedText(data.text)
      setNote(data)
      toast.success('Zapisano notatkę')
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-md border-white/10 text-white sm:max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-full bg-sky-500/15 border border-sky-500/30">
              <StickyNote className="w-5 h-5 text-sky-400" />
            </div>
            <div>
              <DialogTitle className="text-white text-lg">Notatki</DialogTitle>
              <DialogDescription className="text-white/50 text-sm">
                Jedna notatka dla użytkownika. Zmiany zapisują się po kliknięciu Zapisz.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-1">
          {[
            {
              icon: <StickyNote className="w-4 h-4 text-sky-400" />,
              label: 'Status',
              value: isDirty ? 'Niezapisane zmiany' : 'Zapisano',
            },
            {
              icon: <Clock3 className="w-4 h-4 text-amber-400" />,
              label: 'Ostatnia zmiana',
              value: formatTimestamp(note?.updated_at),
            },
            {
              icon: <AlignLeft className="w-4 h-4 text-emerald-400" />,
              label: 'Liczba znaków',
              value: `${text.length}`,
            },
          ].map(({ icon, label, value }) => (
            <div key={label} className="bg-slate-800/60 border border-white/10 rounded-xl p-3 min-w-0">
              <div className="flex items-center gap-1.5 mb-1">
                {icon}
                <span className="text-[10px] text-white/50 uppercase tracking-wide">{label}</span>
              </div>
              <p className="text-sm font-semibold truncate">{value}</p>
            </div>
          ))}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <label htmlFor="wallet-notes-textarea" className="text-sm font-medium text-white/80">
              Treść notatki
            </label>
            {isLoading ? (
              <span className="inline-flex items-center gap-1 text-xs text-white/45">
                <LoaderCircle className="w-3.5 h-3.5 animate-spin" />
                Wczytywanie…
              </span>
            ) : (
              <span className="text-xs text-white/45">
                {isDirty ? 'Masz niezapisane zmiany' : 'Treść zgodna z ostatnim zapisem'}
              </span>
            )}
          </div>

          <textarea
            id="wallet-notes-textarea"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Twoje notatki…"
            disabled={isLoading || isSaving}
            className="min-h-[320px] w-full resize-y rounded-xl border border-white/10 bg-slate-800/70 px-3 py-3 text-sm leading-6 text-white placeholder:text-white/30 outline-none transition focus:border-sky-400/30 focus:ring-2 focus:ring-sky-500/30 disabled:cursor-not-allowed disabled:opacity-70"
          />

          {loadError && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2">
              <p className="text-sm text-red-300">{loadError}</p>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setReloadKey((current) => current + 1)}
                className="h-7 text-red-200 hover:text-white hover:bg-red-500/10"
              >
                Spróbuj ponownie
              </Button>
            </div>
          )}

          {saveError && <p className="text-sm text-red-400">{saveError}</p>}
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button
            type="button"
            variant="ghost"
            onClick={() => handleClose(false)}
            className="text-white/60 hover:text-white hover:bg-white/10"
          >
            Zamknij
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={isLoading || isSaving || !isDirty}
            className="bg-sky-700 hover:bg-sky-600 text-white gap-2"
          >
            {isSaving ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {isSaving ? 'Zapisywanie…' : 'Zapisz'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
