'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { CashDialog, type CashRow, type CashWalletOpt } from './CashDialog'

type Props = {
  open: boolean
  totalFmt: string
  accountsFmt: string
  physicalFmt: string
  accountsCount: number
  cashHoldings: CashRow[]
  wallets: CashWalletOpt[]
  viewCurrency: string
}

export function CashDialogWrapper({
  open,
  totalFmt,
  accountsFmt,
  physicalFmt,
  accountsCount,
  cashHoldings,
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
    <CashDialog
      key={cashHoldings.map((item) => `${item.id}:${item.name}:${item.amount}:${item.currency}:${item.note}`).join('|')}
      open={isOpen}
      onOpenChange={handleOpenChange}
      totalFmt={totalFmt}
      accountsFmt={accountsFmt}
      physicalFmt={physicalFmt}
      accountsCount={accountsCount}
      cashHoldings={cashHoldings}
      wallets={wallets}
      viewCurrency={viewCurrency}
    />
  )
}
