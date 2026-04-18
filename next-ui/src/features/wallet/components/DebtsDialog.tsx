'use client'

import { useMemo, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, CalendarDays, Landmark, Percent, Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DateTimePicker } from '@/components/ui/date-time-picker'
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
export type DebtRow = {
  id: string
  walletId: string
  walletName: string
  name: string
  lander: string
  amount: string
  currency: 'PLN' | 'USD' | 'EUR'
  interestRatePct: string
  monthlyPayment: string
  endDate: string
  amountFmt: string
  monthlyFmt: string
}

export type DebtWalletOpt = {
  id: string
  name: string
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  totalFmt: string
  subtitle: string
  countFmt: string
  avgRateFmt: string
  monthlyFmt: string
  debts: DebtRow[]
  wallets: DebtWalletOpt[]
  viewCurrency: string
}

type View =
  | { mode: 'list' }
  | { mode: 'add' }

type EditableDebtRow = {
  id: string
  name: string
  lander: string
  amount: string
  currency: 'PLN' | 'USD' | 'EUR'
  interestRatePct: string
  monthlyPayment: string
  endDateLocal: string
}

const CURRENCIES = ['PLN', 'USD', 'EUR'] as const

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

function toDateTimeLocal(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function toIsoString(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toISOString()
}

function AddDebtForm({
  wallets,
  viewCurrency,
  onSuccess,
  onCancel,
}: {
  wallets: DebtWalletOpt[]
  viewCurrency: string
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [walletId, setWalletId] = useState(wallets[0]?.id ?? '')
  const [name, setName] = useState('')
  const [lander, setLander] = useState('')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState<'PLN' | 'USD' | 'EUR'>((viewCurrency === 'USD' || viewCurrency === 'EUR') ? viewCurrency : 'PLN')
  const [interestRatePct, setInterestRatePct] = useState('0')
  const [monthlyPayment, setMonthlyPayment] = useState('0')
  const [endDate, setEndDate] = useState('')
  const [error, setError] = useState<string>()

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!name.trim()) { setError('Podaj nazwę zobowiązania'); return }
    if (!lander.trim()) { setError('Podaj nazwę wierzyciela'); return }
    if (!amount.trim()) { setError('Podaj kwotę zobowiązania'); return }
    if (!monthlyPayment.trim()) { setError('Podaj ratę miesięczną'); return }
    if (!endDate) { setError('Podaj datę końca zobowiązania'); return }
    if (!walletId) { setError('Wybierz portfel'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch('/api/wallet/debts', 'POST', {
        wallet_id: walletId,
        name: name.trim(),
        lander: lander.trim(),
        amount: amount.trim().replace(',', '.'),
        currency,
        interest_rate_pct: interestRatePct.trim().replace(',', '.'),
        monthly_payment: monthlyPayment.trim().replace(',', '.'),
        end_date: toIsoString(endDate),
      })
      if (!ok) { setError(err || 'Nie udało się dodać zobowiązania'); return }
      toast.success('Zobowiązanie zostało dodane')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel} className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <h3 className="text-base font-semibold text-white">Dodaj zobowiązanie</h3>
      </div>

      {wallets.length > 1 && (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Portfel *</Label>
          <Select value={walletId} onValueChange={setWalletId}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {wallets.map((wallet) => <SelectItem key={wallet.id} value={wallet.id}>{wallet.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Nazwa *</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="np. Kredyt hipoteczny" className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Wierzyciel *</Label>
          <Input value={lander} onChange={(e) => setLander(e.target.value)} placeholder="np. mBank" className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Kwota *</Label>
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="np. 250000" inputMode="decimal" className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Waluta *</Label>
          <Select value={currency} onValueChange={(value: 'PLN' | 'USD' | 'EUR') => setCurrency(value)}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {CURRENCIES.map((ccy) => <SelectItem key={ccy} value={ccy}>{ccy}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Oprocentowanie %</Label>
          <Input value={interestRatePct} onChange={(e) => setInterestRatePct(e.target.value)} placeholder="np. 7.2" inputMode="decimal" className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Rata miesięczna *</Label>
          <Input value={monthlyPayment} onChange={(e) => setMonthlyPayment(e.target.value)} placeholder="np. 2100" inputMode="decimal" className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm" />
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Koniec zobowiązania *</Label>
        <DateTimePicker value={endDate} onChange={setEndDate} placeholder="Wybierz datę i godzinę" />
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel} className="text-white/60 hover:text-white hover:bg-white/10">Anuluj</Button>
        <Button type="submit" disabled={isPending} className="bg-red-700 hover:bg-red-600 text-white">
          {isPending ? 'Dodawanie…' : 'Dodaj'}
        </Button>
      </div>
    </form>
  )
}

export function DebtsDialog({
  open,
  onOpenChange,
  totalFmt,
  subtitle,
  countFmt,
  avgRateFmt,
  monthlyFmt,
  debts,
  wallets,
  viewCurrency,
}: Props) {
  const router = useRouter()
  const initialRows = useMemo(() => debts.map((debt) => ({
    id: debt.id,
    name: debt.name,
    lander: debt.lander,
    amount: debt.amount,
    currency: debt.currency,
    interestRatePct: debt.interestRatePct,
    monthlyPayment: debt.monthlyPayment,
    endDateLocal: toDateTimeLocal(debt.endDate),
  })), [debts])
  const [view, setView] = useState<View>({ mode: 'list' })
  const [isPending, startTransition] = useTransition()
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ id: string; msg: string } | null>(null)
  const [rows, setRows] = useState<EditableDebtRow[]>(initialRows)

  const originalById = useMemo(
    () => Object.fromEntries(debts.map((debt) => [debt.id, debt])),
    [debts],
  )

  function handleClose(next: boolean) {
    if (!next) {
      setView({ mode: 'list' })
      setDeletingId(null)
      setRowError(null)
    }
    onOpenChange(next)
  }

  function refresh() {
    router.refresh()
  }

  function handleAddSuccess() {
    setView({ mode: 'list' })
    refresh()
  }

  function updateRow(id: string, patch: Partial<EditableDebtRow>) {
    setRows((current) => current.map((row) => row.id === id ? { ...row, ...patch } : row))
  }

  function isRowDirty(row: EditableDebtRow): boolean {
    const original = originalById[row.id]
    if (!original) return false

    return (
      row.name !== original.name ||
      row.lander !== original.lander ||
      row.amount !== original.amount ||
      row.currency !== original.currency ||
      row.interestRatePct !== original.interestRatePct ||
      row.monthlyPayment !== original.monthlyPayment ||
      row.endDateLocal !== toDateTimeLocal(original.endDate)
    )
  }

  function handleSave(id: string) {
    const row = rows.find((item) => item.id === id)
    if (!row) return

    if (!row.name.trim()) { setRowError({ id, msg: 'Podaj nazwę zobowiązania' }); return }
    if (!row.lander.trim()) { setRowError({ id, msg: 'Podaj nazwę wierzyciela' }); return }
    if (!row.amount.trim()) { setRowError({ id, msg: 'Podaj kwotę zobowiązania' }); return }
    if (!row.monthlyPayment.trim()) { setRowError({ id, msg: 'Podaj ratę miesięczną' }); return }
    if (!row.endDateLocal.trim()) { setRowError({ id, msg: 'Podaj datę końca zobowiązania' }); return }
    setRowError(null)

    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/debts/${id}`, 'PUT', {
        name: row.name.trim(),
        lander: row.lander.trim(),
        amount: row.amount.trim().replace(',', '.'),
        currency: row.currency,
        interest_rate_pct: row.interestRatePct.trim().replace(',', '.'),
        monthly_payment: row.monthlyPayment.trim().replace(',', '.'),
        end_date: toIsoString(row.endDateLocal),
      })

      if (!ok) {
        setRowError({ id, msg: error || 'Nie udało się zaktualizować zobowiązania' })
        return
      }

      toast.success('Zobowiązanie zaktualizowane')
      refresh()
    })
  }

  function handleDelete(id: string) {
    setRowError(null)
    setDeletingId(id)

    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/debts/${id}`, 'DELETE')
      setDeletingId(null)
      if (!ok) {
        setRowError({ id, msg: error || 'Nie udało się usunąć zobowiązania' })
        return
      }

      toast.success('Zobowiązanie usunięte')
      refresh()
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-md border-white/10 text-white sm:max-w-4xl max-h-[85vh] overflow-y-auto">
        {view.mode === 'add' ? (
          <AddDebtForm wallets={wallets} viewCurrency={viewCurrency} onSuccess={handleAddSuccess} onCancel={() => setView({ mode: 'list' })} />
        ) : (
          <>
            <DialogHeader>
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-full bg-red-500/15 border border-red-500/30">
                  <Landmark className="w-5 h-5 text-red-400" />
                </div>
                <div>
                  <DialogTitle className="text-white text-lg">Szczegóły zobowiązań</DialogTitle>
                  <DialogDescription className="text-white/50 text-sm">
                    Łącznie: <span className="text-white font-semibold">{totalFmt}</span>
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="grid grid-cols-3 gap-3 mt-1">
              {[
                { icon: <Landmark className="w-4 h-4 text-red-400" />, label: 'Liczba', value: countFmt },
                { icon: <Percent className="w-4 h-4 text-amber-400" />, label: 'Śr. oproc.', value: avgRateFmt },
                { icon: <CalendarDays className="w-4 h-4 text-sky-400" />, label: 'Rata', value: monthlyFmt },
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
                  <Landmark className="w-4 h-4 text-white/40" />
                  <span className="text-sm font-medium text-white/80">Zobowiązania</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-white/45 hidden sm:inline">{subtitle}</span>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setView({ mode: 'add' })} className="h-7 text-xs text-white/60 hover:text-white hover:bg-white/10 gap-1">
                    <Plus className="w-3 h-3" /> Dodaj
                  </Button>
                </div>
              </div>

              {debts.length === 0 ? (
                <p className="text-xs text-white/30 py-3 text-center">Brak zobowiązań w portfelu</p>
              ) : (
                <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left px-3 py-2 text-xs text-white/40 font-medium">Nazwa</th>
                        <th className="text-left px-2 py-2 text-xs text-white/40 font-medium">Wierzyciel</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Kwota</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Oproc. %</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Rata</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Koniec</th>
                        <th className="w-24" />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => {
                        const dirty = isRowDirty(row)
                        return (
                          <tr key={row.id} className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}>
                            <td className="px-3 py-1.5 align-top">
                              {deletingId === row.id ? (
                                <span className="text-red-400 text-xs">Czy na pewno usunąć?</span>
                              ) : (
                                <>
                                  <Input
                                    value={row.name}
                                    onChange={(e) => updateRow(row.id, { name: e.target.value })}
                                    className="bg-transparent border-transparent h-7 px-1 text-sm text-white focus-visible:border-white/20 focus-visible:bg-slate-700/50"
                                  />
                                  {rowError?.id === row.id && <p className="text-red-400 text-xs mt-0.5">{rowError.msg}</p>}
                                </>
                              )}
                            </td>
                            <td className="px-2 py-1.5 align-top">
                              <Input
                                value={row.lander}
                                onChange={(e) => updateRow(row.id, { lander: e.target.value })}
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white focus-visible:border-white/20 focus-visible:bg-slate-700/50"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-top">
                              <div className="flex items-center justify-center gap-1">
                                <Input
                                  value={row.amount}
                                  onChange={(e) => updateRow(row.id, { amount: e.target.value })}
                                  inputMode="decimal"
                                  className="bg-transparent border-transparent h-7 px-1 text-sm text-white text-right focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[92px]"
                                />
                                <Select value={row.currency} onValueChange={(value: 'PLN' | 'USD' | 'EUR') => updateRow(row.id, { currency: value })}>
                                  <SelectTrigger className="h-7 w-[70px] bg-transparent border-transparent px-1 text-xs text-white focus:border-white/20 focus:bg-slate-700/50">
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent className="bg-slate-900 border-white/10 text-white">
                                    {CURRENCIES.map((ccy) => <SelectItem key={ccy} value={ccy}>{ccy}</SelectItem>)}
                                  </SelectContent>
                                </Select>
                              </div>
                            </td>
                            <td className="px-2 py-1.5 align-top">
                              <Input
                                value={row.interestRatePct}
                                onChange={(e) => updateRow(row.id, { interestRatePct: e.target.value })}
                                inputMode="decimal"
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white text-center focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[72px] mx-auto"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-top">
                              <Input
                                value={row.monthlyPayment}
                                onChange={(e) => updateRow(row.id, { monthlyPayment: e.target.value })}
                                inputMode="decimal"
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white text-center focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[92px] mx-auto"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-top">
                              <DateTimePicker
                                value={row.endDateLocal}
                                onChange={(next) => updateRow(row.id, { endDateLocal: next })}
                                placeholder="Data"
                                variant="inline"
                                className="text-center"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-top">
                              {deletingId === row.id ? (
                                <div className="flex items-center gap-1 pl-1">
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    onClick={() => handleDelete(row.id)}
                                    disabled={isPending}
                                    className="h-6 w-6 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </Button>
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    onClick={() => setDeletingId(null)}
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
                                    onClick={() => setDeletingId(row.id)}
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
