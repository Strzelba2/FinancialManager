'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { FileDown, Plus, StickyNote } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type Props = {
  walletNames: string[]   // e.g. ['Wszystkie', 'Wspólne', 'Makler']
  currencies: string[]    // ['PLN', 'USD', 'EUR']
}

export function WalletToolbar({ walletNames, currencies }: Props) {
  const router = useRouter()
  const params = useSearchParams()

  // Update a single search param and push to history
  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params.toString())
    next.set(key, value)
    router.push(`?${next.toString()}`)
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-800/40 border border-white/10 rounded-xl mb-4">
      {/* Left: filters */}
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={params.get('range') ?? 'year'}
          onValueChange={(v) => setParam('range', v)}
        >
          <SelectTrigger className="w-40 bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            <SelectItem value="month">Ostatni miesiąc</SelectItem>
            <SelectItem value="3months">Ostatnie 3 mies.</SelectItem>
            <SelectItem value="year">Ostatni rok</SelectItem>
            <SelectItem value="all">Całość</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={params.get('wallet') ?? 'all'}
          onValueChange={(v) => setParam('wallet', v)}
        >
          <SelectTrigger className="w-36 bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            <SelectItem value="all">Wszystkie</SelectItem>
            {walletNames.map((n) => (
              <SelectItem key={n} value={n}>{n}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={params.get('currency') ?? 'PLN'}
          onValueChange={(v) => setParam('currency', v)}
        >
          <SelectTrigger className="w-24 bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {currencies.map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          size="sm"
          onClick={() => setParam('modal', 'transaction')}
          className="h-8 bg-emerald-700/60 hover:bg-emerald-600/70 text-white/80 hover:text-white border-0 gap-1"
        >
          <Plus className="w-3.5 h-3.5" /> Transakcja
        </Button>
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setParam('modal', 'notes')}
          className="h-8 text-white/60 hover:text-white hover:bg-white/10 gap-1"
        >
          <StickyNote className="w-3.5 h-3.5" /> Notatki
        </Button>
        {/* TODO: export CSV/PDF */}
        <Button size="sm" variant="ghost" className="h-8 text-white/60 hover:text-white hover:bg-white/10 gap-1">
          <FileDown className="w-3.5 h-3.5" /> Eksport
        </Button>
      </div>
    </div>
  )
}
