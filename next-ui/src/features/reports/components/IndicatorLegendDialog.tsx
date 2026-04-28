'use client'
import { X, BookOpen } from 'lucide-react'
import { INDICATORS, INDICATOR_CATEGORIES } from '../data/indicators'

export function IndicatorLegendDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-start justify-center pt-12 px-4 bg-black/70 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-6xl max-h-[82vh] overflow-hidden flex flex-col shadow-2xl">
        <div className="px-6 py-4 border-b border-white/10 flex items-center gap-3 shrink-0">
          <BookOpen className="w-4 h-4 text-blue-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-white">Legenda wskaźników</h2>
            <p className="text-xs text-white/40 mt-0.5">Progi diagnostyczne — interpretacja kolorów wskaźników w raporcie</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 px-2.5 py-0.5 rounded-full font-medium">Zdrowo</span>
            <span className="text-xs bg-amber-500/15 text-amber-400 border border-amber-500/25 px-2.5 py-0.5 rounded-full font-medium">Uważaj</span>
            <span className="text-xs bg-red-500/15 text-red-400 border border-red-500/25 px-2.5 py-0.5 rounded-full font-medium">Alarm</span>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-white/40 hover:text-white hover:bg-white/8 transition-colors shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-6">
          {INDICATOR_CATEGORIES.map((category) => {
            const items = INDICATORS.filter((ind) => ind.category === category)
            if (items.length === 0) return null
            return (
              <div key={category}>
                <p className="text-[10px] font-bold text-white/35 uppercase tracking-widest mb-2">{category}</p>
                <div className="border border-white/8 rounded-xl overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-white/8 bg-slate-800/60">
                        <th className="py-2 px-3 text-left text-white/40 font-medium w-36">Wskaźnik</th>
                        <th className="py-2 px-3 text-left text-white/40 font-medium w-48">Wzór / Obliczenie</th>
                        <th className="py-2 px-3 text-left text-emerald-400 font-medium w-32">Zdrowo</th>
                        <th className="py-2 px-3 text-left text-amber-400 font-medium w-28">Uważaj</th>
                        <th className="py-2 px-3 text-left text-red-400 font-medium w-40">Alarm (unikaj)</th>
                        <th className="py-2 px-3 text-left text-white/40 font-medium">Uwaga kontekstowa</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((ind, i) => (
                        <tr
                          key={ind.id}
                          className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? 'bg-slate-800/20' : 'bg-slate-800/5'}`}
                        >
                          <td className="py-2.5 px-3 text-white/70 font-medium leading-tight">{ind.name}</td>
                          <td className="py-2.5 px-3 text-white/40 leading-tight">{ind.formula}</td>
                          <td className="py-2.5 px-3 text-emerald-400 leading-tight">{ind.healthyLabel}</td>
                          <td className="py-2.5 px-3 text-amber-400 leading-tight">{ind.cautionLabel}</td>
                          <td className="py-2.5 px-3 text-red-400 leading-tight">{ind.dangerLabel}</td>
                          <td className="py-2.5 px-3 text-white/35 leading-relaxed">{ind.context}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
