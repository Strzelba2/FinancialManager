import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'

type Props = {
  title: string
  value: string
  sub?: string
  onClick?: () => void
  href?: string
}

export function KpiCard({ title, value, sub, onClick, href }: Props) {
  const card = (
    <Card
      onClick={onClick}
      className={`bg-slate-800/60 border-white/10 text-white h-full ${(onClick || href) ? 'cursor-pointer hover:bg-slate-700/60 transition-colors' : ''}`}
    >
      <CardContent className="pt-4 pb-3 px-4">
        <p className="text-xs text-white/50 uppercase tracking-wide mb-1">{title}</p>
        <p className="text-xl font-semibold truncate">{value}</p>
        {sub && <p className="text-xs text-white/40 mt-1 truncate">{sub}</p>}
      </CardContent>
    </Card>
  )

  if (href) {
    return <Link href={href} className="block h-full">{card}</Link>
  }
  return card
}
