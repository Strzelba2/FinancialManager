import { headers } from 'next/headers'
import { Mail, User } from 'lucide-react'
import { getTwoFactorStatus } from '@/features/auth/actions/two-factor'
import { TwoFactorSettings } from '@/features/auth/components/TwoFactorSettings'

export default async function ProfileSettingsPage() {
  const headerStore = await headers()
  const username = headerStore.get('x-user') ?? ''
  const firstName = headerStore.get('x-first-name') ?? ''
  const email = headerStore.get('x-email') ?? ''
  const status = await getTwoFactorStatus()

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-8">
      <section className="rounded-lg border border-white/10 bg-white/5 p-5 text-white shadow-xl">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
            <User className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">Profil</h1>
            <p className="text-sm text-white/60">Ustawienia konta i zabezpieczeń</p>
          </div>
        </div>

        <dl className="mt-6 grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-white/10 bg-white/5 p-4">
            <dt className="text-xs uppercase text-white/50">Użytkownik</dt>
            <dd className="mt-1 text-sm font-medium">{username || 'User'}</dd>
          </div>
          <div className="rounded-lg border border-white/10 bg-white/5 p-4">
            <dt className="text-xs uppercase text-white/50">Imię</dt>
            <dd className="mt-1 text-sm font-medium">{firstName || '-'}</dd>
          </div>
          <div className="rounded-lg border border-white/10 bg-white/5 p-4">
            <dt className="flex items-center gap-1 text-xs uppercase text-white/50">
              <Mail className="h-3.5 w-3.5" />
              Email
            </dt>
            <dd className="mt-1 text-sm font-medium">{email || '-'}</dd>
          </div>
        </dl>

        {status.message && (
          <p className="mt-4 text-sm text-amber-200">{status.message}</p>
        )}
      </section>

      <TwoFactorSettings initialEnabled={status.isTwoFactorEnabled} />
    </main>
  )
}
