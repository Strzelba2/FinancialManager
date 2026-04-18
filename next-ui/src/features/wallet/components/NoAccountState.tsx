import Link from 'next/link'
import { Landmark } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
  username: string
}

export function NoAccountState({ username }: Props) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center">
      <div className="p-5 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-6">
        <Landmark className="w-12 h-12 text-emerald-400" />
      </div>

      <h2 className="text-2xl font-semibold text-white mb-2">
        {username ? `${username}, ` : ''}dodaj pierwsze konto
      </h2>
      <p className="text-white/50 max-w-sm mb-8">
        Portfel jest gotowy. Teraz dodaj konto bankowe, oszczędnościowe lub maklerskie,
        aby zacząć śledzić swoje finanse.
      </p>

      <Button asChild className="bg-emerald-600 hover:bg-emerald-500 text-white px-8 py-3 rounded-full text-base">
        <Link href="/wallet?modal=create-account">
          Dodaj konto
        </Link>
      </Button>
    </div>
  )
}
