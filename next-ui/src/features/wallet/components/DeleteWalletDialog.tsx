'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  wallets: { id: string; name: string }[]
}

export function DeleteWalletDialog({ open, onOpenChange, wallets }: Props) {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [selected, setSelected] = useState<string[]>([])
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string>()

  function toggle(id: string) {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  function handleClose(next: boolean) {
    if (!next) {
      setSelected([])
      setConfirm('')
      setError(undefined)
    }
    onOpenChange(next)
  }

  function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (selected.length === 0) { setError('Wybierz co najmniej jeden portfel'); return }
    if (confirm.trim().toUpperCase() !== 'USUŃ') { setError('Wpisz dokładnie: USUŃ'); return }
    setError(undefined)

    startTransition(async () => {
      const res = await fetch('/api/wallet/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ walletIds: selected }),
      })
      let data: { error?: string; success?: boolean; partial?: boolean } = {}
      try { data = await res.json() } catch { /* ignore */ }

      if (!res.ok || data.error) {
        setError(data.error || 'Nie udało się usunąć portfeli')
        return
      }

      if (data.partial) {
        toast.warning('Niektóre portfele nie zostały usunięte')
      } else {
        const names = wallets.filter(w => selected.includes(w.id)).map(w => w.name).join(', ')
        toast.success(`Usunięto: ${names}`)
      }

      handleClose(false)
      router.refresh()
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-red-950/95 backdrop-blur-md border-red-800/50 text-white max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="p-2.5 rounded-full bg-red-500/15 border border-red-500/30">
              <Trash2 className="w-5 h-5 text-red-400" />
            </div>
            <DialogTitle className="text-white text-lg">Usuń portfele</DialogTitle>
          </div>
          <DialogDescription className="text-white/50 text-sm">
            Wybierz portfele do usunięcia. Tej operacji nie można cofnąć.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">

          <div className="space-y-2">
            {wallets.length === 0 ? (
              <p className="text-white/40 text-sm">Brak portfeli do usunięcia.</p>
            ) : (
              wallets.map(w => (
                <label
                  key={w.id}
                  className="flex items-center gap-3 p-2.5 rounded-lg bg-white/5 border border-white/10 cursor-pointer hover:bg-white/10 transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(w.id)}
                    onChange={() => toggle(w.id)}
                    className="w-4 h-4 accent-red-500 cursor-pointer"
                  />
                  <span className="text-sm text-white/80">{w.name}</span>
                </label>
              ))
            )}
          </div>

          <div className="bg-red-900/30 border border-red-700/40 rounded-lg px-3 py-2 text-xs text-red-300">
            <strong>Uwaga:</strong> usunięcie portfela może spowodować usunięcie powiązanych danych
            (transakcje, ustawienia).
          </div>

          <div className="space-y-1.5">
            <Label className="text-white/70 text-sm">Aby potwierdzić, wpisz: USUŃ</Label>
            <Input
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              placeholder="USUŃ"
              className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:ring-red-500/50"
            />
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={() => handleClose(false)}
              className="text-white/60 hover:text-white hover:bg-white/10"
            >
              Anuluj
            </Button>
            <Button
              type="submit"
              disabled={isPending || wallets.length === 0}
              className="bg-red-600 hover:bg-red-500 text-white"
            >
              {isPending ? 'Usuwanie…' : 'Usuń'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
