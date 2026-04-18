import { Wallet } from 'lucide-react'

export function NoWalletState({ username }: { username: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-32 text-white/60 gap-4">
      <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-400/20 flex items-center justify-center">
        <Wallet className="w-8 h-8 text-emerald-400" />
      </div>
      <h2 className="text-xl font-semibold text-white">
        Witaj, {username}!
      </h2>
      <p className="text-center max-w-sm text-sm leading-relaxed">
        Nie masz jeszcze żadnego portfela. Utwórz pierwszy korzystając z menu{' '}
        <strong className="text-white">Portfel → Dodaj portfel…</strong> w nawigacji.
      </p>
    </div>
  )
}
