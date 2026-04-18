'use client'

import { useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Wallet } from 'lucide-react'
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
}

export function CreateWalletDialog({ open, onOpenChange }: Props) {
  const router = useRouter()
  const formRef = useRef<HTMLFormElement>(null)
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string>()

  function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    const name = (new FormData(e.currentTarget).get('name') as string | null)?.trim() ?? ''
    if (!name) { setError('Podaj nazwę portfela'); return }
    setError(undefined)

    startTransition(async () => {
      const res = await fetch('/api/wallet/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      let data: { error?: string; success?: boolean; walletName?: string } = {}
      try {
        data = await res.json()
      } catch {
        setError('Nie udało się odczytać odpowiedzi serwera')
        return
      }

      if (!res.ok || data.error) {
        setError(data.error || 'Nie udało się utworzyć portfela')
        return
      }

      toast.success(`Portfel "${data.walletName}" został utworzony`)
      onOpenChange(false)
      formRef.current?.reset()
      router.refresh()
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-emerald-950/95 backdrop-blur-md border-emerald-800/50 text-white max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="p-2.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
              <Wallet className="w-5 h-5 text-emerald-400" />
            </div>
            <DialogTitle className="text-white text-lg">Utwórz nowy portfel</DialogTitle>
          </div>
          <DialogDescription className="text-white/50 text-sm">
            Podaj krótką, rozpoznawalną nazwę (max. 40 znaków).
          </DialogDescription>
        </DialogHeader>

        <form ref={formRef} onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label htmlFor="wallet-name" className="text-white/70 text-sm">
              Nazwa portfela *
            </Label>
            <Input
              id="wallet-name"
              name="name"
              placeholder="np. Wspólne wydatki"
              maxLength={40}
              autoFocus
              className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:ring-emerald-500/50"
            />
            <p className="text-white/40 text-xs">
              Wskazówka: użyj nazwy opisującej cel, np. &quot;Inwestycje 2025&quot;.
            </p>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              className="text-white/60 hover:text-white hover:bg-white/10"
            >
              Anuluj
            </Button>
            <Button
              type="submit"
              disabled={isPending}
              className="bg-emerald-600 hover:bg-emerald-500 text-white"
            >
              {isPending ? 'Tworzenie…' : 'Utwórz portfel'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
