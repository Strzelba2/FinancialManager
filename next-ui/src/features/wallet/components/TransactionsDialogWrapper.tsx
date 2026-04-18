'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  TransactionsDialog,
  type TransactionAccountOpt,
  type TransactionBrokerageAccountOpt,
} from './TransactionsDialog'

type Props = {
  open: boolean
  accounts: TransactionAccountOpt[]
  brokerageAccounts: TransactionBrokerageAccountOpt[]
}

export function TransactionsDialogWrapper({ open, accounts, brokerageAccounts }: Props) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [isOpen, setIsOpen] = useState(open)

  useEffect(() => {
    setIsOpen(open)
  }, [open])

  function handleOpenChange(next: boolean) {
    setIsOpen(next)

    if (!next) {
      const params = new URLSearchParams(searchParams.toString())
      params.delete('modal')
      const query = params.toString()
      router.push(query ? `/wallet?${query}` : '/wallet')
    }
  }

  return (
    <TransactionsDialog
      open={isOpen}
      onOpenChange={handleOpenChange}
      accounts={accounts}
      brokerageAccounts={brokerageAccounts}
    />
  )
}
