'use client'

import { startTransition, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import {
  TrendingUp, TrendingDown, Minus, ExternalLink,
  CheckCircle2, AlertTriangle, Calendar, Users, Target,
  BarChart3, Activity, Shield, Zap, BookOpen,
} from 'lucide-react'
import type {
  EquityReport, ReportPeriod, MV, ScoreItem,
  Recommendation, Source, Confidence, Trend, MomentumSignal,
} from '../types/equity'
import { evalStatus } from '../data/indicators'
import { IndicatorLegendDialog } from './IndicatorLegendDialog'

// ── Constants ────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'fundamentals',  label: 'Analiza fundamentalna', short: 'Fundamenty',  icon: BarChart3 },
  { id: 'debt',          label: 'Dług i bilans',          short: 'Dług',        icon: Shield },
  { id: 'trend',         label: 'Trend i kondycja',       short: 'Trend',       icon: TrendingUp },
  { id: 'dividend',      label: 'Dywidenda',               short: 'Dywidenda',   icon: Zap },
  { id: 'events',        label: 'Zdarzenia kluczowe',      short: 'Zdarzenia',   icon: Calendar },
  { id: 'moat',          label: 'Przewagi i ryzyka',       short: 'Przewagi',    icon: Target },
  { id: 'technical',     label: 'Technika i momentum',     short: 'Technika',    icon: Activity },
  { id: 'volume',        label: 'Wolumen i płynność',      short: 'Wolumen',     icon: BarChart3 },
  { id: 'shareholders',  label: 'Struktura akcjonariatu',  short: 'Akcjonariat', icon: Users },
  { id: 'verdict',       label: 'Werdykt',                 short: 'Werdykt',     icon: Target },
] as const

type TabId = typeof TABS[number]['id']

const REC_CONFIG: Record<Recommendation, { label: string; cls: string }> = {
  strong_buy: { label: 'Silny KUPUJ',  cls: 'bg-emerald-500 text-white' },
  buy:        { label: 'KUPUJ',        cls: 'bg-emerald-600/70 text-emerald-200 border border-emerald-500/40' },
  hold:       { label: 'TRZYMAJ',      cls: 'bg-slate-600/70 text-slate-200 border border-slate-500/40' },
  reduce:     { label: 'REDUKUJ',      cls: 'bg-amber-600/70 text-amber-200 border border-amber-500/40' },
  sell:       { label: 'SPRZEDAJ',     cls: 'bg-red-600/70 text-red-200 border border-red-500/40' },
}

const CONF_CLS: Record<Confidence, string> = {
  high:   'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25',
  medium: 'bg-amber-500/15 text-amber-400 border border-amber-500/25',
  low:    'bg-red-500/15 text-red-400 border border-red-500/25',
}

const SRC_CLS: Record<Source, { cls: string; label: string }> = {
  openai: { cls: 'bg-purple-500/15 text-purple-400 border border-purple-500/25', label: 'AI' },
  local:  { cls: 'bg-blue-500/15 text-blue-400 border border-blue-500/25',       label: 'LOC' },
  manual: { cls: 'bg-slate-500/15 text-slate-400 border border-slate-500/25',    label: 'MAN' },
}

const MOMENTUM_CFG: Record<MomentumSignal, { cls: string; icon: string }> = {
  buy_now:       { cls: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300', icon: '⚡' },
  accumulate:    { cls: 'bg-blue-500/20    border-blue-500/40    text-blue-300',    icon: '📥' },
  wait:          { cls: 'bg-amber-500/20   border-amber-500/40   text-amber-300',   icon: '⏳' },
  too_expensive: { cls: 'bg-orange-500/20  border-orange-500/40  text-orange-300',  icon: '💸' },
  avoid:         { cls: 'bg-red-500/20     border-red-500/40     text-red-300',     icon: '🚫' },
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtPLN(v: number): string {
  if (Math.abs(v) >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)} mld PLN`
  if (Math.abs(v) >= 1_000_000)     return `${(v / 1_000_000).toFixed(0)} mln PLN`
  if (Math.abs(v) >= 1_000)         return `${(v / 1_000).toFixed(0)} k PLN`
  return `${v.toFixed(2)} PLN`
}

function fmtMV(mv: MV): string {
  if (mv.value === null) return '—'
  const v = mv.value
  if (mv.unit === 'PLN')   return fmtPLN(v)
  if (mv.unit === '%')     return `${v.toFixed(1)}%`
  if (mv.unit === 'x')     return `${v.toFixed(2)}x`
  if (mv.unit === 'akcji/sesja' || mv.unit === 'akcji') return v.toLocaleString('pl-PL')
  return `${v.toLocaleString('pl-PL', { maximumFractionDigits: 2 })}${mv.unit ? ` ${mv.unit}` : ''}`
}

function scoreColor(s: number): string {
  if (s >= 8) return 'bg-emerald-500'
  if (s >= 6) return 'bg-blue-500'
  if (s >= 4) return 'bg-amber-500'
  return 'bg-red-500'
}

function impactCls(impact: string): string {
  if (impact === 'high')   return 'bg-red-500/20 text-red-300 border border-red-500/30'
  if (impact === 'medium') return 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
  return 'bg-slate-500/20 text-slate-300 border border-slate-500/30'
}

function strengthCls(s: string): string {
  if (s === 'strong')   return 'text-emerald-400'
  if (s === 'moderate') return 'text-amber-400'
  return 'text-slate-400'
}

function trendIcon(t: Trend | string) {
  if (t === 'bullish' || t === 'rising') return <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
  if (t === 'bearish' || t === 'falling') return <TrendingDown className="w-3.5 h-3.5 text-red-400" />
  return <Minus className="w-3.5 h-3.5 text-slate-400" />
}

function ConfBadge({ c }: { c: Confidence }) {
  return <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${CONF_CLS[c]}`}>{c === 'high' ? 'H' : c === 'medium' ? 'M' : 'L'}</span>
}

function SrcBadge({ s }: { s: Source }) {
  const cfg = SRC_CLS[s]
  return <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${cfg.cls}`}>{cfg.label}</span>
}

function Card({ title, children, className }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-slate-800/40 border border-white/10 rounded-xl ${className ?? ''}`}>
      {title && (
        <div className="px-4 py-2.5 border-b border-white/8 flex items-center gap-2">
          <span className="text-xs font-semibold text-white/50 uppercase tracking-widest">{title}</span>
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}

function MetricRow({ label, mv, note, indicatorId }: { label: string; mv: MV; note?: string; indicatorId?: string }) {
  const status = indicatorId !== undefined && mv.value !== null ? evalStatus(mv.value, indicatorId) : null
  const valueCls =
    status === 'healthy' ? 'text-emerald-400' :
    status === 'caution' ? 'text-amber-400' :
    status === 'danger'  ? 'text-red-400' :
    'text-white'

  return (
    <div className="flex items-start justify-between py-2.5 border-b border-white/5 last:border-0 gap-3">
      <div className="min-w-0">
        <p className="text-xs text-white/50">{label}</p>
        {(note ?? mv.note) && <p className="text-[10px] text-white/30 mt-0.5 leading-tight">{note ?? mv.note}</p>}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <span className={`font-mono text-sm font-medium ${valueCls}`}>{fmtMV(mv)}</span>
        <SrcBadge s={mv.source} />
        <ConfBadge c={mv.confidence} />
      </div>
    </div>
  )
}

function ScoreMeter({ item, label }: { item: ScoreItem; label: string }) {
  return (
    <div className="py-2.5 border-b border-white/5 last:border-0">
      <div className="flex items-center gap-3 mb-1.5">
        <span className="text-xs text-white/60 w-44 shrink-0">{label}</span>
        <div className="flex-1 h-2 bg-white/8 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${scoreColor(item.score)}`}
            style={{ width: `${item.score * 10}%` }}
          />
        </div>
        <span className={`text-sm font-bold w-6 text-right ${
          item.score >= 8 ? 'text-emerald-400' : item.score >= 6 ? 'text-blue-400' : item.score >= 4 ? 'text-amber-400' : 'text-red-400'
        }`}>{item.score}</span>
      </div>
      <p className="text-[11px] text-white/35 leading-relaxed pl-0">{item.reasoning}</p>
    </div>
  )
}

function InterpretCard({ text }: { text: string }) {
  return (
    <div className="mt-6 rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 flex gap-3">
      <BookOpen className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
      <div>
        <p className="text-xs font-semibold text-blue-400 mb-1 uppercase tracking-wide">Jak interpretować tę sekcję</p>
        <p className="text-xs text-white/55 leading-relaxed">{text}</p>
      </div>
    </div>
  )
}

function CompanyHeader({ company, meta }: { company: EquityReport['company']; meta: EquityReport['meta'] }) {
  const { price } = company
  const cap = price.market_cap
  const capFmt = cap >= 1_000_000_000 ? `${(cap / 1_000_000_000).toFixed(2)} mld PLN` : `${(cap / 1_000_000).toFixed(0)} mln PLN`
  const ytdColor = price.change_ytd_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
  const d1Color  = price.change_1d_pct  >= 0 ? 'text-emerald-400' : 'text-red-400'

  return (
    <div className="bg-slate-800/60 border border-white/10 rounded-xl p-5 mb-4">
      <div className="flex flex-wrap gap-6 items-start justify-between">

        {/* Left: identity + description */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h1 className="text-2xl font-bold text-white">{company.name}</h1>
            <span className="text-white/40 text-lg">{company.full_name}</span>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs mb-3">
            <span className="bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded border border-blue-500/30 font-medium">{meta.symbol}</span>
            <span className="text-white/30">{meta.mic}</span>
            <span className="text-white/20">·</span>
            <span className="text-white/40">{company.isin}</span>
            <span className="text-white/20">·</span>
            <span className="text-white/40">{company.sector}</span>
            <span className="text-white/20">·</span>
            <span className="text-white/40">{company.industry}</span>
          </div>

          <p className="text-xs text-white/55 leading-relaxed max-w-2xl mb-3">{company.description}</p>

          {/* Leader badges */}
          <div className="flex flex-wrap gap-1.5 mb-3">
            {company.is_leader_in.map((s, i) => (
              <span key={i} className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded">
                ⭐ {s}
              </span>
            ))}
          </div>

          {/* Quick facts row */}
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-white/40">
            <span><span className="text-white/25">CEO</span> <span className="text-white/65">{company.ceo}</span> <span className="text-white/25">od {company.ceo_since}</span></span>
            <span><span className="text-white/25">Założona</span> <span className="text-white/65">{company.founded}</span></span>
            <span><span className="text-white/25">HQ</span> <span className="text-white/65">{company.headquarters}</span></span>
            <span><span className="text-white/25">Pracownicy</span> <span className="text-white/65">{company.employees.value?.toLocaleString('pl-PL')}</span></span>
            <a href={company.website} target="_blank" rel="noopener noreferrer" className="text-blue-400/70 hover:text-blue-300 flex items-center gap-0.5">
              www <ExternalLink className="w-2.5 h-2.5" />
            </a>
          </div>
        </div>

        {/* Right: price panel */}
        <div className="bg-slate-900/60 border border-white/8 rounded-xl p-4 min-w-[220px]">
          <div className="flex items-baseline gap-2 mb-1">
            <span className="text-3xl font-bold text-white">{price.current.toFixed(2)}</span>
            <span className="text-white/40 text-sm">{price.currency}</span>
          </div>
          <div className="flex items-center gap-2 mb-3">
            <span className={`text-sm font-medium ${d1Color}`}>
              {price.change_1d_pct >= 0 ? '+' : ''}{price.change_1d_pct.toFixed(2)}% dziś
            </span>
            <span className="text-white/25">·</span>
            <span className={`text-sm font-medium ${ytdColor}`}>
              {price.change_ytd_pct >= 0 ? '+' : ''}{price.change_ytd_pct.toFixed(2)}% YTD
            </span>
          </div>

          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between"><span className="text-white/35">52W max</span><span className="text-white/80">{price.week_52_high.toFixed(2)} {price.currency}</span></div>
            <div className="flex justify-between"><span className="text-white/35">52W min</span><span className="text-white/80">{price.week_52_low.toFixed(2)} {price.currency}</span></div>
            <div className="flex justify-between"><span className="text-white/35">Kap. rynkowa</span><span className="text-white/80">{capFmt}</span></div>
            <div className="flex justify-between"><span className="text-white/35">Pozycja rynkowa</span><span className="text-white/80 text-right max-w-[130px] leading-tight">{company.market_position.split('·')[0]?.trim()}</span></div>
          </div>

          <p className="text-[10px] text-white/25 mt-2.5" suppressHydrationWarning>
            Kurs: {new Date(price.as_of).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' })}
          </p>
        </div>

      </div>

      {/* Products + Competitors row */}
      <div className="mt-4 pt-3 border-t border-white/5 flex flex-wrap gap-6 text-xs">
        <div>
          <span className="text-white/25 uppercase tracking-wide text-[10px]">Produkty</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {company.main_products.map((p, i) => (
              <span key={i} className="bg-slate-700/50 text-white/50 px-2 py-0.5 rounded border border-white/5">{p}</span>
            ))}
          </div>
        </div>
        <div>
          <span className="text-white/25 uppercase tracking-wide text-[10px]">Konkurencja</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {company.key_competitors.map((c, i) => (
              <span key={i} className="bg-red-900/20 text-red-400/60 px-2 py-0.5 rounded border border-red-500/10">{c}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ReportBanner({
  meta,
  periods,
  activePeriod,
  onPeriodChange,
}: {
  meta: EquityReport['meta']
  periods: ReportPeriod[]
  activePeriod: string
  onPeriodChange: (p: string) => void
}) {
  const genDate = new Date(meta.generated_at)
  const validDate = new Date(meta.valid_until)
  const now = new Date()
  const daysLeft = Math.ceil((validDate.getTime() - now.getTime()) / 86_400_000)
  const freshness = daysLeft > 30 ? 'fresh' : daysLeft > 0 ? 'aging' : 'stale'
  const dotCls = freshness === 'fresh' ? 'bg-emerald-400' : freshness === 'aging' ? 'bg-amber-400' : 'bg-red-400'

  return (
    <div className="bg-slate-800/40 border border-white/10 rounded-xl px-4 py-3 mb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">

        {/* Period picker */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
          <span className="text-[10px] text-white/25 uppercase tracking-wide shrink-0 mr-1">Raport:</span>
          {periods.map((p) => (
            <button
              key={p.period}
              onClick={() => onPeriodChange(p.period)}
              className={[
                'shrink-0 px-3 py-1 rounded-lg text-xs font-medium border transition-colors',
                activePeriod === p.period
                  ? 'bg-blue-600/30 border-blue-500/40 text-blue-300'
                  : 'bg-slate-800/60 border-white/8 text-white/40 hover:text-white hover:border-white/20',
              ].join(' ')}
            >
              {p.period}
              {p.is_current && <span className="ml-1 text-[9px] text-emerald-400">●</span>}
            </button>
          ))}
        </div>

        {/* Freshness info */}
        <div className="flex items-center gap-2 text-[11px] text-white/35 shrink-0">
          <span className={`w-1.5 h-1.5 rounded-full ${dotCls}`} />
          <span>Wygenerowano: {genDate.toLocaleDateString('pl-PL', { dateStyle: 'medium' })}</span>
          <span className="text-white/15">·</span>
          <span>Model: {meta.source_versions.model}</span>
          <span className="text-white/15">·</span>
          <span>Ważny do: {validDate.toLocaleDateString('pl-PL', { dateStyle: 'medium' })}</span>
          {daysLeft > 0 && <span className="text-white/25">({daysLeft} dni)</span>}
          {daysLeft <= 0 && <span className="text-amber-400">Wygasły — regeneruj</span>}
        </div>
      </div>
    </div>
  )
}

function FundamentalsTab({ d }: { d: EquityReport['fundamentals'] }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Wycena rynkowa">
          <MetricRow label="C/Z (P/E) — cena / zysk na akcję" mv={d.pe_ratio} note="Im niższy, tym tańsza spółka. Branża budowlana: typowo 8–14x" indicatorId="pe_ratio" />
          <MetricRow label="EV/EBITDA — wartość przedsiębiorstwa / EBITDA" mv={d.ev_ebitda} note="Lepszy niż P/E gdy spółka ma dług. Tania: <6x" indicatorId="ev_ebitda" />
          <MetricRow label="C/WK (P/B) — cena / wartość księgowa" mv={d.pb_ratio} note="<1 = spółka wyceniana poniżej majątku netto" indicatorId="pb_ratio" />
          <MetricRow label="BVPS — wartość księgowa na akcję" mv={d.bvps} note="Kapitał własny / liczba akcji. Podstawa do oceny P/B i wyceny majątkowej" />
          <MetricRow label="C/P (P/S) — cena / przychody" mv={d.ps_ratio} note="Dobry dla spółek bez zysku lub cyklicznych" indicatorId="ps_ratio" />
          <MetricRow label="Dyskonto od 52W szczytu" mv={d.discount_from_peak_pct} note="Jak dużo kurs spadł od rocznego maksimum" />
        </Card>

        <Card title="Rentowność">
          <MetricRow label="Marża EBITDA — zysk operacyjny / przychody" mv={d.ebitda_margin} note="Mierzy efektywność operacyjną. Budownictwo: 6–10%" indicatorId="ebitda_margin" />
          <MetricRow label="ROE — zwrot na kapitale własnym" mv={d.roe} note="Jak skutecznie spółka zarabia dla akcjonariuszy. Dobry: >10%" indicatorId="roe" />
          <MetricRow label="ROIC — zwrot na zainwestowanym kapitale" mv={d.roic} note="Kluczowy: jeśli ROIC > WACC, spółka tworzy wartość" indicatorId="roic" />
          <MetricRow label="OCF — przepływy pieniężne z działalności operacyjnej" mv={d.ocf} note="Pokazuje przepływy pieniężne generowane przez podstawowy biznes przed CAPEX. Ujemny OCF przy dodatnim zysku to sygnał ostrzegawczy" />
          <MetricRow label="FCF — wolna gotówka (po CAPEX)" mv={d.fcf} note="Realny cash dostępny dla akcjonariuszy / na dług" />
          <MetricRow label="FCF yield — FCF / kapitalizacja rynkowa" mv={d.fcf_yield} note="Jak wiele gotówki generuje na PLN ceny akcji. >8% = atrakcyjnie" indicatorId="fcf_yield" />
        </Card>

        <Card title="Wyniki TTM (ostatnie 12 miesięcy)">
          <MetricRow label="Przychody (revenue)" mv={d.revenue_ttm} />
          <MetricRow label="EBITDA" mv={d.ebitda_ttm} />
          <MetricRow label="Zysk netto" mv={d.net_income_ttm} />
          <MetricRow label="EPS — zysk na akcję" mv={d.eps_ttm} note="Podstawa P/E. Porównuj rok do roku" />
        </Card>
      </div>
      <InterpretCard text={d.interpretation} />
    </div>
  )
}

function DebtTab({ d }: { d: EquityReport['debt_balance'] }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Struktura długu">
          <MetricRow label="Gotówka i ekwiwalenty" mv={d.cash_and_equivalents} note="Płynne rezerwy — bufor na trudne czasy" />
          <MetricRow label="Dług netto = Dług − Gotówka" mv={d.net_debt} note="Rzeczywiste zadłużenie po odjęciu rezerw" />
          <MetricRow label="Dług netto / EBITDA" mv={d.net_debt_ebitda} note="Ile lat zysku EBITDA potrzeba na spłatę długu. Bezpieczne: <2x" indicatorId="net_debt_ebitda" />
          <MetricRow label="Dług / Kapitał własny (D/E)" mv={d.de_ratio} note="Im niższy, tym mniejsza dźwignia finansowa. Ryzyko: >1.5x" indicatorId="de_ratio" />
          <MetricRow label="Pokrycie odsetek = EBIT / odsetki" mv={d.interest_coverage} note="Jak komfortowo spółka obsługuje odsetki. Alarm: <2x" indicatorId="interest_coverage" />
        </Card>

        <Card title="Płynność i majątek">
          <MetricRow label="Wskaźnik bieżący (current ratio)" mv={d.current_ratio} note="Aktywa bieżące / pasywa bieżące. Minimum 1.0x. Dobry: 1.5–2.5x" indicatorId="current_ratio" />
          <MetricRow label="Quick ratio (płynność szybka)" mv={d.quick_ratio} note="Bez zapasów. Ostrzejszy test płynności. Minimum ~0.8x" indicatorId="quick_ratio" />
          <MetricRow label="Aktywa ogółem" mv={d.total_assets} />
          <MetricRow label="Kapitał własny" mv={d.equity} />
        </Card>

        <Card title="Inwestycje (CAPEX)">
          <MetricRow label="CAPEX — nakłady inwestycyjne" mv={d.capex} note="Ile spółka wydaje na aktywa trwałe. Wysoki CAPEX = intensywność kapitałowa" />
          <MetricRow label="CAPEX / Amortyzacja" mv={d.capex_to_depreciation} note=">1.0 = firma inwestuje w rozwój. <1.0 = konserwacja istniejącej bazy" indicatorId="capex_to_depreciation" />
        </Card>
      </div>
      <InterpretCard text={d.interpretation} />
    </div>
  )
}

function TrendTab({ d }: { d: EquityReport['trend_condition'] }) {
  const scoreItems: { key: keyof typeof d.scores; label: string }[] = [
    { key: 'profitability',         label: 'Rentowność' },
    { key: 'balance_sheet',         label: 'Kondycja bilansu' },
    { key: 'earnings_quality',      label: 'Jakość zysku' },
    { key: 'revenue_growth',        label: 'Wzrost przychodów' },
    { key: 'market_valuation',      label: 'Wycena rynkowa' },
    { key: 'management_quality',    label: 'Jakość zarządzania' },
    { key: 'competitive_advantage', label: 'Przewaga konkurencyjna' },
    { key: 'industry_outlook',      label: 'Perspektywy branży' },
  ]

  return (
    <div className="space-y-4">
      {/* Scoring */}
      <Card title="Scoring kondycji spółki (1–10)">
        <div className="flex items-center gap-3 mb-4 pb-3 border-b border-white/8">
          <span className="text-white/50 text-sm">Ocena ogólna</span>
          <div className={`text-2xl font-bold ${d.scores.overall >= 8 ? 'text-emerald-400' : d.scores.overall >= 6 ? 'text-blue-400' : 'text-amber-400'}`}>
            {d.scores.overall.toFixed(1)}
          </div>
          <span className="text-white/25 text-sm">/ 10</span>
          <div className="flex-1 h-3 bg-white/8 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${scoreColor(d.scores.overall)}`} style={{ width: `${d.scores.overall * 10}%` }} />
          </div>
        </div>
        {scoreItems.map(({ key, label }) => {
          const item = d.scores[key] as ScoreItem
          return <ScoreMeter key={key} item={item} label={label} />
        })}
      </Card>

      {/* Historical table */}
      <Card title="Historia finansowa (PLN mln)">
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="w-full text-xs min-w-[700px]">
            <thead>
              <tr className="border-b border-white/10">
                {['Rok','Przychody','EBITDA','Marża%','Zysk netto','EPS','ROE%','ND/EBITDA','DPS',''].map((h, i) => (
                  <th key={i} className="py-2 text-left text-white/35 font-medium pr-3 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.history.map((r) => (
                <tr key={r.year} className="border-b border-white/5 last:border-0 hover:bg-white/2 transition-colors">
                  <td className="py-2 pr-3 text-white/70 font-medium">{r.year}</td>
                  <td className="py-2 pr-3 text-white/80 tabular-nums">{r.revenue?.toLocaleString('pl-PL') ?? '—'}</td>
                  <td className="py-2 pr-3 text-white/80 tabular-nums">{r.ebitda?.toLocaleString('pl-PL') ?? '—'}</td>
                  <td className="py-2 pr-3 tabular-nums">
                    <span className={r.ebitda_margin_pct && r.ebitda_margin_pct >= 7 ? 'text-emerald-400' : 'text-amber-400'}>
                      {r.ebitda_margin_pct?.toFixed(1) ?? '—'}%
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-white/80 tabular-nums">{r.net_income?.toLocaleString('pl-PL') ?? '—'}</td>
                  <td className="py-2 pr-3 text-white/80 tabular-nums">{r.eps?.toFixed(2) ?? '—'}</td>
                  <td className="py-2 pr-3 tabular-nums">
                    <span className={r.roe_pct && r.roe_pct >= 8 ? 'text-emerald-400' : 'text-white/60'}>
                      {r.roe_pct?.toFixed(1) ?? '—'}%
                    </span>
                  </td>
                  <td className="py-2 pr-3 tabular-nums">
                    <span className={r.net_debt_ebitda !== null && r.net_debt_ebitda < 2 ? 'text-emerald-400' : 'text-amber-400'}>
                      {r.net_debt_ebitda?.toFixed(2) ?? '—'}x
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-white/70 tabular-nums">{r.dividend_per_share ? `${r.dividend_per_share.toFixed(2)} PLN` : '—'}</td>
                  <td className="py-2">
                    {r.direction === 'up'   && <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />}
                    {r.direction === 'down' && <TrendingDown className="w-3.5 h-3.5 text-red-400" />}
                    {r.direction === 'flat' && <Minus className="w-3.5 h-3.5 text-white/30" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Signals */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Sygnały pozytywne">
          <ul className="space-y-2">
            {d.positive_signals.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-white/60">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                {s}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Ryzyka i sygnały negatywne">
          <ul className="space-y-2">
            {d.negative_signals.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-white/60">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
                {s}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <InterpretCard text={d.interpretation} />
    </div>
  )
}


function DividendTab({ d }: { d: EquityReport['dividend'] }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Metryki dywidendy">
          <MetricRow label="Stopa dywidendy (yield)" mv={d.dividend_yield} note=">4% uznawane za atrakcyjne. Sprawdź stabilność wypłat" indicatorId="dividend_yield" />
          <MetricRow label="Payout ratio — % zysku wypłacany" mv={d.payout_ratio} note="40–60% to zdrowy poziom. >80% = ryzyko cięcia" indicatorId="payout_ratio" />
          <MetricRow label="CAGR dywidendy 3-letni" mv={d.dividend_growth_3y} note="Roczny wzrost dywidendy przez 3 lata" />
        </Card>

        {d.last_dividend && (
          <Card title="Ostatnia dywidenda">
            <div className="space-y-2 text-xs">
              <div className="flex justify-between py-1.5 border-b border-white/5">
                <span className="text-white/40">Kwota na akcję</span>
                <span className="text-white font-medium text-sm">{d.last_dividend.amount.toFixed(2)} {d.last_dividend.currency}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-white/5">
                <span className="text-white/40">Dzień ex-dividend (bez prawa)</span>
                <span className="text-white/80">{d.last_dividend.ex_date}</span>
              </div>
              <div className="flex justify-between py-1.5">
                <span className="text-white/40">Data wypłaty</span>
                <span className="text-emerald-400 font-medium">{d.last_dividend.pay_date}</span>
              </div>
            </div>
          </Card>
        )}
      </div>

      <Card title="Historia dywidendy">
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="w-full text-xs min-w-[500px]">
            <thead>
              <tr className="border-b border-white/10">
                {['Rok','DPS (PLN)','Yield','Payout ratio','Status'].map((h, i) => (
                  <th key={i} className="py-2 text-left text-white/35 font-medium pr-6">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...d.history].reverse().map((r) => (
                <tr key={r.year} className="border-b border-white/5 last:border-0">
                  <td className="py-2 pr-6 text-white/70">{r.year}</td>
                  <td className="py-2 pr-6 text-white/80 tabular-nums">{r.dividend_per_share?.toFixed(2) ?? '—'}</td>
                  <td className="py-2 pr-6 tabular-nums">
                    <span className={r.yield_pct && r.yield_pct >= 4 ? 'text-emerald-400' : 'text-white/60'}>
                      {r.yield_pct?.toFixed(1) ?? '—'}%
                    </span>
                  </td>
                  <td className="py-2 pr-6 tabular-nums text-white/60">{r.payout_ratio_pct?.toFixed(1) ?? '—'}%</td>
                  <td className="py-2">
                    {r.paid
                      ? <span className="text-emerald-400">Wypłacona</span>
                      : <span className="text-red-400">Brak</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <InterpretCard text={d.interpretation} />
    </div>
  )
}


function EventsTab({ d }: { d: EquityReport['key_events'] }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Zdarzenia pozytywne">
          <div className="space-y-3">
            {d.positive.map((e, i) => (
              <div key={i} className="border border-emerald-500/15 bg-emerald-500/5 rounded-lg p-3">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <span className="text-xs font-medium text-white/80 leading-snug">{e.title}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${impactCls(e.impact)}`}>
                    {e.impact === 'high' ? 'Wysoki' : e.impact === 'medium' ? 'Średni' : 'Niski'}
                  </span>
                </div>
                <p className="text-[11px] text-white/45 leading-relaxed mb-1">{e.description}</p>
                <span className="text-[10px] text-white/25">{e.date}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Zdarzenia negatywne i ryzyka">
          <div className="space-y-3">
            {d.negative.map((e, i) => (
              <div key={i} className="border border-red-500/15 bg-red-500/5 rounded-lg p-3">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <span className="text-xs font-medium text-white/80 leading-snug">{e.title}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${impactCls(e.impact)}`}>
                    {e.impact === 'high' ? 'Wysoki' : e.impact === 'medium' ? 'Średni' : 'Niski'}
                  </span>
                </div>
                <p className="text-[11px] text-white/45 leading-relaxed mb-1">{e.description}</p>
                <span className="text-[10px] text-white/25">{e.date}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Nadchodzące kluczowe daty">
        <div className="space-y-2">
          {d.upcoming_dates.map((u, i) => {
            const typeCls = u.type === 'earnings' ? 'bg-blue-500/15 text-blue-300' :
              u.type === 'dividend' ? 'bg-emerald-500/15 text-emerald-300' :
              u.type === 'agm' ? 'bg-purple-500/15 text-purple-300' : 'bg-slate-500/15 text-slate-300'
            return (
              <div key={i} className="flex items-center gap-3 py-2 border-b border-white/5 last:border-0">
                <span className="text-white/60 font-mono text-xs w-24 shrink-0">{u.date}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded ${typeCls}`}>
                  {u.type === 'earnings' ? 'Wyniki' : u.type === 'dividend' ? 'Dywidenda' : u.type === 'agm' ? 'WZA' : 'Inne'}
                </span>
                <span className="text-xs text-white/60">{u.event}</span>
              </div>
            )
          })}
        </div>
      </Card>

      <InterpretCard text={d.interpretation} />
    </div>
  )
}

function MoatTab({ d }: { d: EquityReport['advantages_risks'] }) {
  return (
    <div className="space-y-4">
      <Card title="Ocena fosy ekonomicznej (Moat)">
        <div className="flex items-center gap-4">
          <div className="text-4xl font-bold text-blue-400">{d.moat_score}<span className="text-white/25 text-xl">/10</span></div>
          <div>
            <p className="text-white/60 text-sm">{d.moat_type}</p>
            <div className="w-48 h-2.5 bg-white/8 rounded-full mt-1.5 overflow-hidden">
              <div className={`h-full rounded-full ${scoreColor(d.moat_score)}`} style={{ width: `${d.moat_score * 10}%` }} />
            </div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Przewagi konkurencyjne">
          <div className="space-y-3">
            {d.advantages.map((a, i) => (
              <div key={i} className="border-b border-white/5 last:border-0 pb-3 last:pb-0">
                <div className="flex items-start gap-2 mb-1">
                  <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald-400" />
                  <span className="text-xs font-medium text-white/80">{a.title}</span>
                  <span className={`ml-auto text-[10px] shrink-0 font-medium ${strengthCls(a.strength)}`}>
                    {a.strength === 'strong' ? 'Silna' : a.strength === 'moderate' ? 'Umiarkowana' : 'Słaba'}
                  </span>
                </div>
                <p className="text-[11px] text-white/40 leading-relaxed pl-5">{a.description}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Ryzyka">
          <div className="space-y-3">
            {d.risks.map((r, i) => (
              <div key={i} className="border-b border-white/5 last:border-0 pb-3 last:pb-0">
                <div className="flex items-start gap-2 mb-1">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-400" />
                  <span className="text-xs font-medium text-white/80">{r.title}</span>
                  <div className="ml-auto flex gap-1 shrink-0">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${impactCls(r.severity)}`}>
                      {r.severity === 'high' ? 'Wysokie' : r.severity === 'medium' ? 'Śred.' : 'Niskie'}
                    </span>
                  </div>
                </div>
                <p className="text-[11px] text-white/40 leading-relaxed pl-5">{r.description}</p>
                <p className="text-[10px] text-white/25 pl-5 mt-1">
                  Prawdopodobieństwo: {r.probability === 'high' ? 'Wysokie' : r.probability === 'medium' ? 'Średnie' : 'Niskie'}
                </p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <InterpretCard text={d.interpretation} />
    </div>
  )
}

function TechnicalTab({ d, price }: { d: EquityReport['technical']; price: number }) {
  const maSign = (level: number) => price > level
    ? <span className="text-emerald-400 text-[10px]">↑ Powyżej</span>
    : <span className="text-red-400 text-[10px]">↓ Poniżej</span>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Trend ogólny i średnie kroczące">
          <div className="flex items-center gap-2 mb-3 pb-3 border-b border-white/8">
            {trendIcon(d.trend)}
            <span className={`text-sm font-medium ${d.trend === 'bullish' ? 'text-emerald-400' : d.trend === 'bearish' ? 'text-red-400' : 'text-slate-300'}`}>
              {d.trend === 'bullish' ? 'Wzrostowy' : d.trend === 'bearish' ? 'Spadkowy' : 'Neutralny'}
            </span>
          </div>
          <div className="space-y-0">
            <div className="flex items-center justify-between py-2 border-b border-white/5">
              <span className="text-xs text-white/40">MA20 — krótki termin</span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-white">{d.moving_averages.ma_20.value?.toFixed(2)}</span>
                {maSign(d.moving_averages.ma_20.value ?? 0)}
              </div>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-white/5">
              <span className="text-xs text-white/40">MA50 — średni termin</span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-white">{d.moving_averages.ma_50.value?.toFixed(2)}</span>
                {maSign(d.moving_averages.ma_50.value ?? 0)}
              </div>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-xs text-white/40">MA200 — długi termin</span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-white">{d.moving_averages.ma_200.value?.toFixed(2)}</span>
                {maSign(d.moving_averages.ma_200.value ?? 0)}
              </div>
            </div>
          </div>
        </Card>

        <Card title="RSI i Stochastic RSI">
          <MetricRow label="RSI (14) — siła względna" mv={d.rsi} note="<30 = wyprzedany (sygnał kupna), >70 = wykupiony (sygnał sprzedaży)" indicatorId="rsi" />
          <MetricRow label="Stoch RSI %K" mv={d.stoch_rsi.k} note="Szybsza linia — wyprzedza sygnały RSI" />
          <MetricRow label="Stoch RSI %D" mv={d.stoch_rsi.d} note="Wolniejsza (sygnał) — przejście %K przez %D to sygnał" />
          <div className="mt-2 pt-2 border-t border-white/5">
            <p className="text-xs text-white/35">
              Sygnał Stoch RSI:{' '}
              <span className={d.stoch_rsi.signal === 'oversold' ? 'text-emerald-400' : d.stoch_rsi.signal === 'overbought' ? 'text-red-400' : 'text-slate-300'}>
                {d.stoch_rsi.signal === 'oversold' ? 'Wyprzedany (potencjalne dno)' : d.stoch_rsi.signal === 'overbought' ? 'Wykupiony (potencjalny szczyt)' : 'Neutralny'}
              </span>
            </p>
          </div>
        </Card>

        <Card title="MACD — Moving Average Convergence Divergence">
          <MetricRow label="Linia MACD" mv={d.macd.macd_line} note="Różnica MA12 − MA26. Powyżej 0 = trend wzrostowy" />
          <MetricRow label="Linia sygnału (Signal)" mv={d.macd.signal_line} note="9-dniowa EMA linii MACD" />
          <MetricRow label="Histogram MACD" mv={d.macd.histogram} note=">0 i rosnący = byki przejmują kontrolę. <0 = niedźwiedzie" />
          <div className="mt-2 pt-2 border-t border-white/5">
            <p className="text-xs">
              <span className="text-white/35">Sygnał: </span>
              <span className={d.macd.signal === 'bullish' ? 'text-emerald-400' : d.macd.signal === 'bearish' ? 'text-red-400' : 'text-slate-300'}>
                {d.macd.signal === 'bullish' ? 'Bycze' : d.macd.signal === 'bearish' ? 'Niedźwiedzie' : 'Neutralne'}
              </span>
            </p>
          </div>
        </Card>

        <Card title="Wstęgi Bollingera">
          <MetricRow label="Górna wstęga" mv={d.bollinger_bands.upper} note="Strefa oporu / wykupienia w kontekście zmienności" />
          <MetricRow label="Środkowa (MA20)" mv={d.bollinger_bands.middle} />
          <MetricRow label="Dolna wstęga" mv={d.bollinger_bands.lower} note="Strefa wsparcia / wyprzedania w kontekście zmienności" />
          <MetricRow label="Szerokość wstęg" mv={d.bollinger_bands.width_pct} note="Duża szerokość = wysoka zmienność. Ścieśnienie = oczekiwany ruch" />
          <p className="text-xs text-white/35 mt-2">
            Pozycja ceny: {d.bollinger_bands.position === 'upper' ? '↑ Przy górnej — ryzyko odwrócenia' : d.bollinger_bands.position === 'lower' ? '↓ Przy dolnej — szansa odwrócenia' : '→ W środku wstęg — neutralnie'}
          </p>
        </Card>
      </div>

      <Card title="Wsparcia i opory">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-white/35 mb-2 uppercase tracking-wide">Wsparcia (strefy kupna)</p>
            {d.support_resistance.supports.map((s, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0">
                <span className="font-mono text-sm text-emerald-400">{s.level.toFixed(2)} PLN</span>
                <span className={`text-xs ${strengthCls(s.strength)}`}>
                  {s.strength === 'strong' ? 'Silne' : s.strength === 'moderate' ? 'Umiarkowane' : 'Słabe'}
                </span>
              </div>
            ))}
          </div>
          <div>
            <p className="text-xs text-white/35 mb-2 uppercase tracking-wide">Opory (strefy podaży)</p>
            {d.support_resistance.resistances.map((r, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0">
                <span className="font-mono text-sm text-red-400">{r.level.toFixed(2)} PLN</span>
                <span className={`text-xs ${strengthCls(r.strength)}`}>
                  {r.strength === 'strong' ? 'Silny' : r.strength === 'moderate' ? 'Umiarkowany' : 'Słaby'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <InterpretCard text={d.interpretation} />
    </div>
  )
}

function VolumeTab({ d }: { d: EquityReport['volume_liquidity'] }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Metryki wolumenu">
          <MetricRow label="Średni wolumen 30D" mv={d.avg_volume_30d} note="Benchmark — punkt odniesienia dla oceny aktywności" />
          <MetricRow label="Wolumen bieżącej sesji" mv={d.current_volume} />
          <MetricRow label="Ratio (bieżący / 30D avg)" mv={d.volume_ratio} note=">2x = sesja ponadprzeciętna. >3x = sygnał analizy" indicatorId="volume_ratio" />
          <div className="mt-3 pt-3 border-t border-white/5">
            <div className="flex items-center gap-2 mb-1">
              {trendIcon(d.obv_trend)}
              <span className="text-xs text-white/40">OBV trend: <span className={d.obv_signal === 'bullish' ? 'text-emerald-400' : d.obv_signal === 'bearish' ? 'text-red-400' : 'text-slate-300'}>
                {d.obv_signal === 'bullish' ? 'Bycze (akumulacja)' : d.obv_signal === 'bearish' ? 'Niedźwiedzie (dystrybucja)' : 'Neutralne'}
              </span></span>
            </div>
            <p className="text-[10px] text-white/25">On-Balance Volume (OBV): rosnący OBV = kupujący dominują</p>
          </div>
        </Card>

        <Card title="Płynność">
          <div className="mb-3 pb-3 border-b border-white/8">
            <p className="text-xs text-white/35 mb-1">Score płynności</p>
            <div className="flex items-center gap-3">
              <span className={`text-2xl font-bold ${scoreColor(d.liquidity_score) === 'bg-emerald-500' ? 'text-emerald-400' : 'text-amber-400'}`}>
                {d.liquidity_score}<span className="text-white/25 text-base">/10</span>
              </span>
              <div className="flex-1 h-2 bg-white/8 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${scoreColor(d.liquidity_score)}`} style={{ width: `${d.liquidity_score * 10}%` }} />
              </div>
            </div>
          </div>
          <MetricRow label="Spread bid-ask" mv={d.bid_ask_spread_pct} note="<0.1% = płynny. >0.5% = mała płynność, slippage przy dużych pozycjach" />
          <MetricRow label="Akcje w wolnym obrocie (float)" mv={d.float_shares} />
        </Card>
      </div>

      <Card title="Sesje z nadzwyczajnym wolumenem">
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="w-full text-xs min-w-[580px]">
            <thead>
              <tr className="border-b border-white/10">
                {['Data','Wolumen','Avg 30D','Ratio','Zmiana ceny','Typ'].map((h, i) => (
                  <th key={i} className="py-2 text-left text-white/35 font-medium pr-4">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.anomalous_sessions.map((s, i) => (
                <tr key={i} className="border-b border-white/5 last:border-0">
                  <td className="py-2 pr-4 text-white/60 font-mono">{s.date}</td>
                  <td className="py-2 pr-4 text-white/80 tabular-nums">{s.volume.toLocaleString('pl-PL')}</td>
                  <td className="py-2 pr-4 text-white/40 tabular-nums">{s.avg_volume.toLocaleString('pl-PL')}</td>
                  <td className="py-2 pr-4 font-medium tabular-nums">
                    <span className={s.ratio >= 3 ? 'text-amber-400' : 'text-white/60'}>{s.ratio.toFixed(1)}x</span>
                  </td>
                  <td className="py-2 pr-4 tabular-nums">
                    <span className={s.price_change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                      {s.price_change_pct >= 0 ? '+' : ''}{s.price_change_pct.toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                      s.type === 'accumulation' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' :
                      s.type === 'distribution' ? 'bg-red-500/15 text-red-300 border-red-500/25' :
                      'bg-slate-500/15 text-slate-300 border-slate-500/25'
                    }`}>
                      {s.type === 'accumulation' ? 'Akumulacja' : s.type === 'distribution' ? 'Dystrybucja' : 'Neutralna'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <InterpretCard text={d.interpretation} />
    </div>
  )
}

function ShareholdersTab({ d }: { d: EquityReport['shareholders'] }) {
  const changeCls = (dir: string) =>
    dir === 'increased' ? 'text-emerald-400' : dir === 'decreased' ? 'text-red-400' :
    dir === 'new' ? 'text-blue-400' : 'text-white/30'
  const changeLabel = (dir: string) =>
    dir === 'increased' ? '↑' : dir === 'decreased' ? '↓' : dir === 'new' ? 'NEW' : '='

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title="Free Float">
          <MetricRow label="Wolny obrót (free float)" mv={d.free_float_pct} note="% akcji dostępnych na rynku dla inwestorów zewnętrznych" />
        </Card>
        <Card title="Instytucje">
          <MetricRow label="Własność instytucjonalna" mv={d.institutional_ownership_pct} note="OFE, TFI, fundusze zagraniczne" />
        </Card>
        <Card title="Insiderzy">
          <MetricRow label="Własność insiderów" mv={d.insider_ownership_pct} note="Zarząd, rada nadzorcza i powiązane podmioty" />
        </Card>
      </div>

      <Card title="Główni akcjonariusze (>5%)">
        <div className="space-y-0">
          {d.major_shareholders.map((s, i) => (
            <div key={i} className="flex items-center gap-3 py-2.5 border-b border-white/5 last:border-0">
              <div className="flex-1">
                <p className="text-xs text-white/75">{s.name}</p>
                <span className={`text-[10px] ${
                  s.type === 'insider' ? 'text-amber-400' : s.type === 'state' ? 'text-blue-400' :
                  s.type === 'strategic' ? 'text-purple-400' : 'text-slate-400'
                }`}>
                  {s.type === 'insider' ? 'Insider' : s.type === 'state' ? 'Skarb Państwa' : s.type === 'strategic' ? 'Strategiczny' : 'Instytucjonalny'}
                </span>
              </div>
              <div className="w-24 h-1.5 bg-white/8 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500/60 rounded-full" style={{ width: `${Math.min(s.stake_pct * 2, 100)}%` }} />
              </div>
              <span className="font-mono text-sm text-white/80 w-12 text-right">{s.stake_pct.toFixed(1)}%</span>
              <span className={`text-sm font-bold w-8 text-center ${changeCls(s.change_direction)}`}>{changeLabel(s.change_direction)}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Transakcje insiderskie (ostatnie)">
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="w-full text-xs min-w-[680px]">
            <thead>
              <tr className="border-b border-white/10">
                {['Data','Insider','Rola','Typ','Akcji','Cena','Wartość','Źródło'].map((h, i) => (
                  <th key={i} className="py-2 text-left text-white/35 font-medium pr-4">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.insider_transactions.map((t, i) => (
                <tr key={i} className="border-b border-white/5 last:border-0">
                  <td className="py-2 pr-4 text-white/50 font-mono">{t.date}</td>
                  <td className="py-2 pr-4 text-white/70">{t.insider}</td>
                  <td className="py-2 pr-4 text-white/40">{t.role}</td>
                  <td className="py-2 pr-4">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${t.type === 'buy' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' : 'bg-red-500/15 text-red-300 border-red-500/25'}`}>
                      {t.type === 'buy' ? 'ZAKUP' : 'SPRZEDAŻ'}
                    </span>
                  </td>
                  <td className="py-2 pr-4 tabular-nums text-white/60">{t.shares.toLocaleString('pl-PL')}</td>
                  <td className="py-2 pr-4 tabular-nums text-white/60">{t.price.toFixed(2)} {t.currency}</td>
                  <td className="py-2 tabular-nums">
                    <span className={t.type === 'buy' ? 'text-emerald-400' : 'text-red-400'}>
                      {t.type === 'buy' ? '+' : '-'}{(t.value / 1000).toFixed(0)}k {t.currency}
                    </span>
                  </td>
                  <td className="py-2">
                    {t.source_url ? (
                      <a
                        href={t.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] text-blue-300 hover:text-blue-200 transition-colors"
                      >
                        PDF <ExternalLink className="w-3 h-3" />
                      </a>
                    ) : (
                      <span className="text-white/25">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <InterpretCard text={d.interpretation} />
    </div>
  )
}

function VerdictTab({ d, price }: { d: EquityReport['verdict']; price: number }) {
  const recCfg = REC_CONFIG[d.recommendation]
  const probCls = (p: string) =>
    p === 'high' ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' :
    p === 'medium' ? 'text-amber-400 bg-amber-500/10 border-amber-500/20' :
    'text-slate-400 bg-slate-500/10 border-slate-500/20'

  return (
    <div className="space-y-4">
      {/* Summary banner */}
      <div className="bg-gradient-to-r from-slate-800/80 to-slate-800/40 border border-white/10 rounded-xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div>
              <p className="text-xs text-white/35 mb-1 uppercase tracking-wide">Rekomendacja</p>
              <span className={`text-lg font-bold px-4 py-1.5 rounded-lg ${recCfg.cls}`}>{recCfg.label}</span>
            </div>
            <div>
              <p className="text-xs text-white/35 mb-1 uppercase tracking-wide">Score ogólny</p>
              <span className={`text-3xl font-bold ${d.overall_score >= 8 ? 'text-emerald-400' : d.overall_score >= 6 ? 'text-blue-400' : 'text-amber-400'}`}>
                {d.overall_score.toFixed(1)}<span className="text-white/25 text-lg">/10</span>
              </span>
            </div>
            <div>
              <p className="text-xs text-white/35 mb-1 uppercase tracking-wide">Horyzont</p>
              <span className="text-sm text-white/70">
                {d.time_horizon === 'short' ? 'Krótki (< 3m)' : d.time_horizon === 'medium' ? 'Średni (6–12m)' : 'Długi (> 12m)'}
              </span>
            </div>
          </div>
          <div className="text-right">
            <p className="text-xs text-white/35 mb-1 uppercase tracking-wide">Target 12m</p>
            <p className="text-2xl font-bold text-white">
              {d.price_target.value != null ? `${d.price_target.value.toFixed(2)} ${d.price_target.unit ?? ''}`.trim() : '—'}
            </p>
            <p className={`text-sm font-medium ${d.upside_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {d.price_target.value != null
                ? `${d.upside_pct >= 0 ? '+' : ''}${d.upside_pct.toFixed(1)}% od ${price.toFixed(2)} PLN`
                : 'Brak wiarygodnej wyceny 12m'}
            </p>
            <div className="flex items-center gap-1 justify-end mt-0.5">
              <SrcBadge s={d.price_target.source} />
              <ConfBadge c={d.price_target.confidence} />
            </div>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-white/10">
          <p className="text-xs text-white/35 mb-1 uppercase tracking-wide">Dlaczego taki score i price target</p>
          <p className="text-sm text-white/70 leading-relaxed">{d.interpretation}</p>
          {d.price_target.note ? (
            <p className="text-sm text-white/55 leading-relaxed mt-2">{d.price_target.note}</p>
          ) : null}
        </div>
      </div>

      {/* 3 Scenarios */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: 'Scenariusz byczys', case: d.bull_case, cls: 'border-emerald-500/25 bg-emerald-500/5', titleCls: 'text-emerald-400', icon: TrendingUp },
          { label: 'Scenariusz bazowy', case: d.base_case, cls: 'border-blue-500/25 bg-blue-500/5', titleCls: 'text-blue-400', icon: Minus },
          { label: 'Scenariusz niedźwiedzi', case: d.bear_case, cls: 'border-red-500/25 bg-red-500/5', titleCls: 'text-red-400', icon: TrendingDown },
        ].map(({ label, case: c, cls, titleCls, icon: Icon }) => (
          <div key={label} className={`border rounded-xl p-4 ${cls}`}>
            <div className="flex items-start justify-between mb-2">
              <p className="text-[10px] text-white/30 uppercase tracking-wide">{label}</p>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${probCls(c.probability)}`}>
                {c.probability === 'high' ? 'Wysokie prawdop.' : c.probability === 'medium' ? 'Średnie' : 'Niskie'}
              </span>
            </div>
            <Icon className={`w-4 h-4 mb-1.5 ${titleCls}`} />
            <p className={`text-sm font-semibold mb-2 leading-snug ${titleCls}`}>{c.title}</p>
            <p className="text-[11px] text-white/50 leading-relaxed mb-3">{c.description}</p>
            <ul className="space-y-1">
              {c.catalysts_or_risks.map((item, i) => (
                <li key={i} className="text-[11px] text-white/35 flex items-start gap-1.5">
                  <span className={`text-[10px] mt-0.5 ${titleCls}`}>•</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* Valuation × Condition matrix */}
      {(() => {
        const mx = d.valuation_matrix
        const mom = MOMENTUM_CFG[mx.momentum.signal]

        type QDef = {
          id:       'A' | 'B' | 'C' | 'D'
          rowLabel: string
          colLabel: string
          activeCls:   string
          inactiveCls: string
          letterCls:   string
        }
        const QDEFS: QDef[] = [
          { id: 'A', rowLabel: 'TANIA CENA',  colLabel: 'DOBRA KONDYCJA', activeCls: 'border-emerald-500/60 bg-emerald-500/8',  inactiveCls: 'border-white/10 bg-white/3',  letterCls: 'text-emerald-400' },
          { id: 'B', rowLabel: 'TANIA CENA',  colLabel: 'ZŁA KONDYCJA',   activeCls: 'border-amber-500/60  bg-amber-500/8',    inactiveCls: 'border-white/10 bg-white/3',  letterCls: 'text-amber-400' },
          { id: 'C', rowLabel: 'DROGA CENA',  colLabel: 'DOBRA KONDYCJA', activeCls: 'border-blue-500/60   bg-blue-500/8',     inactiveCls: 'border-white/10 bg-white/3',  letterCls: 'text-blue-400' },
          { id: 'D', rowLabel: 'DROGA CENA',  colLabel: 'ZŁA KONDYCJA',   activeCls: 'border-red-500/60    bg-red-500/8',      inactiveCls: 'border-white/10 bg-white/3',  letterCls: 'text-red-400' },
        ]

        return (
          <div className="bg-slate-800/40 border border-white/10 rounded-xl p-4">
            <p className="text-[10px] font-semibold text-white/35 uppercase tracking-widest mb-3">
              Macierz: wycena rynkowa vs kondycja fundamentalna
            </p>

            {/* 2×2 grid */}
            <div className="grid grid-cols-2 gap-2 mb-3">
              {QDEFS.map(({ id, rowLabel, colLabel, activeCls, inactiveCls, letterCls }) => {
                const isActive = mx.current_quadrant === id
                const q = mx.quadrants[id]
                return (
                  <div
                    key={id}
                    className={`rounded-lg border p-3 transition-all ${isActive ? activeCls : inactiveCls}`}
                  >
                    <p className="text-[9px] font-semibold text-white/30 uppercase tracking-widest mb-1">
                      {rowLabel} + {colLabel}
                    </p>
                    <div className="flex items-baseline gap-1.5 mb-1.5">
                      <span className={`text-2xl font-black ${isActive ? letterCls : 'text-white/20'}`}>{id}</span>
                      {isActive && (
                        <span className="text-[10px] text-white/50">← {q.title}</span>
                      )}
                      {!isActive && q.title && (
                        <span className="text-[10px] text-white/30">{q.title}</span>
                      )}
                    </div>
                    <p className={`text-[11px] leading-relaxed ${isActive ? 'text-white/65' : 'text-white/35'}`}>
                      {q.description}
                    </p>
                  </div>
                )
              })}
            </div>

            {/* Momentum signal */}
            <div className={`rounded-lg border px-4 py-3 flex items-start gap-3 ${mom.cls}`}>
              <span className="text-lg leading-none mt-0.5">{mom.icon}</span>
              <div>
                <p className="text-sm font-bold mb-0.5">{mx.momentum.label}</p>
                <p className="text-xs opacity-80 leading-relaxed">{mx.momentum.reasoning}</p>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Key Watchpoints */}
      <Card title="Co monitorować (key watchpoints)">
        <ul className="space-y-2">
          {d.key_watchpoints.map((w, i) => (
            <li key={i} className="flex items-start gap-2.5 text-xs text-white/60 py-1.5 border-b border-white/5 last:border-0">
              <span className="w-5 h-5 rounded-full bg-blue-500/15 text-blue-400 text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {w}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

type Props = {
  report:           EquityReport
  availablePeriods: ReportPeriod[]
}

export function EquityReportPage({ report, availablePeriods }: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState<TabId>('fundamentals')
  const [legendOpen, setLegendOpen] = useState(false)
  const activePeriod = report.meta.period

  function handlePeriodChange(period: string) {
    if (period === activePeriod) return

    const params = new URLSearchParams(searchParams.toString())
    params.set('period', period)
    const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname
    startTransition(() => {
      router.replace(nextUrl)
    })
  }

  function renderTab() {
    switch (activeTab) {
      case 'fundamentals': return <FundamentalsTab d={report.fundamentals} />
      case 'debt':         return <DebtTab d={report.debt_balance} />
      case 'trend':        return <TrendTab d={report.trend_condition} />
      case 'dividend':     return <DividendTab d={report.dividend} />
      case 'events':       return <EventsTab d={report.key_events} />
      case 'moat':         return <MoatTab d={report.advantages_risks} />
      case 'technical':    return <TechnicalTab d={report.technical} price={report.company.price.current} />
      case 'volume':       return <VolumeTab d={report.volume_liquidity} />
      case 'shareholders': return <ShareholdersTab d={report.shareholders} />
      case 'verdict':      return <VerdictTab d={report.verdict} price={report.company.price.current} />
    }
  }

  return (
    <div className="px-4 py-4 max-w-screen-2xl mx-auto">

      {/* Company header */}
      <CompanyHeader company={report.company} meta={report.meta} />

      {/* Report period + freshness */}
      <ReportBanner
        meta={report.meta}
        periods={availablePeriods}
        activePeriod={activePeriod}
        onPeriodChange={handlePeriodChange}
      />

      {/* Tab navigation */}
      <div className="flex items-center bg-slate-800/40 border border-white/10 rounded-xl p-1.5 mb-4 gap-1">
        <div className="flex gap-1 overflow-x-auto flex-1 min-w-0">
          {TABS.map((tab) => {
            const Icon = tab.icon
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as TabId)}
                className={[
                  'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors whitespace-nowrap shrink-0',
                  active
                    ? 'bg-blue-600/30 text-white border border-blue-500/40'
                    : 'text-white/40 hover:text-white/70 hover:bg-white/5',
                ].join(' ')}
                title={tab.label}
              >
                <Icon className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden sm:inline">{tab.short}</span>
              </button>
            )
          })}
        </div>
        <div className="w-px h-5 bg-white/10 shrink-0 mx-1" />
        <button
          onClick={() => setLegendOpen(true)}
          className="shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors whitespace-nowrap text-white/40 hover:text-white/70 hover:bg-white/5"
          title="Legenda wskaźników"
        >
          <BookOpen className="w-3.5 h-3.5 shrink-0" />
          <span className="hidden sm:inline">Legenda</span>
        </button>
      </div>

      {/* Active tab label */}
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-base font-semibold text-white">
          {TABS.find((t) => t.id === activeTab)?.label}
        </h2>
        <div className="flex items-center gap-1.5 ml-auto text-[10px] text-white/25">
          <span className="bg-purple-500/15 text-purple-400 border border-purple-500/25 px-1.5 py-0.5 rounded">AI</span>
          <span>= OpenAI</span>
          <span className="ml-2 bg-blue-500/15 text-blue-400 border border-blue-500/25 px-1.5 py-0.5 rounded">LOC</span>
          <span>= lokalne dane</span>
          <span className="ml-2 bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 px-1 py-0.5 rounded">H</span>
          <span>= wysoka pewność</span>
          <span className="bg-amber-500/15 text-amber-400 border border-amber-500/25 px-1 py-0.5 rounded">M</span>
          <span>= średnia</span>
        </div>
      </div>

      {/* Tab content */}
      {renderTab()}

      <IndicatorLegendDialog open={legendOpen} onClose={() => setLegendOpen(false)} />

    </div>
  )
}
