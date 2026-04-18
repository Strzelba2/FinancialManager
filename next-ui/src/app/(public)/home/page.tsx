import Link from 'next/link'
import { BarChart2, PiggyBank, Bell } from 'lucide-react'

export default function HomePage() {
  return (
    <div className="text-white">

      {/* ── Hero ───────────────────────────────────────────────────── */}
      <section className="flex flex-col items-center justify-center text-center px-6 py-28 gap-6">
        <h1 className="text-5xl font-bold tracking-tight">
          Zyskaj kontrolę nad{' '}
          <span className="text-emerald-400">swoimi finansami</span>
        </h1>
        <p className="max-w-xl text-white/60 text-lg leading-relaxed">
          Śledź wydatki, planuj oszczędności i analizuj swój portfel inwestycyjny —
          wszystko w jednym miejscu.
        </p>
        <div className="flex gap-4 mt-2">
          <Link
            href="/register"
            className="px-6 py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 font-medium transition-colors"
          >
            Zarejestruj się
          </Link>
          <Link
            href="/login"
            className="px-6 py-3 rounded-full border border-white/20 hover:bg-white/10 font-medium transition-colors"
          >
            Zaloguj się
          </Link>
        </div>
      </section>

      {/* ── Features ───────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-24 grid grid-cols-1 sm:grid-cols-3 gap-6">
        {[
          {
            icon: BarChart2,
            title: 'Analizuj wydatki i przychody',
            desc: 'Szczegółowe wykresy i raporty pomagają lepiej zrozumieć Twoje finanse.',
          },
          {
            icon: PiggyBank,
            title: 'Planuj cele oszczędnościowe',
            desc: 'Ustalaj cele i obserwuj swoje postępy w odkładaniu środków.',
          },
          {
            icon: Bell,
            title: 'Otrzymuj powiadomienia',
            desc: 'Bądź na bieżąco z limitem wydatków i ważnymi terminami.',
          },
        ].map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="backdrop-blur-md bg-white/5 border border-white/10 rounded-2xl p-6 flex flex-col gap-3 hover:bg-white/10 transition-colors"
          >
            <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center">
              <Icon className="w-5 h-5 text-emerald-400" />
            </div>
            <h3 className="font-semibold">{title}</h3>
            <p className="text-sm text-white/50 leading-relaxed">{desc}</p>
          </div>
        ))}
      </section>

      {/* ── Why us ─────────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 pb-28 text-center">
        <h2 className="text-2xl font-semibold mb-8">Dlaczego warto wybrać FinancialManager?</h2>
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
          {[
            'Intuicyjny interfejs – zacznij w minutę',
            'Bezpieczne przechowywanie danych',
            'Import wyciągów z mBank, ING, BOSSA, Saxo',
            'Możliwość eksportu raportów',
          ].map((item) => (
            <li
              key={item}
              className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white/70"
            >
              <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
              {item}
            </li>
          ))}
        </ul>
      </section>

    </div>
  )
}
