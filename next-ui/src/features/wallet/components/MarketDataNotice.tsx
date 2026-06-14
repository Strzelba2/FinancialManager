'use client'

import { useMemo, useState } from 'react'
import { AlertTriangle, Info, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

type NoticeScope = 'dashboard' | 'manager' | 'holdings'

type Props = {
  affectedPositions?: number
  defaultOpen?: boolean
  scope?: NoticeScope
}

function scopeDetails(scope: NoticeScope): string {
  if (scope === 'manager') {
    return 'Wartości rachunków maklerskich i podsumowania portfeli mogą nie obejmować części pozycji bez aktualnego kursu.'
  }
  if (scope === 'holdings') {
    return 'Pozycje bez kursu są oznaczone jako brak notowań i nie zwiększają bieżącej wartości pozycji maklerskich.'
  }
  return 'Wartość netto, inwestycje, alokacja oraz wykres aktywów nominalnie vs realnie mogą być niepełne lub zaniżone.'
}

export function MarketDataNotice({
  affectedPositions,
  defaultOpen = true,
  scope = 'dashboard',
}: Props) {
  const [visible, setVisible] = useState(true)
  const [open, setOpen] = useState(defaultOpen)

  const affectedText = useMemo(() => {
    if (!affectedPositions || affectedPositions <= 0) return null
    const label = affectedPositions === 1 ? 'pozycja nie ma' : 'pozycji nie ma'
    return `${affectedPositions} ${label} aktualnego notowania.`
  }, [affectedPositions])

  if (!visible) return null

  const detail = scopeDetails(scope)

  return (
    <>
      <section
        role="status"
        aria-live="polite"
        className="mb-4 rounded-xl border border-amber-400/25 bg-amber-500/10 px-4 py-3 text-amber-100"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-300" />
            <div>
              <p className="text-sm font-semibold text-amber-100">Dane rynkowe są tymczasowo niedostępne</p>
              <p className="mt-1 text-sm text-amber-100/75">
                Nie udało się pobrać aktualnych notowań z serwisu giełdowego. {detail}
              </p>
              {affectedText && (
                <p className="mt-1 text-xs text-amber-100/60">{affectedText}</p>
              )}
            </div>
          </div>
          <div className="flex flex-shrink-0 items-center gap-2 self-end sm:self-start">
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300/25 bg-amber-300/10 px-3 py-1.5 text-xs font-medium text-amber-100 transition-colors hover:bg-amber-300/15"
            >
              <Info className="h-3.5 w-3.5" />
              Szczegóły
            </button>
            <button
              type="button"
              aria-label="Ukryj komunikat o danych rynkowych"
              onClick={() => setVisible(false)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-amber-100/50 transition-colors hover:bg-amber-300/10 hover:text-amber-100"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      </section>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="border border-amber-400/20 bg-slate-950 text-white sm:max-w-lg">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-400/10 text-amber-300">
                <AlertTriangle className="h-5 w-5" />
              </span>
              <DialogTitle>Dane rynkowe niedostępne</DialogTitle>
            </div>
            <DialogDescription className="text-white/60">
              Aktualne notowania nie są teraz dostępne dla części instrumentów.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm text-white/70">
            <p>
              System nadal pokazuje zapisane rachunki i pozycje, ale bieżąca wycena instrumentów
              bez kursu nie może zostać wiarygodnie obliczona.
            </p>
            <p>
              Do czasu przywrócenia danych rynkowych wartość majątku, inwestycje,
              alokacja oraz wykres aktywów mogą być niepełne lub zaniżone.
            </p>
            {affectedText && (
              <p className="rounded-lg border border-amber-400/15 bg-amber-400/10 px-3 py-2 text-amber-100/80">
                {affectedText}
              </p>
            )}
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              Rozumiem
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
