'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { RecurringExpensesDialog, type ExpenseWalletOpt } from './RecurringExpensesDialog'
import type { RecurringExpenseOut } from '@/lib/types/wallet'

type Props = {
  open: boolean
  initialExpenses: RecurringExpenseOut[]
  wallets: ExpenseWalletOpt[]
  viewCurrency: string
}

export function RecurringExpensesDialogWrapper({ open, initialExpenses, wallets, viewCurrency }: Props) {
  const router = useRouter()
  const [isOpen, setIsOpen] = useState(open)

  useEffect(() => { setIsOpen(open) }, [open])

  function handleOpenChange(next: boolean) {
    setIsOpen(next)
    if (!next) router.push('/wallet')
  }

  return (
    <RecurringExpensesDialog
      key={initialExpenses.map((e) => `${e.id}:${e.amount}:${e.due_day}`).join('|')}
      open={isOpen}
      onOpenChange={handleOpenChange}
      initialExpenses={initialExpenses}
      wallets={wallets}
      viewCurrency={viewCurrency}
    />
  )
}
