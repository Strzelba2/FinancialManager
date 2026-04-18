import { headers } from 'next/headers'
import { syncUser } from '@/lib/api/wallet'
import { saveWalletUserId } from '@/lib/api/session'
import { fetchEventsPage } from '@/lib/api/brokerageEvents'
import { BrokerageEventsPage } from '@/features/wallet/components/BrokerageEventsPage'

export default async function BrokerageEventsRoute() {
  const headerStore = await headers()
  const username = headerStore.get('x-user') ?? ''
  const first_name = headerStore.get('x-first-name') ?? ''
  const email = headerStore.get('x-email') ?? ''
  const existingUserId = headerStore.get('x-user-id') ?? ''

  const data = await syncUser({ username, first_name, email })

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

  const brokerageAccounts = data.wallets.flatMap((w) =>
    w.brokerage_accounts.map((a) => ({ id: a.id, name: a.name, walletName: w.name }))
  )

  const initialData = await fetchEventsPage({ userId: data.user_id, page: 1, size: 40, view_ccy: 'PLN' })

  return (
    <BrokerageEventsPage
      brokerageAccounts={brokerageAccounts}
      initialData={initialData}
    />
  )
}
