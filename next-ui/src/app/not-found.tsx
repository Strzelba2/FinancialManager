import Link from 'next/link'

export default function NotFound() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-4">
      <div className="text-center space-y-4">
        <p className="text-7xl font-bold text-white/10">404</p>
        <h1 className="text-2xl font-semibold text-white">Strona nie istnieje</h1>
        <p className="text-white/50 text-sm">Sprawdź adres URL lub wróć do poprzedniej strony.</p>
        <Link
          href="/home"
          className="inline-block mt-4 px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
        >
          Wróć na stronę główną
        </Link>
      </div>
    </main>
  )
}
