import { headers } from 'next/headers'
import { syncUser } from '@/lib/api/wallet'
import { saveWalletUserId } from '@/lib/api/session'
import { fetchHoldings } from '@/lib/api/holdings'
import { HoldingsPage } from '@/features/wallet/components/HoldingsPage'

export default async function BrokerageHoldingsRoute() {
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

  const result = await fetchHoldings({ userId: data.user_id, view_ccy: 'PLN' })

  return (
    <HoldingsPage
      initialRows={result.rows}
      initialTotalValue={result.totalValueView}
      initialTotalCost={result.totalCostView}
      initialViewCcy={result.viewCcy}
      fxRates={result.fxRates}
      brokerageAccounts={result.brokerageAccounts}
    />
  )
}
