'use client'

import { useMemo, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Plus, Receipt, Save, Trash2 } from 'lucide-react'
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
import type { RecurringExpenseOut } from '@/lib/types/wallet'

export type ExpenseWalletOpt = {
  id: string
  name: string
  accounts: ExpenseAccountOpt[]
}

export type ExpenseAccountOpt = {
  id: string
  name: string
  currency: 'PLN' | 'USD' | 'EUR'
  accountType: string
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialExpenses: RecurringExpenseOut[]
  wallets: ExpenseWalletOpt[]
  viewCurrency: string
}

type View = { mode: 'list' } | { mode: 'add' }

type EditableRow = RecurringExpenseOut & {
  _name: string
  _category: string
  _amount: string
  _currency: 'PLN' | 'USD' | 'EUR'
  _due_day: string
  _account: string
  _note: string
}

const CURRENCIES = ['PLN', 'USD', 'EUR'] as const
const NONE_SELECT_VALUE = '__none__'
const DEFAULT_CATEGORY_OPTIONS = [
  'Mieszkanie',
  'Rachunki',
  'Żywność',
  'Transport',
  'Paliwo',
  'Zdrowie',
  'Ubezpieczenia',
  'Subskrypcje',
  'Telefon',
  'Internet',
  'Edukacja',
  'Sport',
  'Dzieci',
  'Prezenty',
  'Podatki',
  'Inne',
]

type SelectOption = { value: string; label: string }

function uniqueTextOptions(values: string[]): SelectOption[] {
  const byValue = new Map<string, SelectOption>()
  for (const raw of values) {
    const value = raw.trim()
    if (!value || byValue.has(value)) continue
    byValue.set(value, { value, label: value })
  }
  return [...byValue.values()]
}

function categoryOptions(expenses: RecurringExpenseOut[]): SelectOption[] {
  return uniqueTextOptions([
    ...DEFAULT_CATEGORY_OPTIONS,
    ...expenses.map((expense) => expense.category ?? ''),
  ])
}

function accountOptionsForWallet(wallets: ExpenseWalletOpt[], walletId: string): SelectOption[] {
  const wallet = wallets.find((item) => item.id === walletId)
  if (!wallet) return []
  const byName = new Map<string, SelectOption>()
  for (const account of wallet.accounts) {
    if (account.accountType === 'BROKERAGE') continue
    const name = account.name.trim()
    if (!name || byName.has(name)) continue
    byName.set(name, { value: name, label: `${name} · ${account.currency}` })
  }
  return [...byName.values()]
}

async function apiFetch(url: string, method: string, body?: unknown) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  let data: { error?: string } = {}
  try { data = await res.json() } catch { /* empty body */ }
  return { ok: res.ok, error: data.error }
}

function AddExpenseForm({
  wallets,
  categories,
  viewCurrency,
  onSuccess,
  onCancel,
}: {
  wallets: ExpenseWalletOpt[]
  categories: SelectOption[]
  viewCurrency: string
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [walletId, setWalletId] = useState(wallets[0]?.id ?? '')
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState<'PLN' | 'USD' | 'EUR'>(
    (CURRENCIES.includes(viewCurrency as 'PLN' | 'USD' | 'EUR') ? viewCurrency : 'PLN') as 'PLN' | 'USD' | 'EUR'
  )
  const [dueDay, setDueDay] = useState('')
  const [account, setAccount] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string>()
  const accountOptions = useMemo(() => accountOptionsForWallet(wallets, walletId), [walletId, wallets])

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!walletId) { setError('Wybierz portfel'); return }
    const nm = name.trim()
    if (!nm) { setError('Podaj nazwę wydatku'); return }
    const amt = parseFloat(amount.replace(',', '.'))
    if (!Number.isFinite(amt) || amt <= 0) { setError('Kwota musi być liczbą > 0'); return }
    const dd = parseInt(dueDay, 10)
    if (!Number.isFinite(dd) || dd < 1 || dd > 31) { setError('Dzień musi być w zakresie 1–31'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch('/api/wallet/recurring-expenses', 'POST', {
        wallet_id: walletId,
        name: nm,
        category: category.trim() || undefined,
        amount: amt.toFixed(2),
        currency,
        due_day: dd,
        account: account.trim() || undefined,
        note: note.trim() || undefined,
      })
      if (!ok) { setError(err || 'Nie udało się dodać wydatku'); return }
      toast.success('Wydatek dodany')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel} className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <h3 className="text-base font-semibold text-white">Dodaj stały wydatek</h3>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {wallets.length > 1 && (
          <div className="space-y-1 col-span-2">
            <Label className="text-white/70 text-xs">Portfel *</Label>
            <Select value={walletId} onValueChange={(value) => { setWalletId(value); setAccount('') }}>
              <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-900 border-white/10 text-white">
                {wallets.map((w) => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="space-y-1 col-span-2">
          <Label className="text-white/70 text-xs">Nazwa *</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="np. Czynsz"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>

        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Kategoria</Label>
          <Select value={category || NONE_SELECT_VALUE} onValueChange={(value) => setCategory(value === NONE_SELECT_VALUE ? '' : value)}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue placeholder="Wybierz kategorię" />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              <SelectItem value={NONE_SELECT_VALUE}>Brak kategorii</SelectItem>
              {categories.map((option) => (
                <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Konto</Label>
          <Select value={account || NONE_SELECT_VALUE} onValueChange={(value) => setAccount(value === NONE_SELECT_VALUE ? '' : value)}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue placeholder="Wybierz konto" />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              <SelectItem value={NONE_SELECT_VALUE}>Brak konta</SelectItem>
              {accountOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Kwota *</Label>
          <Input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="np. 1800"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>

        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Waluta *</Label>
          <Select value={currency} onValueChange={(v: 'PLN' | 'USD' | 'EUR') => setCurrency(v)}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Dzień miesiąca * (1–31)</Label>
          <Input
            value={dueDay}
            onChange={(e) => setDueDay(e.target.value)}
            placeholder="np. 10"
            inputMode="numeric"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>

        <div className="space-y-1 col-span-2">
          <Label className="text-white/70 text-xs">Notatka</Label>
          <Input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="opcjonalnie"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel} className="text-white/60 hover:text-white hover:bg-white/10">
          Anuluj
        </Button>
        <Button type="submit" disabled={isPending} className="bg-emerald-700 hover:bg-emerald-600 text-white">
          {isPending ? 'Zapisywanie…' : 'Dodaj'}
        </Button>
      </div>
    </form>
  )
}

function toEditableRow(e: RecurringExpenseOut): EditableRow {
  return {
    ...e,
    _name: e.name,
    _category: e.category ?? '',
    _amount: e.amount,
    _currency: e.currency,
    _due_day: String(e.due_day),
    _account: e.account ?? '',
    _note: e.note ?? '',
  }
}

export function RecurringExpensesDialog({
  open,
  onOpenChange,
  initialExpenses,
  wallets,
  viewCurrency,
}: Props) {
  const router = useRouter()

  const walletNameById = useMemo(
    () => Object.fromEntries(wallets.map((w) => [w.id, w.name])),
    [wallets],
  )

  const initialRows: EditableRow[] = useMemo(
    () =>
      [...initialExpenses]
        .sort((a, b) => a.due_day - b.due_day)
        .map(toEditableRow),
    [initialExpenses],
  )
  const categories = useMemo(() => categoryOptions(initialExpenses), [initialExpenses])

  const originalById = useMemo(
    () => Object.fromEntries(initialExpenses.map((e) => [e.id, e])),
    [initialExpenses],
  )

  const [view, setView] = useState<View>({ mode: 'list' })
  const [isPending, startTransition] = useTransition()
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ id: string; msg: string } | null>(null)
  const [rows, setRows] = useState<EditableRow[]>(initialRows)

  function handleClose(next: boolean) {
    if (!next) {
      setView({ mode: 'list' })
      setDeletingId(null)
      setRowError(null)
    }
    onOpenChange(next)
  }

  function refresh() { router.refresh() }

  function handleAddSuccess() {
    setView({ mode: 'list' })
    refresh()
  }

  function updateRow(id: string, patch: Partial<Pick<EditableRow, '_name' | '_category' | '_amount' | '_currency' | '_due_day' | '_account' | '_note'>>) {
    setRows((cur) => cur.map((r) => r.id === id ? { ...r, ...patch } : r))
  }

  function isRowDirty(row: EditableRow): boolean {
    const orig = originalById[row.id]
    if (!orig) return false
    return (
      row._name !== orig.name ||
      row._category !== (orig.category ?? '') ||
      row._amount !== orig.amount ||
      row._currency !== orig.currency ||
      row._due_day !== String(orig.due_day) ||
      row._account !== (orig.account ?? '') ||
      row._note !== (orig.note ?? '')
    )
  }

  function handleSave(id: string) {
    const row = rows.find((r) => r.id === id)
    if (!row) return
    const nm = row._name.trim()
    if (!nm) { setRowError({ id, msg: 'Nazwa nie może być pusta' }); return }
    const amt = parseFloat(row._amount.replace(',', '.'))
    if (!Number.isFinite(amt) || amt <= 0) { setRowError({ id, msg: 'Kwota musi być > 0' }); return }
    const dd = parseInt(row._due_day, 10)
    if (!Number.isFinite(dd) || dd < 1 || dd > 31) { setRowError({ id, msg: 'Dzień musi być 1–31' }); return }
    setRowError(null)

    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/recurring-expenses/${id}`, 'PUT', {
        name: nm,
        category: row._category.trim() || undefined,
        amount: amt.toFixed(2),
        currency: row._currency,
        due_day: dd,
        account: row._account.trim() || undefined,
        note: row._note.trim() || undefined,
      })
      if (!ok) { setRowError({ id, msg: error || 'Nie udało się zapisać' }); return }
      toast.success('Wydatek zaktualizowany')
      refresh()
    })
  }

  function handleDelete(id: string) {
    setRowError(null)
    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/recurring-expenses/${id}`, 'DELETE')
      setDeletingId(null)
      if (!ok) { setRowError({ id, msg: error || 'Nie udało się usunąć' }); return }
      toast.success('Wydatek usunięty')
      refresh()
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-md border-white/10 text-white sm:max-w-3xl max-h-[85vh] overflow-y-auto">
        {view.mode === 'add' ? (
          <AddExpenseForm
            wallets={wallets}
            categories={categories}
            viewCurrency={viewCurrency}
            onSuccess={handleAddSuccess}
            onCancel={() => setView({ mode: 'list' })}
          />
        ) : (
          <>
            <DialogHeader>
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-full bg-blue-500/15 border border-blue-500/30">
                  <Receipt className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <DialogTitle className="text-white text-lg">Stałe miesięczne wydatki</DialogTitle>
                  <DialogDescription className="text-white/50 text-sm">
                    Zarządzaj stałymi opłatami miesięcznymi
                    {viewCurrency ? ` · widok: ${viewCurrency}` : ''}
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="mt-2">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-1.5">
                  <Receipt className="w-4 h-4 text-white/40" />
                  <span className="text-sm font-medium text-white/80">
                    {rows.length === 0
                      ? 'Brak wydatków'
                      : `${rows.length} ${rows.length === 1 ? 'wydatek' : rows.length <= 4 ? 'wydatki' : 'wydatków'}`}
                  </span>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setView({ mode: 'add' })}
                  className="h-7 text-xs text-white/60 hover:text-white hover:bg-white/10 gap-1"
                >
                  <Plus className="w-3 h-3" /> Dodaj
                </Button>
              </div>

              {rows.length === 0 ? (
                <p className="text-xs text-white/30 py-6 text-center">
                  Brak stałych wydatków. Kliknij &quot;Dodaj&quot; aby dodać.
                </p>
              ) : (
                <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left px-3 py-2 text-xs text-white/40 font-medium">Portfel</th>
                        <th className="text-left px-2 py-2 text-xs text-white/40 font-medium">Nazwa</th>
                        <th className="text-left px-2 py-2 text-xs text-white/40 font-medium hidden md:table-cell">Kategoria</th>
                        <th className="text-right px-2 py-2 text-xs text-white/40 font-medium">Kwota</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium w-[44px]">Waluta</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium w-[44px]">Dzień</th>
                        <th className="text-left px-2 py-2 text-xs text-white/40 font-medium hidden lg:table-cell">Konto</th>
                        <th className="w-16" />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => {
                        const dirty = isRowDirty(row)
                        return (
                          <tr
                            key={row.id}
                            className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}
                          >
                            <td className="px-3 py-1.5 align-middle text-xs text-white/40">
                              {walletNameById[row.wallet_id] ?? '—'}
                            </td>
                            <td className="px-2 py-1.5 align-middle">
                              {deletingId === row.id ? (
                                <span className="text-red-400 text-xs">Czy usunąć?</span>
                              ) : (
                                <>
                                  <Input
                                    value={row._name}
                                    onChange={(e) => updateRow(row.id, { _name: e.target.value })}
                                    className="bg-transparent border-transparent h-7 px-1 text-xs text-white focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[120px]"
                                  />
                                  {rowError?.id === row.id && (
                                    <p className="text-red-400 text-[10px] mt-0.5">{rowError.msg}</p>
                                  )}
                                </>
                              )}
                            </td>
                            <td className="px-2 py-1.5 align-middle hidden md:table-cell">
                              <Select
                                value={row._category || NONE_SELECT_VALUE}
                                onValueChange={(value) => updateRow(row.id, { _category: value === NONE_SELECT_VALUE ? '' : value })}
                              >
                                <SelectTrigger className="bg-transparent border-transparent h-7 px-1 text-xs text-white/60 focus:ring-0 w-[128px]">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-white/10 text-white">
                                  <SelectItem value={NONE_SELECT_VALUE}>Brak kategorii</SelectItem>
                                  {categories.map((option) => (
                                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </td>
                            <td className="px-2 py-1.5 align-middle">
                              <Input
                                value={row._amount}
                                onChange={(e) => updateRow(row.id, { _amount: e.target.value })}
                                inputMode="decimal"
                                className="bg-transparent border-transparent h-7 px-1 text-xs text-white text-right focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[80px] ml-auto"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-middle">
                              <Select
                                value={row._currency}
                                onValueChange={(v: 'PLN' | 'USD' | 'EUR') => updateRow(row.id, { _currency: v })}
                              >
                                <SelectTrigger className="bg-transparent border-transparent h-7 px-1 text-xs text-white/60 focus:ring-0 w-[56px]">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-white/10 text-white">
                                  {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                                </SelectContent>
                              </Select>
                            </td>
                            <td className="px-2 py-1.5 align-middle">
                              <Input
                                value={row._due_day}
                                onChange={(e) => updateRow(row.id, { _due_day: e.target.value })}
                                inputMode="numeric"
                                className="bg-transparent border-transparent h-7 px-1 text-xs text-white text-center focus-visible:border-white/20 focus-visible:bg-slate-700/50 w-[40px] mx-auto"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-middle hidden lg:table-cell">
                              <Select
                                value={row._account || NONE_SELECT_VALUE}
                                onValueChange={(value) => updateRow(row.id, { _account: value === NONE_SELECT_VALUE ? '' : value })}
                              >
                                <SelectTrigger className="bg-transparent border-transparent h-7 px-1 text-xs text-white/50 focus:ring-0 w-[132px]">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-white/10 text-white">
                                  <SelectItem value={NONE_SELECT_VALUE}>Brak konta</SelectItem>
                                  {accountOptionsForWallet(wallets, row.wallet_id).map((option) => (
                                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </td>
                            <td className="px-2 py-1.5 align-middle">
                              {deletingId === row.id ? (
                                <div className="flex items-center gap-1 justify-end">
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
                                <div className="flex items-center gap-1 justify-end">
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
                                    className="h-6 w-6 text-white/30 hover:text-red-400 hover:bg-red-500/10"
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
