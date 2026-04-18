import { headers } from 'next/headers'
import { syncUser } from '@/lib/api/wallet'
import { saveWalletUserId } from '@/lib/api/session'
import { TransactionsPage } from '@/features/wallet/components/TransactionsPage'
import type { TransactionAccountOpt, TransactionBrokerageAccountOpt } from '@/features/wallet/components/TransactionsDialog'

export default async function TransactionsListPage() {
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

  const accounts: TransactionAccountOpt[] = data.wallets.flatMap((wallet) =>
    wallet.accounts.map((account) => {
      const latestTransaction = account.last_transactions?.[0] ?? null
      return {
        id: account.id,
        name: account.name,
        walletName: wallet.name,
        currency: account.currency,
        available: account.available,
        lastTransactionAt: latestTransaction?.date_transaction ?? null,
        lastBalanceAfter: latestTransaction?.balance_after ?? account.available,
      }
    }),
  )

  const brokerageAccounts: TransactionBrokerageAccountOpt[] = data.wallets.flatMap((wallet) =>
    wallet.brokerage_accounts.map((account) => ({
      id: account.id,
      name: account.name,
      walletName: wallet.name,
    })),
  )

  return <TransactionsPage accounts={accounts} brokerageAccounts={brokerageAccounts} />
}
