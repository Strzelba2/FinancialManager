'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { TrendingUp, Home, Coins, BarChart3, Plus, Save, Trash2, DollarSign, ArrowLeft } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DateTimePicker } from '@/components/ui/date-time-picker'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

export type RealEstateRow = {
  id: string
  walletId: string
  name: string
  area_m2: string | null
  valueFmt: string
  purchaseCurrency: string
}

export type MetalRow = {
  id: string
  walletId: string
  metal: string
  grams: string
  valueFmt: string
}

export type WalletOpt = {
  id: string
  name: string
  accounts: { id: string; name: string }[]
}

type View =
  | { mode: 'list' }
  | { mode: 'add-estate' }
  | { mode: 'add-metal' }
  | { mode: 'prices-m2' }
  | { mode: 'sell-estate'; row: RealEstateRow }
  | { mode: 'sell-metal'; row: MetalRow }

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  totalFmt: string
  brokerageFmt: string
  estatesFmt: string
  metalsFmt: string
  realEstates: RealEstateRow[]
  metals: MetalRow[]
  wallets: WalletOpt[]
  viewCurrency: string
}

const PROPERTY_TYPES = ['APARTMENT', 'LAND', 'HAUSE'] as const
const METAL_TYPES = ['GOLD', 'SILVER', 'PLATINUM', 'PALLADIUM'] as const
const CURRENCIES = ['PLN', 'USD', 'EUR'] as const

async function apiFetch(url: string, method: string, body?: unknown) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  let data: { error?: string; success?: boolean } = {}
  try { data = await res.json() } catch { /* ignore */ }
  return { ok: res.ok, error: data.error }
}

function AddEstateForm({
  wallets,
  viewCurrency,
  onSuccess,
  onCancel,
}: {
  wallets: WalletOpt[]
  viewCurrency: string
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [walletId, setWalletId] = useState(wallets[0]?.id ?? '')
  const [name, setName] = useState('')
  const [country, setCountry] = useState('')
  const [city, setCity] = useState('')
  const [type, setType] = useState<string>(PROPERTY_TYPES[0])
  const [area, setArea] = useState('')
  const [price, setPrice] = useState('')
  const [currency, setCurrency] = useState<string>(viewCurrency)
  const [error, setError] = useState<string>()

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!name.trim()) { setError('Podaj nazwę nieruchomości'); return }
    if (!price.trim()) { setError('Podaj cenę zakupu'); return }
    if (!walletId) { setError('Wybierz portfel'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch('/api/wallet/real-estates', 'POST', {
        wallet_id: walletId,
        name: name.trim(),
        country: country.trim() || null,
        city: city.trim() || null,
        type,
        area_m2: area.trim() || null,
        purchase_price: price.trim().replace(',', '.'),
        purchase_currency: currency,
      })
      if (!ok) { setError(err || 'Nie udało się dodać nieruchomości'); return }
      toast.success('Nieruchomość została dodana')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <h3 className="text-base font-semibold text-white">Dodaj nieruchomość</h3>
      </div>

      {wallets.length > 1 && (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Portfel *</Label>
          <Select value={walletId} onValueChange={setWalletId}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {wallets.map(w => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Nazwa *</Label>
        <Input value={name} onChange={e => setName(e.target.value)} placeholder="np. Mieszkanie Warszawa"
          className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Kraj (ISO2)</Label>
          <Input value={country} onChange={e => setCountry(e.target.value)} placeholder="PL"
            maxLength={2}
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Miasto</Label>
          <Input value={city} onChange={e => setCity(e.target.value)} placeholder="Warszawa"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Typ nieruchomości *</Label>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {PROPERTY_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Powierzchnia (m²)</Label>
          <Input value={area} onChange={e => setArea(e.target.value)} placeholder="65.5"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Cena zakupu *</Label>
          <Input value={price} onChange={e => setPrice(e.target.value)} placeholder="450000"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Waluta zakupu</Label>
        <Select value={currency} onValueChange={setCurrency}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white hover:bg-white/10">Anuluj</Button>
        <Button type="submit" disabled={isPending}
          className="bg-emerald-700 hover:bg-emerald-600 text-white">
          {isPending ? 'Dodawanie…' : 'Dodaj'}
        </Button>
      </div>
    </form>
  )
}

function AddMetalForm({
  wallets,
  viewCurrency,
  onSuccess,
  onCancel,
}: {
  wallets: WalletOpt[]
  viewCurrency: string
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [walletId, setWalletId] = useState(wallets[0]?.id ?? '')
  const [metal, setMetal] = useState<string>(METAL_TYPES[0])
  const [grams, setGrams] = useState('')
  const [costBasis, setCostBasis] = useState('')
  const [currency, setCurrency] = useState<string>(viewCurrency)
  const [error, setError] = useState<string>()

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!grams.trim()) { setError('Podaj ilość gramów'); return }
    if (!walletId) { setError('Wybierz portfel'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch('/api/wallet/metal-holdings', 'POST', {
        wallet_id: walletId,
        metal,
        grams: grams.trim().replace(',', '.'),
        cost_basis: costBasis.trim().replace(',', '.') || null,
        cost_currency: costBasis.trim() ? currency : null,
      })
      if (!ok) { setError(err || 'Nie udało się dodać metalu'); return }
      toast.success('Metal został dodany')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <h3 className="text-base font-semibold text-white">Dodaj metal szlachetny</h3>
      </div>

      {wallets.length > 1 && (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Portfel *</Label>
          <Select value={walletId} onValueChange={setWalletId}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {wallets.map(w => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Metal *</Label>
        <Select value={metal} onValueChange={setMetal}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {METAL_TYPES.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Ilość (g) *</Label>
        <Input value={grams} onChange={e => setGrams(e.target.value)} placeholder="np. 31.10"
          inputMode="decimal"
          className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Koszt bazowy (opcjonalnie)</Label>
          <Input value={costBasis} onChange={e => setCostBasis(e.target.value)} placeholder="np. 8000"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Waluta kosztu</Label>
          <Select value={currency} onValueChange={setCurrency}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white hover:bg-white/10">Anuluj</Button>
        <Button type="submit" disabled={isPending}
          className="bg-emerald-700 hover:bg-emerald-600 text-white">
          {isPending ? 'Dodawanie…' : 'Dodaj'}
        </Button>
      </div>
    </form>
  )
}

function SellEstateForm({
  row,
  wallets,
  onSuccess,
  onCancel,
}: {
  row: RealEstateRow
  wallets: WalletOpt[]
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const accounts = wallets.find(w => w.id === row.walletId)?.accounts ?? []
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '')
  const [proceeds, setProceeds] = useState('')
  const [currency, setCurrency] = useState<string>(row.purchaseCurrency)
  const [date, setDate] = useState('')
  const [createTx, setCreateTx] = useState(true)
  const [error, setError] = useState<string>()

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!proceeds.trim()) { setError('Podaj kwotę sprzedaży'); return }
    if (!accountId) { setError('Wybierz konto do wpłaty'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch(
        `/api/wallet/real-estates/${row.id}/sell`, 'POST',
        {
          deposit_account_id: accountId,
          proceeds_amount: proceeds.trim().replace(',', '.'),
          proceeds_currency: currency,
          occurred_at: date || null,
          create_transaction: createTx,
        }
      )
      if (!ok) { setError(err || 'Nie udało się sprzedać nieruchomości'); return }
      toast.success('Nieruchomość sprzedana')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h3 className="text-base font-semibold text-white">Sprzedaj nieruchomość</h3>
          <p className="text-xs text-white/50">{row.name}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Kwota sprzedaży *</Label>
          <Input value={proceeds} onChange={e => setProceeds(e.target.value)} placeholder="np. 650000"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Waluta</Label>
          <Select value={currency} onValueChange={setCurrency}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {accounts.length > 0 ? (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Konto do wpłaty *</Label>
          <Select value={accountId} onValueChange={setAccountId}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <p className="text-amber-400 text-xs bg-amber-500/10 border border-amber-500/30 rounded-lg p-2">
          Brak kont bieżących w tym portfelu. Dodaj konto przed sprzedażą.
        </p>
      )}

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Data transakcji (opcjonalnie)</Label>
        <DateTimePicker value={date} onChange={setDate} placeholder="Wybierz datę i godzinę" />
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" checked={createTx} onChange={e => setCreateTx(e.target.checked)}
          className="w-4 h-4 accent-emerald-500" />
        <span className="text-sm text-white/70">Utwórz transakcję bankową</span>
      </label>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white hover:bg-white/10">Anuluj</Button>
        <Button type="submit" disabled={isPending || accounts.length === 0}
          className="bg-emerald-700 hover:bg-emerald-600 text-white">
          {isPending ? 'Sprzedawanie…' : 'Sprzedaj'}
        </Button>
      </div>
    </form>
  )
}

function SellMetalForm({
  row,
  wallets,
  onSuccess,
  onCancel,
}: {
  row: MetalRow
  wallets: WalletOpt[]
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const accounts = wallets.find(w => w.id === row.walletId)?.accounts ?? []
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '')
  const [gramsSold, setGramsSold] = useState(row.grams)
  const [proceeds, setProceeds] = useState('')
  const [currency, setCurrency] = useState<string>('PLN')
  const [date, setDate] = useState('')
  const [createTx, setCreateTx] = useState(true)
  const [error, setError] = useState<string>()

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!gramsSold.trim()) { setError('Podaj ilość gramów do sprzedaży'); return }
    if (!proceeds.trim()) { setError('Podaj kwotę uzyskaną ze sprzedaży'); return }
    if (!accountId) { setError('Wybierz konto do wpłaty'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch(
        `/api/wallet/metal-holdings/${row.id}/sell`, 'POST',
        {
          deposit_account_id: accountId,
          grams_sold: gramsSold.trim().replace(',', '.'),
          proceeds_amount: proceeds.trim().replace(',', '.'),
          proceeds_currency: currency,
          occurred_at: date || null,
          create_transaction: createTx,
        }
      )
      if (!ok) { setError(err || 'Nie udało się sprzedać metalu'); return }
      toast.success('Metal sprzedany')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h3 className="text-base font-semibold text-white">Sprzedaj metal</h3>
          <p className="text-xs text-white/50">{row.metal} · dostępne: {row.grams} g</p>
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Ilość do sprzedaży (g) *</Label>
        <Input value={gramsSold} onChange={e => setGramsSold(e.target.value)} placeholder="np. 10.0"
          inputMode="decimal"
          className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Kwota uzyskana *</Label>
          <Input value={proceeds} onChange={e => setProceeds(e.target.value)} placeholder="np. 3500"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Waluta</Label>
          <Select value={currency} onValueChange={setCurrency}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {accounts.length > 0 ? (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Konto do wpłaty *</Label>
          <Select value={accountId} onValueChange={setAccountId}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {accounts.map(a => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <p className="text-amber-400 text-xs bg-amber-500/10 border border-amber-500/30 rounded-lg p-2">
          Brak kont bieżących w tym portfelu. Dodaj konto przed sprzedażą.
        </p>
      )}

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Data transakcji (opcjonalnie)</Label>
        <DateTimePicker value={date} onChange={setDate} placeholder="Wybierz datę i godzinę" />
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" checked={createTx} onChange={e => setCreateTx(e.target.checked)}
          className="w-4 h-4 accent-emerald-500" />
        <span className="text-sm text-white/70">Utwórz transakcję bankową</span>
      </label>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white hover:bg-white/10">Anuluj</Button>
        <Button type="submit" disabled={isPending || accounts.length === 0}
          className="bg-emerald-700 hover:bg-emerald-600 text-white">
          {isPending ? 'Sprzedawanie…' : 'Sprzedaj'}
        </Button>
      </div>
    </form>
  )
}

function PricesM2Form({
  onSuccess,
  onCancel,
}: {
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [country, setCountry] = useState('')
  const [city, setCity] = useState('')
  const [type, setType] = useState<string>(PROPERTY_TYPES[0])
  const [currency, setCurrency] = useState<string>('PLN')
  const [priceM2, setPriceM2] = useState('')
  const [error, setError] = useState<string>()

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!priceM2.trim()) { setError('Podaj cenę za m²'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch('/api/wallet/real-estate-prices', 'POST', {
        country: country.trim().toUpperCase() || null,
        city: city.trim() || null,
        type,
        currency,
        avg_price_per_m2: priceM2.trim().replace(',', '.'),
      })
      if (!ok) { setError(err || 'Nie udało się zapisać ceny'); return }
      toast.success('Zapisano cenę za m²')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h3 className="text-base font-semibold text-white">Średnie ceny za m²</h3>
          <p className="text-xs text-white/50">Nowy wpis będzie użyty do wyceny nieruchomości</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Kraj (ISO2)</Label>
          <Input value={country} onChange={e => setCountry(e.target.value)} placeholder="PL"
            maxLength={2}
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Miasto (opcjonalnie)</Label>
          <Input value={city} onChange={e => setCity(e.target.value)} placeholder="Warszawa"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Typ nieruchomości</Label>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {PROPERTY_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Waluta</Label>
          <Select value={currency} onValueChange={setCurrency}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Cena za 1 m² *</Label>
          <Input value={priceM2} onChange={e => setPriceM2(e.target.value)} placeholder="np. 12 000"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel}
          className="text-white/60 hover:text-white hover:bg-white/10">Anuluj</Button>
        <Button type="submit" disabled={isPending}
          className="bg-sky-700 hover:bg-sky-600 text-white">
          {isPending ? 'Zapisywanie…' : 'Zapisz'}
        </Button>
      </div>
    </form>
  )
}

export function InvestmentsDialog({
  open,
  onOpenChange,
  totalFmt,
  brokerageFmt,
  estatesFmt,
  metalsFmt,
  realEstates,
  metals,
  wallets,
  viewCurrency,
}: Props) {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [view, setView] = useState<View>({ mode: 'list' })
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [editNames, setEditNames] = useState<Record<string, string>>({})
  const [editGrams, setEditGrams] = useState<Record<string, string>>({})
  const [rowError, setRowError] = useState<{ id: string; msg: string } | null>(null)

  function handleClose(next: boolean) {
    if (!next) {
      setView({ mode: 'list' })
      setDeletingId(null)
      setEditNames({})
      setEditGrams({})
      setRowError(null)
    }
    onOpenChange(next)
  }

  function refresh() {
    router.refresh()
  }

  function handleSubSuccess() {
    setView({ mode: 'list' })
    refresh()
  }

  function handleSaveEstateName(id: string) {
    const name = (editNames[id] ?? '').trim()
    if (!name) return
    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/real-estates/${id}`, 'PUT', { name })
      if (!ok) { setRowError({ id, msg: error || 'Błąd zapisu' }); return }
      setEditNames(prev => { const n = { ...prev }; delete n[id]; return n })
      setRowError(null)
      toast.success('Zaktualizowano')
      refresh()
    })
  }

  function handleDeleteEstate(id: string) {
    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/real-estates/${id}`, 'DELETE')
      if (!ok) { setRowError({ id, msg: error || 'Błąd usuwania' }); return }
      setDeletingId(null)
      setRowError(null)
      toast.success('Usunięto nieruchomość')
      refresh()
    })
  }

  function handleSaveMetalGrams(id: string) {
    const grams = (editGrams[id] ?? '').trim().replace(',', '.')
    if (!grams) return
    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/metal-holdings/${id}`, 'PUT', { grams })
      if (!ok) { setRowError({ id, msg: error || 'Błąd zapisu' }); return }
      setEditGrams(prev => { const n = { ...prev }; delete n[id]; return n })
      setRowError(null)
      toast.success('Zaktualizowano')
      refresh()
    })
  }

  function handleDeleteMetal(id: string) {
    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/metal-holdings/${id}`, 'DELETE')
      if (!ok) { setRowError({ id, msg: error || 'Błąd usuwania' }); return }
      setDeletingId(null)
      setRowError(null)
      toast.success('Usunięto pozycję')
      refresh()
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-md border-white/10 text-white sm:max-w-2xl max-h-[85vh] overflow-y-auto">

        {/* ── List view ── */}
        {view.mode === 'list' && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-full bg-blue-500/15 border border-blue-500/30">
                  <TrendingUp className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <DialogTitle className="text-white text-lg">Szczegóły inwestycji</DialogTitle>
                  <DialogDescription className="text-white/50 text-sm">
                    Łącznie: <span className="text-white font-semibold">{totalFmt}</span>
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            {/* Sub-KPIs */}
            <div className="grid grid-cols-3 gap-3 mt-1">
              {[
                { icon: <BarChart3 className="w-4 h-4 text-violet-400" />, label: 'Akcje', value: brokerageFmt },
                { icon: <Home className="w-4 h-4 text-sky-400" />, label: 'Nieruchom.', value: estatesFmt },
                { icon: <Coins className="w-4 h-4 text-amber-400" />, label: 'Metale', value: metalsFmt },
              ].map(({ icon, label, value }) => (
                <div key={label} className="bg-slate-800/60 border border-white/10 rounded-xl p-3 min-w-0">
                  <div className="flex items-center gap-1.5 mb-1">{icon}
                    <span className="text-[10px] text-white/50 uppercase tracking-wide">{label}</span>
                  </div>
                  <p className="text-sm font-semibold truncate">{value}</p>
                </div>
              ))}
            </div>

            {/* Real estates section */}
            <div className="mt-2">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <Home className="w-4 h-4 text-white/40" />
                  <span className="text-sm font-medium text-white/80">Nieruchomości</span>
                </div>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setView({ mode: 'prices-m2' })}
                    className="h-7 text-xs text-sky-400/70 hover:text-sky-300 hover:bg-sky-500/10 gap-1">
                    Ceny m²
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setView({ mode: 'add-estate' })}
                    className="h-7 text-xs text-white/60 hover:text-white hover:bg-white/10 gap-1">
                    <Plus className="w-3 h-3" /> Dodaj
                  </Button>
                </div>
              </div>

              {realEstates.length === 0 ? (
                <p className="text-xs text-white/30 py-3 text-center">Brak nieruchomości w portfelu</p>
              ) : (
                <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left px-3 py-2 text-xs text-white/40 font-medium">Nieruchomość</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Pow.</th>
                        <th className="text-right px-3 py-2 text-xs text-white/40 font-medium">Wartość</th>
                        <th className="w-24" />
                      </tr>
                    </thead>
                    <tbody>
                      {realEstates.map((re, i) => (
                        <tr key={re.id} className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}>
                          <td className="px-3 py-1.5">
                            {deletingId === re.id ? (
                              <span className="text-red-400 text-xs">Czy na pewno usunąć?</span>
                            ) : (
                              <Input
                                value={editNames[re.id] ?? re.name}
                                onChange={e => setEditNames(prev => ({ ...prev, [re.id]: e.target.value }))}
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white focus-visible:border-white/20 focus-visible:bg-slate-700/50"
                              />
                            )}
                            {rowError?.id === re.id && (
                              <p className="text-red-400 text-xs mt-0.5">{rowError.msg}</p>
                            )}
                          </td>
                          <td className="px-2 py-1.5 text-center text-white/50 text-xs">
                            {re.area_m2 ? `${re.area_m2} m²` : '—'}
                          </td>
                          <td className="px-3 py-1.5 text-right text-white/80 text-xs whitespace-nowrap">
                            {re.valueFmt}
                          </td>
                          <td className="px-2 py-1.5">
                            {deletingId === re.id ? (
                              <div className="flex items-center gap-1">
                                <Button size="icon" variant="ghost"
                                  onClick={() => handleDeleteEstate(re.id)}
                                  disabled={isPending}
                                  className="h-6 w-6 text-red-400 hover:text-red-300 hover:bg-red-500/10">
                                  <Trash2 className="w-3 h-3" />
                                </Button>
                                <Button size="icon" variant="ghost"
                                  onClick={() => setDeletingId(null)}
                                  className="h-6 w-6 text-white/40 hover:text-white hover:bg-white/10">
                                  ✕
                                </Button>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1">
                                {(editNames[re.id] !== undefined && editNames[re.id] !== re.name) && (
                                  <Button size="icon" variant="ghost"
                                    onClick={() => handleSaveEstateName(re.id)}
                                    disabled={isPending}
                                    className="h-6 w-6 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10">
                                    <Save className="w-3 h-3" />
                                  </Button>
                                )}
                                <Button size="icon" variant="ghost"
                                  onClick={() => setDeletingId(re.id)}
                                  className="h-6 w-6 text-white/30 hover:text-red-400 hover:bg-red-500/10">
                                  <Trash2 className="w-3 h-3" />
                                </Button>
                                <Button size="icon" variant="ghost"
                                  onClick={() => setView({ mode: 'sell-estate', row: re })}
                                  className="h-6 w-6 text-white/30 hover:text-emerald-400 hover:bg-emerald-500/10">
                                  <DollarSign className="w-3 h-3" />
                                </Button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Metals section */}
            <div className="mt-2">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <Coins className="w-4 h-4 text-white/40" />
                  <span className="text-sm font-medium text-white/80">Metale szlachetne</span>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setView({ mode: 'add-metal' })}
                  className="h-7 text-xs text-white/60 hover:text-white hover:bg-white/10 gap-1">
                  <Plus className="w-3 h-3" /> Dodaj
                </Button>
              </div>

              {metals.length === 0 ? (
                <p className="text-xs text-white/30 py-3 text-center">Brak metali szlachetnych w portfelu</p>
              ) : (
                <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left px-3 py-2 text-xs text-white/40 font-medium">Metal</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Ilość (g)</th>
                        <th className="text-right px-3 py-2 text-xs text-white/40 font-medium">Wartość</th>
                        <th className="w-24" />
                      </tr>
                    </thead>
                    <tbody>
                      {metals.map((m, i) => (
                        <tr key={m.id} className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}>
                          <td className="px-3 py-1.5 text-white/80 text-xs">{m.metal}</td>
                          <td className="px-2 py-1.5">
                            {deletingId === m.id ? (
                              <span className="text-red-400 text-xs">Czy na pewno usunąć?</span>
                            ) : (
                              <Input
                                value={editGrams[m.id] ?? m.grams}
                                onChange={e => setEditGrams(prev => ({ ...prev, [m.id]: e.target.value }))}
                                inputMode="decimal"
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white text-center focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[80px] mx-auto"
                              />
                            )}
                            {rowError?.id === m.id && (
                              <p className="text-red-400 text-xs mt-0.5">{rowError.msg}</p>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-right text-white/80 text-xs whitespace-nowrap">
                            {m.valueFmt}
                          </td>
                          <td className="px-2 py-1.5">
                            {deletingId === m.id ? (
                              <div className="flex items-center gap-1">
                                <Button size="icon" variant="ghost"
                                  onClick={() => handleDeleteMetal(m.id)}
                                  disabled={isPending}
                                  className="h-6 w-6 text-red-400 hover:text-red-300 hover:bg-red-500/10">
                                  <Trash2 className="w-3 h-3" />
                                </Button>
                                <Button size="icon" variant="ghost"
                                  onClick={() => setDeletingId(null)}
                                  className="h-6 w-6 text-white/40 hover:text-white hover:bg-white/10">
                                  ✕
                                </Button>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1">
                                {(editGrams[m.id] !== undefined && editGrams[m.id] !== m.grams) && (
                                  <Button size="icon" variant="ghost"
                                    onClick={() => handleSaveMetalGrams(m.id)}
                                    disabled={isPending}
                                    className="h-6 w-6 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10">
                                    <Save className="w-3 h-3" />
                                  </Button>
                                )}
                                <Button size="icon" variant="ghost"
                                  onClick={() => setDeletingId(m.id)}
                                  className="h-6 w-6 text-white/30 hover:text-red-400 hover:bg-red-500/10">
                                  <Trash2 className="w-3 h-3" />
                                </Button>
                                <Button size="icon" variant="ghost"
                                  onClick={() => setView({ mode: 'sell-metal', row: m })}
                                  className="h-6 w-6 text-white/30 hover:text-emerald-400 hover:bg-emerald-500/10">
                                  <DollarSign className="w-3 h-3" />
                                </Button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}

        {/* ── Prices m² ── */}
        {view.mode === 'prices-m2' && (
          <PricesM2Form
            onSuccess={() => { setView({ mode: 'list' }); refresh() }}
            onCancel={() => setView({ mode: 'list' })}
          />
        )}

        {/* ── Add estate ── */}
        {view.mode === 'add-estate' && (
          <AddEstateForm
            wallets={wallets}
            viewCurrency={viewCurrency}
            onSuccess={handleSubSuccess}
            onCancel={() => setView({ mode: 'list' })}
          />
        )}

        {/* ── Add metal ── */}
        {view.mode === 'add-metal' && (
          <AddMetalForm
            wallets={wallets}
            viewCurrency={viewCurrency}
            onSuccess={handleSubSuccess}
            onCancel={() => setView({ mode: 'list' })}
          />
        )}

        {/* ── Sell estate ── */}
        {view.mode === 'sell-estate' && (
          <SellEstateForm
            row={view.row}
            wallets={wallets}
            onSuccess={handleSubSuccess}
            onCancel={() => setView({ mode: 'list' })}
          />
        )}

        {/* ── Sell metal ── */}
        {view.mode === 'sell-metal' && (
          <SellMetalForm
            row={view.row}
            wallets={wallets}
            onSuccess={handleSubSuccess}
            onCancel={() => setView({ mode: 'list' })}
          />
        )}

      </DialogContent>
    </Dialog>
  )
}
