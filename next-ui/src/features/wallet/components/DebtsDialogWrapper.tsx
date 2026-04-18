'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { DebtsDialog, type DebtRow, type DebtWalletOpt } from './DebtsDialog'

type Props = {
  open: boolean
  totalFmt: string
  subtitle: string
  countFmt: string
  avgRateFmt: string
  monthlyFmt: string
  debts: DebtRow[]
  wallets: DebtWalletOpt[]
  viewCurrency: string
}

export function DebtsDialogWrapper({
  open,
  totalFmt,
  subtitle,
  countFmt,
  avgRateFmt,
  monthlyFmt,
  debts,
  wallets,
  viewCurrency,
}: Props) {
  const router = useRouter()
  const [isOpen, setIsOpen] = useState(open)

  useEffect(() => { setIsOpen(open) }, [open])

  function handleOpenChange(next: boolean) {
    setIsOpen(next)
    if (!next) router.push('/wallet')
  }

  return (
    <DebtsDialog
      key={debts.map((debt) => `${debt.id}:${debt.amount}:${debt.monthlyPayment}:${debt.endDate}`).join('|')}
      open={isOpen}
      onOpenChange={handleOpenChange}
      totalFmt={totalFmt}
      subtitle={subtitle}
      countFmt={countFmt}
      avgRateFmt={avgRateFmt}
      monthlyFmt={monthlyFmt}
      debts={debts}
      wallets={wallets}
      viewCurrency={viewCurrency}
    />
  )
}
