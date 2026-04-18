'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  ChevronDown, ChevronRight, Camera, RefreshCw,
  AlertTriangle, Eye,
} from 'lucide-react'
import type {
  WalletManagerNode,
  ManagerDepositAccount,
  ManagerBrokerageAccount,
  ManagerMetals,
  ManagerRealEstate,
  ManagerHealth,
} from '@/lib/api/wallet'
import type { FxRates } from '@/lib/api/nbp'

type ViewCcy = 'PLN' | 'USD' | 'EUR'

function toNum(v: string | number | null | undefined): number {
  if (v === null || v === undefined) return 0
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  return isNaN(n) ? 0 : n
}

function makeConv(fxRates: FxRates | null) {
  return (amount: number, from: string, to: string): number => {
    if (from === to || !fxRates) return amount
    const key = `${from}/${to}` as keyof FxRates
    if (fxRates[key]) return amount * fxRates[key]
    const invKey = `${to}/${from}` as keyof FxRates
    if (fxRates[invKey]) return amount / fxRates[invKey]
    return amount
  }
}

function currentMonthKey(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function prevMonthKey(key: string): string {
  const parts = key.split('-')
  const y = Number(parts[0])
  const m = Number(parts[1])
  if (m === 1) return `${y - 1}-12`
  return `${y}-${String(m - 1).padStart(2, '0')}`
}

function pctChange(cur: number, prev: number | null): number | null {
  if (prev === null || prev === 0) return null
  return ((cur - prev) / prev) * 100
}

function fmtMoney(v: number | null, ccy: string): string {
  if (v === null) return '—'
  return (
    v.toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) +
    '\u00a0' + ccy
  )
}

function fmtPct(v: number): string {
  return (v >= 0 ? '+' : '') + v.toFixed(1) + '%'
}

type Breakdown = {
  cashDeposit: number
  cashBroker: number
  stocks: number
  metals: number
  realEstate: number
  total: number
}

function walletBreakdown(
  w: WalletManagerNode,
  viewCcy: ViewCcy,
  conv: (a: number, f: string, t: string) => number,
): Breakdown {
  let cashDeposit = 0, cashBroker = 0, stocks = 0, metals = 0, realEstate = 0

  for (const a of w.deposit_accounts ?? []) {
    cashDeposit += conv(toNum(a.available), a.ccy, viewCcy)
  }
  for (const b of w.brokerage_accounts ?? []) {
    const src = b.ccy ?? viewCcy
    cashBroker += conv(toNum(b.sum_cash_accounts), src, viewCcy)
    stocks += conv(toNum(b.positions_value), src, viewCcy)
  }
  if (w.metals) metals = conv(toNum(w.metals.value), w.metals.ccy ?? viewCcy, viewCcy)
  if (w.real_estate) realEstate = conv(toNum(w.real_estate.value), w.real_estate.ccy ?? viewCcy, viewCcy)

  return { cashDeposit, cashBroker, stocks, metals, realEstate, total: cashDeposit + cashBroker + stocks + metals + realEstate }
}

function walletMoM(
  w: WalletManagerNode,
  currentTotal: number,
  viewCcy: ViewCcy,
  conv: (a: number, f: string, t: string) => number,
): number | null {
  const snap = w.snapshots?.[prevMonthKey(currentMonthKey())]
  if (!snap) return null
  const src = snap.ccy ?? viewCcy
  const prevTotal =
    conv(toNum(snap.cash_deposit), src, viewCcy) +
    conv(toNum(snap.cash_broker), src, viewCcy) +
    conv(toNum(snap.stocks), src, viewCcy) +
    conv(toNum(snap.metals), src, viewCcy) +
    conv(toNum(snap.real_estate), src, viewCcy)
  return pctChange(currentTotal, prevTotal || null)
}

function MomBadge({ value }: { value: number }) {
  const positive = value >= 0
  return (
    <span
      className={`text-xs font-medium px-1.5 py-0.5 rounded ${
        positive ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
      }`}
    >
      {fmtPct(value)}
    </span>
  )
}

function HealthChips({ health }: { health?: ManagerHealth }) {
  if (!health) return null
  const chips: { label: string; cls: string }[] = []
  if (health.missing_quotes) chips.push({ label: `Brak kursów: ${health.missing_quotes}`, cls: 'bg-red-500/20 text-red-300' })
  if (health.stale_quotes) chips.push({ label: 'Nieaktualne kursy', cls: 'bg-amber-500/20 text-amber-300' })
  if (health.projection_mismatch) chips.push({ label: 'Niezgodność', cls: 'bg-red-500/20 text-red-300' })
  if (health.needs_review) chips.push({ label: 'Do weryfikacji', cls: 'bg-amber-500/20 text-amber-300' })
  if (!chips.length) return null
  return (
    <>
      {chips.map((c) => (
        <span key={c.label} className={`text-xs font-medium px-1.5 py-0.5 rounded flex items-center gap-1 ${c.cls}`}>
          <AlertTriangle className="w-3 h-3" />
          {c.label}
        </span>
      ))}
    </>
  )
}

function AllocationBar({ cashPct, stocksPct, metalsPct, rePct }: {
  cashPct: number; stocksPct: number; metalsPct: number; rePct: number
}) {
  return (
    <div className="px-4 pb-2">
      <div className="flex h-1.5 rounded-full overflow-hidden bg-white/5">
        <div style={{ width: `${cashPct}%` }} className="bg-blue-400 transition-all" />
        <div style={{ width: `${stocksPct}%` }} className="bg-emerald-400 transition-all" />
        <div style={{ width: `${metalsPct}%` }} className="bg-amber-400 transition-all" />
        <div style={{ width: `${rePct}%` }} className="bg-violet-400 transition-all" />
      </div>
      <div className="flex gap-3 mt-1.5 flex-wrap">
        {cashPct > 0 && <Legend color="bg-blue-400" label={`Gotówka ${cashPct.toFixed(0)}%`} />}
        {stocksPct > 0 && <Legend color="bg-emerald-400" label={`Akcje ${stocksPct.toFixed(0)}%`} />}
        {metalsPct > 0 && <Legend color="bg-amber-400" label={`Metale ${metalsPct.toFixed(0)}%`} />}
        {rePct > 0 && <Legend color="bg-violet-400" label={`Nieruchomości ${rePct.toFixed(0)}%`} />}
      </div>
    </div>
  )
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1 text-xs text-white/40">
      <span className={`w-2 h-2 rounded-full ${color}`} />
      {label}
    </span>
  )
}

function SectionToggle({
  label, count, totalFmt, mom, open, onToggle,
}: {
  label: string; count: number; totalFmt: string; mom: number | null; open: boolean; onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/5 transition-colors text-left"
    >
      <div className="flex items-center gap-2 text-sm text-white/70 font-medium">
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        {label}
        <span className="text-white/30 text-xs font-normal">{count}</span>
      </div>
      <div className="flex items-center gap-2">
        {mom !== null && <MomBadge value={mom} />}
        <span className="text-sm text-white/60">{totalFmt}</span>
      </div>
    </button>
  )
}

function DepositSection({
  accounts, viewCcy, conv,
}: {
  accounts: ManagerDepositAccount[]
  viewCcy: ViewCcy
  conv: (a: number, f: string, t: string) => number
}) {
  const [open, setOpen] = useState(true)

  const total = accounts.reduce((s, a) => s + conv(toNum(a.available), a.ccy, viewCcy), 0)

  // Section-level MoM: sum of previous-month balances
  const prevKey = prevMonthKey(currentMonthKey())
  const prevTotal = accounts.reduce((s, a) => {
    const snap = a.snapshots?.[prevKey]
    if (!snap) return s
    return s + conv(toNum(snap.available), snap.ccy ?? a.ccy, viewCcy)
  }, 0)
  const mom = accounts.some((a) => a.snapshots?.[prevKey]) ? pctChange(total, prevTotal || null) : null

  if (!accounts.length) return null

  return (
    <div>
      <SectionToggle
        label="Konta depozytowe"
        count={accounts.length}
        totalFmt={fmtMoney(total, viewCcy)}
        mom={mom}
        open={open}
        onToggle={() => setOpen((v) => !v)}
      />
      {open && (
        <div className="space-y-2 mt-1 ml-2">
          {accounts.map((a) => {
            const bal = conv(toNum(a.available), a.ccy, viewCcy)
            const snap = a.snapshots?.[prevKey]
            const prevBal = snap ? conv(toNum(snap.available), snap.ccy ?? a.ccy, viewCcy) : null
            const accountMom = prevBal !== null ? pctChange(bal, prevBal || null) : null

            return (
              <div key={a.id} className="bg-slate-900/50 border border-white/5 rounded-lg px-3 py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-white">{a.name}</p>
                    <p className="text-xs text-white/35 mt-0.5">
                      Tx/mies: {a.tx_per_month ?? 0} · {a.ccy}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    <HealthChips health={a.health} />
                    {accountMom !== null && <MomBadge value={accountMom} />}
                    <span className="text-sm font-semibold text-white tabular-nums">
                      {fmtMoney(bal, viewCcy)}
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function BrokerageSection({
  accounts, viewCcy, conv,
}: {
  accounts: ManagerBrokerageAccount[]
  viewCcy: ViewCcy
  conv: (a: number, f: string, t: string) => number
}) {
  const [open, setOpen] = useState(true)
  const [openAccounts, setOpenAccounts] = useState<Set<string>>(new Set())

  const total = accounts.reduce((s, b) => {
    const src = b.ccy ?? viewCcy
    return s + conv(toNum(b.sum_cash_accounts), src, viewCcy) + conv(toNum(b.positions_value), src, viewCcy)
  }, 0)

  const prevKey = prevMonthKey(currentMonthKey())
  const prevTotal = accounts.reduce((s, b) => {
    const snap = b.snapshots?.[prevKey]
    if (!snap) return s
    const src = snap.ccy ?? b.ccy ?? viewCcy
    return s + conv(toNum(snap.cash), src, viewCcy) + conv(toNum(snap.stocks), src, viewCcy)
  }, 0)
  const mom = accounts.some((b) => b.snapshots?.[prevKey]) ? pctChange(total, prevTotal || null) : null

  const toggleAccount = useCallback((id: string) => {
    setOpenAccounts((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  if (!accounts.length) return null

  return (
    <div>
      <SectionToggle
        label="Rachunki maklerskie"
        count={accounts.length}
        totalFmt={fmtMoney(total, viewCcy)}
        mom={mom}
        open={open}
        onToggle={() => setOpen((v) => !v)}
      />
      {open && (
        <div className="space-y-2 mt-1 ml-2">
          {accounts.map((b) => {
            const src = b.ccy ?? viewCcy
            const cashView = conv(toNum(b.sum_cash_accounts), src, viewCcy)
            const posView = conv(toNum(b.positions_value), src, viewCcy)
            const accTotal = cashView + posView
            const snap = b.snapshots?.[prevKey]
            const prevAccTotal = snap
              ? conv(toNum(snap.cash), snap.ccy ?? src, viewCcy) + conv(toNum(snap.stocks), snap.ccy ?? src, viewCcy)
              : null
            const accMom = prevAccTotal !== null ? pctChange(accTotal, prevAccTotal || null) : null
            const isOpen = openAccounts.has(b.id)
            const positions = b.positions ?? []
            const cashAccounts = b.cash_accounts ?? []

            return (
              <div key={b.id} className="bg-slate-900/50 border border-white/5 rounded-lg overflow-hidden">
                <button
                  onClick={() => toggleAccount(b.id)}
                  className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-white/5 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    {isOpen ? <ChevronDown className="w-3.5 h-3.5 text-white/40" /> : <ChevronRight className="w-3.5 h-3.5 text-white/40" />}
                    <div className="text-left">
                      <p className="text-sm font-medium text-white">{b.name}</p>
                      <p className="text-xs text-white/35">
                        Zdarzenia/mies: {Math.round(b.events_per_month ?? 0)} · {b.ccy ?? '—'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    <HealthChips health={b.health} />
                    {accMom !== null && <MomBadge value={accMom} />}
                    <span className="text-sm font-semibold text-white tabular-nums">
                      {fmtMoney(accTotal, viewCcy)}
                    </span>
                  </div>
                </button>

                {isOpen && (
                  <div className="px-3 pb-3 pt-1 space-y-3 border-t border-white/5">
                    {/* Cash accounts */}
                    <div>
                      <p className="text-xs text-white/30 uppercase tracking-wide mb-1.5">Konta gotówkowe</p>
                      {!cashAccounts.length ? (
                        <p className="text-xs text-white/30">Brak powiązanych kont.</p>
                      ) : (
                        <div className="space-y-1">
                          {cashAccounts.map((ca, i) => (
                            <div key={i} className="flex justify-between text-xs text-white/60">
                              <span>{ca.name ?? '—'}</span>
                              <span className="tabular-nums">
                                {toNum(ca.available).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                {'\u00a0'}{ca.ccy ?? ''}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="flex justify-between text-xs font-medium text-white/50 mt-1.5 pt-1.5 border-t border-white/5">
                        <span>Suma gotówki</span>
                        <span className="tabular-nums">{fmtMoney(cashView, viewCcy)}</span>
                      </div>
                    </div>

                    {/* Top positions */}
                    {positions.length > 0 && (
                      <div>
                        <p className="text-xs text-white/30 uppercase tracking-wide mb-1.5">Pozycje (top 8)</p>
                        <div className="flex flex-wrap gap-1.5">
                          {positions.slice(0, 8).map((p, i) => {
                            const pnl = toNum(p.pnl_pct)
                            const positive = pnl >= 0
                            return (
                              <span
                                key={i}
                                className={`text-xs px-2 py-0.5 rounded font-medium ${
                                  positive ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
                                }`}
                              >
                                {p.symbol ?? '?'} · {fmtPct(pnl)}
                              </span>
                            )
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function MetalsSection({
  metals, viewCcy, conv,
}: {
  metals: ManagerMetals
  viewCcy: ViewCcy
  conv: (a: number, f: string, t: string) => number
}) {
  const [open, setOpen] = useState(true)
  const total = conv(toNum(metals.value), metals.ccy ?? viewCcy, viewCcy)
  const items = metals.items ?? []

  return (
    <div>
      <SectionToggle
        label="Metale szlachetne"
        count={metals.count ?? items.length}
        totalFmt={fmtMoney(total, viewCcy)}
        mom={null}
        open={open}
        onToggle={() => setOpen((v) => !v)}
      />
      {open && (
        <div className="mt-1 ml-2 bg-slate-900/50 border border-white/5 rounded-lg overflow-hidden">
          <HealthChips health={metals.health} />
          {!items.length ? (
            <p className="text-xs text-white/30 px-3 py-2">Brak pozycji w metalach.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left px-3 py-2 text-white/30 font-medium">Metal</th>
                  <th className="text-right px-3 py-2 text-white/30 font-medium">Ilość</th>
                  <th className="text-right px-3 py-2 text-white/30 font-medium">Wartość ({viewCcy})</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => {
                  const name = it.name ?? it.metal ?? it.type ?? '—'
                  const qty = toNum(it.quantity)
                  const unit = it.qty_unit ?? 'g'
                  const val = conv(toNum(it.value), it.ccy ?? metals.ccy ?? viewCcy, viewCcy)
                  return (
                    <tr key={it.id ?? i} className="border-b border-white/5 last:border-0">
                      <td className="px-3 py-2 text-white/70">{name}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-white/60">
                        {qty.toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {unit}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-white/70 font-medium">
                        {fmtMoney(val, viewCcy)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

function RealEstateSection({
  re, viewCcy, conv,
}: {
  re: ManagerRealEstate
  viewCcy: ViewCcy
  conv: (a: number, f: string, t: string) => number
}) {
  const [open, setOpen] = useState(true)
  const total = conv(toNum(re.value), re.ccy ?? viewCcy, viewCcy)
  const items = re.items ?? []

  return (
    <div>
      <SectionToggle
        label="Nieruchomości"
        count={re.count ?? items.length}
        totalFmt={fmtMoney(total, viewCcy)}
        mom={null}
        open={open}
        onToggle={() => setOpen((v) => !v)}
      />
      {open && (
        <div className="mt-1 ml-2 bg-slate-900/50 border border-white/5 rounded-lg overflow-hidden">
          <HealthChips health={re.health} />
          {!items.length ? (
            <p className="text-xs text-white/30 px-3 py-2">Brak nieruchomości.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left px-3 py-2 text-white/30 font-medium">Nazwa</th>
                  <th className="text-left px-3 py-2 text-white/30 font-medium">Miasto</th>
                  <th className="text-right px-3 py-2 text-white/30 font-medium">Wartość ({viewCcy})</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => {
                  const val = conv(toNum(it.value), it.ccy ?? re.ccy ?? viewCcy, viewCcy)
                  return (
                    <tr key={it.id ?? i} className="border-b border-white/5 last:border-0">
                      <td className="px-3 py-2 text-white/70">{it.name ?? it.type ?? '—'}</td>
                      <td className="px-3 py-2 text-white/50">{it.city ?? '—'}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-white/70 font-medium">
                        {fmtMoney(val, viewCcy)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

function WalletCard({
  wallet, viewCcy, conv,
}: {
  wallet: WalletManagerNode
  viewCcy: ViewCcy
  conv: (a: number, f: string, t: string) => number
}) {
  const [open, setOpen] = useState(true)

  const bd = walletBreakdown(wallet, viewCcy, conv)
  const mom = walletMoM(wallet, bd.total, viewCcy, conv)

  const cashPct = bd.total > 0 ? ((bd.cashDeposit + bd.cashBroker) / bd.total) * 100 : 0
  const stocksPct = bd.total > 0 ? (bd.stocks / bd.total) * 100 : 0
  const metalsPct = bd.total > 0 ? (bd.metals / bd.total) * 100 : 0
  const rePct = bd.total > 0 ? (bd.realEstate / bd.total) * 100 : 0

  const depositAccounts = wallet.deposit_accounts ?? []
  const brokerageAccounts = wallet.brokerage_accounts ?? []

  return (
    <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden mb-4">
      {/* Header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3.5 hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-3">
          {open ? (
            <ChevronDown className="w-4 h-4 text-white/40" />
          ) : (
            <ChevronRight className="w-4 h-4 text-white/40" />
          )}
          <span className="font-semibold text-white">{wallet.name}</span>
        </div>
        <div className="flex items-center gap-3">
          {mom !== null && <MomBadge value={mom} />}
          <span className="font-semibold text-white tabular-nums">
            {fmtMoney(bd.total, viewCcy)}
          </span>
        </div>
      </button>

      {/* Allocation bar */}
      {open && bd.total > 0 && (
        <AllocationBar
          cashPct={cashPct}
          stocksPct={stocksPct}
          metalsPct={metalsPct}
          rePct={rePct}
        />
      )}

      {/* Content */}
      {open && (
        <div className="px-4 pb-4 pt-1 space-y-1">
          {depositAccounts.length > 0 && (
            <DepositSection accounts={depositAccounts} viewCcy={viewCcy} conv={conv} />
          )}
          {brokerageAccounts.length > 0 && (
            <BrokerageSection accounts={brokerageAccounts} viewCcy={viewCcy} conv={conv} />
          )}
          {wallet.metals && (wallet.metals.count ?? 0) > 0 && (
            <MetalsSection metals={wallet.metals} viewCcy={viewCcy} conv={conv} />
          )}
          {wallet.real_estate && (wallet.real_estate.count ?? 0) > 0 && (
            <RealEstateSection re={wallet.real_estate} viewCcy={viewCcy} conv={conv} />
          )}
          {depositAccounts.length === 0 && brokerageAccounts.length === 0 &&
            !wallet.metals?.count && !wallet.real_estate?.count && (
              <p className="text-sm text-white/30 py-2 pl-1">Brak kont w tym portfelu.</p>
            )}
        </div>
      )}
    </div>
  )
}

type Props = {
  wallets: WalletManagerNode[]
  fxRates: FxRates | null
}

export function WalletManagerPage({ wallets, fxRates }: Props) {
  const router = useRouter()
  const [viewCcy, setViewCcy] = useState<ViewCcy>('PLN')
  const [snapshotLoading, setSnapshotLoading] = useState(false)
  const [snapshotMsg, setSnapshotMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null)

  const conv = makeConv(fxRates)

  const handleSnapshot = async () => {
    setSnapshotLoading(true)
    setSnapshotMsg(null)
    try {
      const res = await fetch('/api/wallet/manager', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const json = await res.json() as { ok?: boolean; month_key?: string; error?: string }
      if (!res.ok || json.error) {
        setSnapshotMsg({ type: 'error', text: json.error ?? 'Błąd tworzenia snapshotu' })
      } else {
        setSnapshotMsg({ type: 'ok', text: `Snapshot zapisany (${json.month_key ?? ''})` })
        router.refresh()
      }
    } catch {
      setSnapshotMsg({ type: 'error', text: 'Błąd połączenia' })
    } finally {
      setSnapshotLoading(false)
    }
  }

  const totalAll = wallets.reduce((s, w) => s + walletBreakdown(w, viewCcy, conv).total, 0)

  return (
    <div className="px-4 py-4">
      <div className="max-w-screen-xl mx-auto">

        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <div>
            <h1 className="text-xl font-semibold text-white">Zarządzanie portfelami</h1>
            {wallets.length > 0 && (
              <p className="text-sm text-white/40 mt-0.5">
                Łącznie: {fmtMoney(totalAll, viewCcy)} · {wallets.length} portfel{wallets.length === 1 ? '' : wallets.length <= 4 ? 'e' : 'i'}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Currency selector */}
            <div className="flex rounded-lg overflow-hidden border border-white/10">
              {(['PLN', 'USD', 'EUR'] as ViewCcy[]).map((ccy) => (
                <button
                  key={ccy}
                  onClick={() => setViewCcy(ccy)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    viewCcy === ccy
                      ? 'bg-blue-600 text-white'
                      : 'text-white/50 hover:text-white hover:bg-white/5'
                  }`}
                >
                  {ccy}
                </button>
              ))}
            </div>

            {/* Snapshot button */}
            <button
              onClick={handleSnapshot}
              disabled={snapshotLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-700/60 border border-white/10 text-white/70 hover:text-white hover:bg-slate-600/60 transition-colors disabled:opacity-50"
            >
              {snapshotLoading ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Camera className="w-3.5 h-3.5" />
              )}
              Utwórz snapshot
            </button>
          </div>
        </div>

        {/* Snapshot message */}
        {snapshotMsg && (
          <div
            className={`mb-4 px-4 py-2.5 rounded-lg text-sm flex items-center justify-between ${
              snapshotMsg.type === 'ok'
                ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-300'
                : 'bg-red-500/10 border border-red-500/20 text-red-300'
            }`}
          >
            <span>{snapshotMsg.text}</span>
            <button onClick={() => setSnapshotMsg(null)} className="text-white/30 hover:text-white/60 ml-3">×</button>
          </div>
        )}

        {/* Empty state */}
        {wallets.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Eye className="w-8 h-8 text-white/20 mb-3" />
            <p className="text-white/40 text-sm">Brak portfeli do wyświetlenia.</p>
            <p className="text-white/25 text-xs mt-1">Utwórz portfel w sekcji Portfele.</p>
          </div>
        )}

        {/* Wallet cards */}
        {wallets.map((w) => (
          <WalletCard key={w.id} wallet={w} viewCcy={viewCcy} conv={conv} />
        ))}

      </div>
    </div>
  )
}
