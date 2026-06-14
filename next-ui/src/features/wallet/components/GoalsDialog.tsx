'use client'

import { useMemo, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Plus, Save, Target, Trash2 } from 'lucide-react'
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
import type { YearGoalOut } from '@/lib/types/wallet'

export type GoalWalletOpt = {
  id: string
  name: string
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialGoals: YearGoalOut[]
  wallets: GoalWalletOpt[]
  viewCurrency: string
}

type View = { mode: 'list' } | { mode: 'add' }

type EditableGoalRow = {
  id: string
  wallet_id: string
  year: number
  currency: 'PLN' | 'USD' | 'EUR'
  rev_target_year: string
  exp_budget_year: string
  capital_gain_target_year: string
}

const CURRENCIES = ['PLN', 'USD', 'EUR'] as const
const CURRENT_YEAR = new Date().getFullYear()
const YEARS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2] as const

async function apiFetch(url: string, method: string, body?: unknown) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  let data: { error?: string } = {}
  try {
    data = await res.json()
  } catch { /* empty body */ }
  return { ok: res.ok, error: data.error }
}

function AddGoalForm({
  wallets,
  onSuccess,
  onCancel,
}: {
  wallets: GoalWalletOpt[]
  onSuccess: () => void
  onCancel: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [walletId, setWalletId] = useState(wallets[0]?.id ?? '')
  const [year, setYear] = useState<number>(CURRENT_YEAR)
  const [currency, setCurrency] = useState<'PLN' | 'USD' | 'EUR'>('PLN')
  const [revTarget, setRevTarget] = useState('')
  const [expBudget, setExpBudget] = useState('')
  const [capTarget, setCapTarget] = useState('')
  const [error, setError] = useState<string>()

  function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!walletId) { setError('Wybierz portfel'); return }
    if (!revTarget.trim()) { setError('Podaj cel przychodów'); return }
    if (!expBudget.trim()) { setError('Podaj budżet wydatków'); return }
    const rev = parseFloat(revTarget.replace(',', '.'))
    const exp = parseFloat(expBudget.replace(',', '.'))
    const cap = capTarget.trim() ? parseFloat(capTarget.replace(',', '.')) : 0
    if (!Number.isFinite(rev) || rev <= 0) { setError('Cel przychodów musi być liczbą > 0'); return }
    if (!Number.isFinite(exp) || exp <= 0) { setError('Budżet wydatków musi być liczbą > 0'); return }
    if (!Number.isFinite(cap) || cap < 0) { setError('Cel zysku kapitałowego musi być liczbą ≥ 0'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiFetch('/api/wallet/goals', 'POST', {
        wallet_id: walletId,
        year,
        rev_target_year: rev.toFixed(2),
        exp_budget_year: exp.toFixed(2),
        capital_gain_target_year: cap.toFixed(2),
        currency,
      })
      if (!ok) { setError(err || 'Nie udało się zapisać celu'); return }
      toast.success('Cel został zapisany')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Button type="button" size="icon" variant="ghost" onClick={onCancel} className="text-white/60 hover:text-white h-7 w-7">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <h3 className="text-base font-semibold text-white">Dodaj / zaktualizuj cel</h3>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {wallets.length > 1 && (
          <div className="space-y-1 col-span-3 sm:col-span-1">
            <Label className="text-white/70 text-xs">Portfel *</Label>
            <Select value={walletId} onValueChange={setWalletId}>
              <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-900 border-white/10 text-white">
                {wallets.map((w) => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Rok *</Label>
          <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {YEARS.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
            </SelectContent>
          </Select>
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
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Cel przychodów *</Label>
          <Input
            value={revTarget}
            onChange={(e) => setRevTarget(e.target.value)}
            placeholder="np. 120000"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Budżet wydatków *</Label>
          <Input
            value={expBudget}
            onChange={(e) => setExpBudget(e.target.value)}
            placeholder="np. 80000"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Cel zysku kap.</Label>
          <Input
            value={capTarget}
            onChange={(e) => setCapTarget(e.target.value)}
            placeholder="np. 24000"
            inputMode="decimal"
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
          {isPending ? 'Zapisywanie…' : 'Zapisz'}
        </Button>
      </div>
    </form>
  )
}

export function GoalsDialog({ open, onOpenChange, initialGoals, wallets, viewCurrency }: Props) {
  const router = useRouter()

  const walletNameById = useMemo(
    () => Object.fromEntries(wallets.map((w) => [w.id, w.name])),
    [wallets],
  )

  const initialRows: EditableGoalRow[] = useMemo(
    () =>
      [...initialGoals]
        .sort((a, b) => {
          const wa = walletNameById[a.wallet_id] ?? ''
          const wb = walletNameById[b.wallet_id] ?? ''
          return wa.localeCompare(wb) || b.year - a.year
        })
        .map((g) => ({
          id: g.id,
          wallet_id: g.wallet_id,
          year: g.year,
          currency: g.currency,
          rev_target_year: g.rev_target_year,
          exp_budget_year: g.exp_budget_year,
          capital_gain_target_year: g.capital_gain_target_year ?? '0.00',
        })),
    [initialGoals, walletNameById],
  )

  const [view, setView] = useState<View>({ mode: 'list' })
  const [isPending, startTransition] = useTransition()
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ id: string; msg: string } | null>(null)
  const [rows, setRows] = useState<EditableGoalRow[]>(initialRows)

  const originalById = useMemo(
    () => Object.fromEntries(initialGoals.map((g) => [g.id, g])),
    [initialGoals],
  )

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

  function updateRow(
    id: string,
    patch: Partial<Pick<EditableGoalRow, 'rev_target_year' | 'exp_budget_year' | 'capital_gain_target_year'>>,
  ) {
    setRows((cur) => cur.map((r) => r.id === id ? { ...r, ...patch } : r))
  }

  function isRowDirty(row: EditableGoalRow): boolean {
    const orig = originalById[row.id]
    if (!orig) return false
    return row.rev_target_year !== orig.rev_target_year
      || row.exp_budget_year !== orig.exp_budget_year
      || row.capital_gain_target_year !== (orig.capital_gain_target_year ?? '0.00')
  }

  function handleSave(id: string) {
    const row = rows.find((r) => r.id === id)
    if (!row) return
    const rev = parseFloat(row.rev_target_year.replace(',', '.'))
    const exp = parseFloat(row.exp_budget_year.replace(',', '.'))
    const cap = parseFloat(row.capital_gain_target_year.replace(',', '.'))
    if (!Number.isFinite(rev) || rev <= 0) { setRowError({ id, msg: 'Cel przychodów musi być > 0' }); return }
    if (!Number.isFinite(exp) || exp <= 0) { setRowError({ id, msg: 'Budżet wydatków musi być > 0' }); return }
    if (!Number.isFinite(cap) || cap < 0) { setRowError({ id, msg: 'Cel zysku kapitałowego musi być ≥ 0' }); return }
    setRowError(null)

    startTransition(async () => {
      const { ok, error } = await apiFetch('/api/wallet/goals', 'POST', {
        wallet_id: row.wallet_id,
        year: row.year,
        currency: row.currency,
        rev_target_year: rev.toFixed(2),
        exp_budget_year: exp.toFixed(2),
        capital_gain_target_year: cap.toFixed(2),
      })
      if (!ok) { setRowError({ id, msg: error || 'Nie udało się zaktualizować celu' }); return }
      toast.success('Cel zaktualizowany')
      refresh()
    })
  }

  function handleDelete(id: string) {
    setRowError(null)
    setDeletingId(id)
    startTransition(async () => {
      const { ok, error } = await apiFetch(`/api/wallet/goals/${id}`, 'DELETE')
      setDeletingId(null)
      if (!ok) { setRowError({ id, msg: error || 'Nie udało się usunąć celu' }); return }
      toast.success('Cel usunięty')
      refresh()
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-md border-white/10 text-white sm:max-w-4xl max-h-[85vh] overflow-y-auto">
        {view.mode === 'add' ? (
          <AddGoalForm
            wallets={wallets}
            onSuccess={handleAddSuccess}
            onCancel={() => setView({ mode: 'list' })}
          />
        ) : (
          <>
            <DialogHeader>
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
                  <Target className="w-5 h-5 text-emerald-400" />
                </div>
                <div>
                  <DialogTitle className="text-white text-lg">Cele roczne</DialogTitle>
                  <DialogDescription className="text-white/50 text-sm">
                    Zarządzaj celami przychodów, budżetami wydatków i zyskiem kapitałowym
                    {viewCurrency ? ` · widok: ${viewCurrency}` : ''}
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="mt-2">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-1.5">
                  <Target className="w-4 h-4 text-white/40" />
                  <span className="text-sm font-medium text-white/80">
                    {rows.length === 0 ? 'Brak celów' : `${rows.length} ${rows.length === 1 ? 'cel' : rows.length <= 4 ? 'cele' : 'celów'}`}
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
                  Brak celów. Kliknij &quot;Dodaj&quot; aby ustawić cel.
                </p>
              ) : (
                <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-x-auto">
                  <table className="w-full min-w-[760px] text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left px-3 py-2 text-xs text-white/40 font-medium">Portfel</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Rok</th>
                        <th className="text-center px-2 py-2 text-xs text-white/40 font-medium">Waluta</th>
                        <th className="text-right px-2 py-2 text-xs text-white/40 font-medium">Cel przychodu</th>
                        <th className="text-right px-2 py-2 text-xs text-white/40 font-medium">Budżet wydatków</th>
                        <th className="text-right px-2 py-2 text-xs text-white/40 font-medium">Cel zysku kap.</th>
                        <th className="w-20" />
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
                            <td className="px-3 py-1.5 align-middle">
                              {deletingId === row.id ? (
                                <span className="text-red-400 text-xs">Czy na pewno usunąć?</span>
                              ) : (
                                <>
                                  <span className="text-white/80 text-sm">
                                    {walletNameById[row.wallet_id] ?? '—'}
                                  </span>
                                  {rowError?.id === row.id && (
                                    <p className="text-red-400 text-xs mt-0.5">{rowError.msg}</p>
                                  )}
                                </>
                              )}
                            </td>
                            <td className="px-2 py-1.5 text-center text-white/60 text-sm align-middle">
                              {row.year}
                            </td>
                            <td className="px-2 py-1.5 text-center text-white/60 text-xs align-middle">
                              {row.currency}
                            </td>
                            <td className="px-2 py-1.5 align-middle">
                              <Input
                                value={row.rev_target_year}
                                onChange={(e) => updateRow(row.id, { rev_target_year: e.target.value })}
                                inputMode="decimal"
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white text-right focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[110px] ml-auto"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-middle">
                              <Input
                                value={row.exp_budget_year}
                                onChange={(e) => updateRow(row.id, { exp_budget_year: e.target.value })}
                                inputMode="decimal"
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white text-right focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[110px] ml-auto"
                              />
                            </td>
                            <td className="px-2 py-1.5 align-middle">
                              <Input
                                value={row.capital_gain_target_year}
                                onChange={(e) => updateRow(row.id, { capital_gain_target_year: e.target.value })}
                                inputMode="decimal"
                                className="bg-transparent border-transparent h-7 px-1 text-sm text-white text-right focus-visible:border-white/20 focus-visible:bg-slate-700/50 max-w-[110px] ml-auto"
                              />
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
