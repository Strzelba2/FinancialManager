'use client'

import { useMemo, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Banknote, Landmark, Plus, Save, Trash2, Wallet } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { CashCurrency } from '@/lib/types/wallet'

export type CashRow = {
  id: string
  walletId: string
  walletName: string
  name: string
  amount: string
  currency: CashCurrency
  note: string
  valueFmt: string
}

export type CashWalletOpt = {
  id: string
  name: string
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  totalFmt: string
  accountsFmt: string
  physicalFmt: string
  accountsCount: number
  cashHoldings: CashRow[]
  wallets: CashWalletOpt[]
  viewCurrency: string
}

type View =
  | { mode: 'list' }
  | { mode: 'add' }

type EditableCashRow = {
  id: string
  name: string
  amount: string
  currency: CashCurrency
  note: string
}

const CURRENCIES: readonly CashCurrency[] = ['PLN', 'USD', 'EUR', 'GBP', 'CHF']
const AMOUNT_RE = /^\d+(\.\d+)?$/

async function apiFetch(url: string, method: string, body?: unknown) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  let data: { error?: string } = {}
  try {
    data = await res.json()
  } catch {
    // ignore empty body
  }
  return { ok: res.ok, error: data.error }
}

function normalizeAmount(value: string): string {
  return value.trim().replace(/\s/g, '').replace(',', '.')
}

function validate(name: string, amount: string): string | undefined {
  if (!name.trim()) return 'Podaj nazwę pozycji'
  if (!amount.trim()) return 'Podaj kwotę'
  if (!AMOUNT_RE.test(normalizeAmount(amount))) return 'Podaj kwotę większą lub równą 0'
  return undefined
}

function isCashCurrency(value: string): value is CashCurrency {
  return (CURRENCIES as readonly string[]).includes(value)
}

function AddCashForm({
  wallets,
  viewCurrency,
  onSuccess,
  onCancel,
}: {
  wallets: CashWalletOpt[]
  viewCurrency: string
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [walletId, setWalletId] = useState(wallets[0]?.id ?? '')
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState<CashCurrency>(isCashCurrency(viewCurrency) ? viewCurrency : 'PLN')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string>()

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    const validationError = validate(name, amount)
    if (validationError) { setError(validationError); return }
    if (!walletId) { setError('Wybierz portfel'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch('/api/wallet/cash-holdings', 'POST', {
        wallet_id: walletId,
        name: name.trim(),
        amount: normalizeAmount(amount),
        currency,
        note: note.trim(),
      })
      if (!ok) { setError(err || 'Nie udało się dodać gotówki'); return }
      toast.success('Gotówka została dodana')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel} aria-label="Wróć do listy" className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <h3 className="text-base font-semibold text-white">Dodaj gotówkę</h3>
      </div>

      {wallets.length > 1 && (
        <div className="space-y-1">
          <Label htmlFor="cash-wallet" className="text-white/70 text-xs">Portfel *</Label>
          <Select value={walletId} onValueChange={setWalletId}>
            <SelectTrigger id="cash-wallet" className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {wallets.map((wallet) => <SelectItem key={wallet.id} value={wallet.id}>{wallet.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="space-y-1">
        <Label htmlFor="cash-name" className="text-white/70 text-xs">Nazwa *</Label>
        <Input id="cash-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="np. Portfel, Sejf" className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label htmlFor="cash-amount" className="text-white/70 text-xs">Kwota *</Label>
          <Input id="cash-amount" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="np. 1500" inputMode="decimal" className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="cash-currency" className="text-white/70 text-xs">Waluta *</Label>
          <Select value={currency} onValueChange={(value) => { if (isCashCurrency(value)) setCurrency(value) }}>
            <SelectTrigger id="cash-currency" className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {CURRENCIES.map((ccy) => <SelectItem key={ccy} value={ccy}>{ccy}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="cash-note" className="text-white/70 text-xs">Notatka</Label>
        <Input id="cash-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="opcjonalnie" maxLength={255} className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel} className="text-white/60 hover:text-white hover:bg-white/10">Anuluj</Button>
        <Button type="submit" disabled={isPending} className="bg-emerald-700 hover:bg-emerald-600 text-white">
          {isPending ? 'Dodawanie…' : 'Dodaj'}
        </Button>
      </div>
    </form>
  )
}

export function CashDialog({
  open,
  onOpenChange,
  totalFmt,
  accountsFmt,
  physicalFmt,
  accountsCount,
  cashHoldings,
  wallets,
  viewCurrency,
}: Props) {
  const router = useRouter()
  const initialRows = useMemo(() => cashHoldings.map((item) => ({
    id: item.id,
    name: item.name,
    amount: item.amount,
    currency: item.currency,
    note: item.note,
  })), [cashHoldings])
  const [view, setView] = useState<View>({ mode: 'list' })
  const [isPending, startTransition] = useTransition()
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ id: string; msg: string } | null>(null)
  const [rows, setRows] = useState<EditableCashRow[]>(initialRows)

  const originalById = useMemo(
    () => Object.fromEntries(cashHoldings.map((item) => [item.id, item])),
    [cashHoldings],
  )
  const showWalletColumn = wallets.length > 1

  function handleClose(next: boolean) {
    if (!next) {
      setView({ mode: 'list' })
      setConfirmDeleteId(null)
      setRowError(null)
    }
    onOpenChange(next)
  }

  function handleAddSuccess() {
    setView({ mode: 'list' })
    router.refresh()
  }

  function updateRow(id: string, patch: Partial<EditableCashRow>) {
    setRows((current) => current.map((row) => row.id === id ? { ...row, ...patch } : row))
  }

  function isRowDirty(row: EditableCashRow): boolean {
    const original = originalById[row.id]
    if (!original) return false
    return (
      row.name !== original.name ||
      row.amount !== original.amount ||
      row.currency !== original.currency ||
      row.note !== original.note
    )
  }

  function handleSave(id: string) {
    const row = rows.find((item) => item.id === id)
    if (!row) return

    const validationError = validate(row.name, row.amount)
    if (validationError) { setRowError({ id, msg: validationError }); return }
    setRowError(null)

    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/cash-holdings/${id}`, 'PUT', {
        name: row.name.trim(),
        amount: normalizeAmount(row.amount),
        currency: row.currency,
        note: row.note.trim(),
      })
      if (!ok) {
        setRowError({ id, msg: error || 'Nie udało się zaktualizować gotówki' })
        return
      }
      toast.success('Gotówka zaktualizowana')
      router.refresh()
    })
  }

  function handleDelete(id: string) {
    setRowError(null)

    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/cash-holdings/${id}`, 'DELETE')
      setConfirmDeleteId(null)
      if (!ok) {
        setRowError({ id, msg: error || 'Nie udało się usunąć pozycji gotówki' })
        return
      }
      toast.success('Pozycja gotówki usunięta')
      router.refresh()
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-md border-white/10 text-white sm:max-w-3xl max-h-[85vh] overflow-y-auto">
        {view.mode === 'add' ? (
          <AddCashForm wallets={wallets} viewCurrency={viewCurrency} onSuccess={handleAddSuccess} onCancel={() => setView({ mode: 'list' })} />
        ) : (
          <>
            <DialogHeader>
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
                  <Wallet className="w-5 h-5 text-emerald-400" />
                </div>
                <div>
                  <DialogTitle className="text-white text-lg">Szczegóły gotówki</DialogTitle>
                  <DialogDescription className="text-white/50 text-sm">
                    Łącznie: <span className="text-white font-semibold">{totalFmt}</span>
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="grid grid-cols-3 gap-3 mt-1">
              {[
                { icon: <Landmark className="w-4 h-4 text-sky-400" />, label: `Konta (${accountsCount})`, value: accountsFmt },
                { icon: <Banknote className="w-4 h-4 text-emerald-400" />, label: 'Gotówka fizyczna', value: physicalFmt },
                { icon: <Wallet className="w-4 h-4 text-amber-400" />, label: 'Pozycje', value: String(cashHoldings.length) },
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

            <div className="mt-2">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-1.5">
                  <Banknote className="w-4 h-4 text-white/40" />
                  <span className="text-sm font-medium text-white/80">Gotówka fizyczna</span>
                </div>
                <Button type="button" size="sm" variant="ghost" onClick={() => setView({ mode: 'add' })} className="h-7 text-xs text-white/60 hover:text-white hover:bg-white/10 gap-1">
                  <Plus className="w-3 h-3" /> Dodaj
                </Button>
              </div>

              {cashHoldings.length === 0 ? (
                <p className="text-xs text-white/30 py-3 text-center">Brak gotówki fizycznej w portfelu</p>
              ) : (
                <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left px-3 py-2 text-xs text-white/40 font-medium">Nazwa</th>
                        {showWalletColumn && <th className="text-left px-2 py-2 text-xs text-white/40 font-medium">Portfel</th>}
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Kwota</th>
                        <th className="text-right px-2 py-2 text-xs text-white/40 font-medium">Wartość</th>
                        <th className="text-left px-2 py-2 text-xs text-white/40 font-medium">Notatka</th>
                        <th className="w-20" />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => {
                        const original = originalById[row.id]
                        const dirty = isRowDirty(row)
                        return (
                          <tr key={row.id} className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}>
                            <td className="px-3 py-1.5 align-top">
                              {confirmDeleteId === row.id ? (
                                <span className="text-red-400 text-xs">Czy na pewno usunąć?</span>
                              ) : (
                                <>
                                  <Input
                                    aria-label="Nazwa pozycji"
                                    value={row.name}
                                    onChange={(e) => updateRow(row.id, { name: e.target.value })}
                                    className="bg-transparent border-transparent h-7 px-1 text-sm text-white focus-visible:border-white/20 focus-visible:bg-slate-700/50"
                                  />
                                  {rowError?.id === row.id && <p className="text-red-400 text-xs mt-0.5">{rowError.msg}</p>}
                                </>
                              )}
                            </td>
                            {showWalletColumn && (
                              <td className="px-2 py-1.5 align-top text-xs text-white/60 pt-3">{original?.walletName}</td>
                            )}
                            <td className="px-2 py-1.5 align-top">
                              <div className="flex items-center justify-center gap-1">
                                <Input
                                  aria-label="Kwota"
                                  value={row.amount}
                                  onChange={(e) => updateRow(row.id, { amount: e.target.value })}
                                  inputMode="decimal"
                                  className="bg-transparent border-transparent h-7 px-1 text-sm text-white text-right focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[100px]"
                                />
                                <Select value={row.currency} onValueChange={(value) => { if (isCashCurrency(value)) updateRow(row.id, { currency: value }) }}>
                                  <SelectTrigger aria-label="Waluta" className="h-7 w-[70px] bg-transparent border-transparent px-1 text-xs text-white focus:border-white/20 focus:bg-slate-700/50">
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent className="bg-slate-900 border-white/10 text-white">
                                    {CURRENCIES.map((ccy) => <SelectItem key={ccy} value={ccy}>{ccy}</SelectItem>)}
                                  </SelectContent>
                                </Select>
                              </div>
                            </td>
                            <td className="px-2 py-1.5 align-top text-right text-xs text-white/70 pt-3 whitespace-nowrap">{original?.valueFmt}</td>
                            <td className="px-2 py-1.5 align-top">
                              <Input
                                aria-label="Notatka"
                                value={row.note}
                                onChange={(e) => updateRow(row.id, { note: e.target.value })}
                                maxLength={255}
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white focus-visible:border-white/20 focus-visible:bg-slate-700/50"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-top">
                              {confirmDeleteId === row.id ? (
                                <div className="flex items-center gap-1 pl-1">
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    aria-label="Potwierdź usunięcie"
                                    onClick={() => handleDelete(row.id)}
                                    disabled={isPending}
                                    className="h-6 w-6 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </Button>
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    aria-label="Anuluj usuwanie"
                                    onClick={() => setConfirmDeleteId(null)}
                                    className="h-6 w-6 text-white/40 hover:text-white hover:bg-white/10"
                                  >
                                    ✕
                                  </Button>
                                </div>
                              ) : (
                                <div className="flex items-center gap-1 pl-1">
                                  {dirty && (
                                    <Button
                                      size="icon"
                                      variant="ghost"
                                      aria-label="Zapisz zmiany"
                                      onClick={() => handleSave(row.id)}
                                      disabled={isPending}
                                      className="h-6 w-6 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
                                    >
                                      <Save className="w-3 h-3" />
                                    </Button>
                                  )}
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    aria-label="Usuń pozycję"
                                    onClick={() => setConfirmDeleteId(row.id)}
                                    className="ml-0.5 h-6 w-6 text-white/30 hover:text-red-400 hover:bg-red-500/10"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </Button>
                                </div>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
