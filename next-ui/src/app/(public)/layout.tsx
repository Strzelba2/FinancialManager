import Link from 'next/link'
import { TrendingUp } from 'lucide-react'
import { SiteFooter } from '@/components/SiteFooter'

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-slate-900 via-emerald-950 to-slate-900">
      <PublicNav />
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </div>
  )
}

function PublicNav() {
  return (
    <nav className="sticky top-0 z-50 backdrop-blur-md bg-white/5 border-b border-white/10">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link href="/home" className="flex items-center gap-2 text-white font-semibold text-lg">
          <TrendingUp className="w-5 h-5 text-emerald-400" />
          FinancialManager
        </Link>

        {/* Links */}
        <div className="flex items-center gap-6 text-sm text-white/70">
          <Link href="/home" className="hover:text-white transition-colors">Home</Link>
          <Link href="/login" className="hover:text-white transition-colors">Logowanie</Link>
          <Link
            href="/register"
            className="px-4 py-1.5 rounded-full bg-emerald-500 hover:bg-emerald-400 text-white transition-colors"
          >
            Rejestracja
          </Link>
        </div>
      </div>
    </nav>
  )
}

