import Link from 'next/link'

export function SiteFooter() {
  return (
    <footer className="border-t border-white/10 py-6 px-6">
      <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-white/40">
        <span>
          <strong className="text-white/60">FinancialManager</strong> © {new Date().getFullYear()}
        </span>
        <div className="flex gap-4">
          <Link href="#" className="hover:text-white/70 transition-colors">Polityka prywatności</Link>
          <Link href="#" className="hover:text-white/70 transition-colors">Kontakt</Link>
        </div>
      </div>
    </footer>
  )
}
