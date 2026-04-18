'use client'

// Dashboard error boundary — catches runtime errors inside (dashboard) routes.
// Also shown when Traefik ForwardAuth returns an error body (401/403) that
// Next.js cannot parse as a valid page.

import { useEffect } from 'react'
import Link from 'next/link'

type Props = {
  error: Error & { digest?: string }
  reset: () => void
}

export default function DashboardError({ error, reset }: Props) {
  useEffect(() => {
    console.error('[dashboard] error boundary caught:', error)
  }, [error])

  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-4">
      <div className="backdrop-blur-md bg-white/5 border border-white/10 rounded-2xl p-8 max-w-sm w-full text-center space-y-4">
        <p className="text-5xl font-bold text-white/10">!</p>
        <h1 className="text-xl font-semibold text-white">Coś poszło nie tak</h1>
        <p className="text-white/50 text-sm">
          Sesja mogła wygasnąć lub wystąpił błąd serwera.
        </p>
        <div className="flex flex-col gap-2 pt-2">
          <button
            onClick={reset}
            className="w-full px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
          >
            Spróbuj ponownie
          </button>
          <Link
            href="/login"
            className="w-full px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5 text-white/70 hover:text-white text-sm font-medium transition-colors"
          >
            Przejdź do logowania
          </Link>
        </div>
      </div>
    </main>
  )
}
