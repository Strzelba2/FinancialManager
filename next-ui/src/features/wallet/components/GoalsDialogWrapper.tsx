'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { GoalsDialog, type GoalWalletOpt } from './GoalsDialog'
import type { YearGoalOut } from '@/lib/types/wallet'

type Props = {
  open: boolean
  initialGoals: YearGoalOut[]
  wallets: GoalWalletOpt[]
  viewCurrency: string
}

export function GoalsDialogWrapper({ open, initialGoals, wallets, viewCurrency }: Props) {
  const router = useRouter()
  const [isOpen, setIsOpen] = useState(open)

  useEffect(() => { setIsOpen(open) }, [open])

  function handleOpenChange(next: boolean) {
    setIsOpen(next)
    if (!next) router.push('/wallet')
  }

  return (
    <GoalsDialog
      key={initialGoals.map((g) => `${g.id}:${g.rev_target_year}:${g.exp_budget_year}:${g.capital_gain_target_year}`).join('|')}
      open={isOpen}
      onOpenChange={handleOpenChange}
      initialGoals={initialGoals}
      wallets={wallets}
      viewCurrency={viewCurrency}
    />
  )
}
