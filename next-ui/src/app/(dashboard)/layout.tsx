import { headers } from 'next/headers'
import { DashboardNav } from '@/components/dashboard/nav'
import { SiteFooter } from '@/components/SiteFooter'

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const username = (await headers()).get('x-user') ?? ''

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-slate-900 via-emerald-950 to-slate-900">
      <DashboardNav username={username} />
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </div>
  )
}
