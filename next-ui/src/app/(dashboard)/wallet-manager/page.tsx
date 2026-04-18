import { headers } from 'next/headers'
import { syncUser, getWalletManagerTree } from '@/lib/api/wallet'
import { saveWalletUserId } from '@/lib/api/session'
import { getFxRates } from '@/lib/api/nbp'
import type { FxRates } from '@/lib/api/nbp'
import { WalletManagerPage } from '@/features/wallet/components/WalletManagerPage'
import type { WalletManagerNode } from '@/lib/api/wallet'

export default async function WalletManagerRoute() {
  const headerStore = await headers()
  const username = headerStore.get('x-user') ?? ''
  const first_name = headerStore.get('x-first-name') ?? ''
  const email = headerStore.get('x-email') ?? ''
  const existingUserId = headerStore.get('x-user-id') ?? ''

  const [data, rates] = await Promise.all([
    syncUser({ username, first_name, email }),
    getFxRates(),
  ])

  if (data && !existingUserId) {
    await saveWalletUserId(data.user_id)
  }

  if (!data) {
    return (
      <div className="p-8 text-white">
        <p className="text-red-400">Nie udało się pobrać danych portfela. Spróbuj ponownie.</p>
      </div>
    )
  }

  const currencyRate: Record<string, string> = {}
  if (rates) {
    for (const [k, v] of Object.entries(rates)) {
      currencyRate[k] = String(v)
    }
  }

  const wallets: WalletManagerNode[] = await getWalletManagerTree(data.user_id, currencyRate, 2) ?? []

  return (
    <WalletManagerPage
      wallets={wallets}
      fxRates={rates as FxRates | null}
    />
  )
}
