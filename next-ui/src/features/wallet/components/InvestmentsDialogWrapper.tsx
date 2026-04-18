'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { InvestmentsDialog, type RealEstateRow, type MetalRow, type WalletOpt } from './InvestmentsDialog'

type Props = {
  open: boolean
  totalFmt: string
  brokerageFmt: string
  estatesFmt: string
  metalsFmt: string
  realEstates: RealEstateRow[]
  metals: MetalRow[]
  wallets: WalletOpt[]
  viewCurrency: string
}

export function InvestmentsDialogWrapper({
  open,
  totalFmt,
  brokerageFmt,
  estatesFmt,
  metalsFmt,
  realEstates,
  metals,
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
    <InvestmentsDialog
      open={isOpen}
      onOpenChange={handleOpenChange}
      totalFmt={totalFmt}
      brokerageFmt={brokerageFmt}
      estatesFmt={estatesFmt}
      metalsFmt={metalsFmt}
      realEstates={realEstates}
      metals={metals}
      wallets={wallets}
      viewCurrency={viewCurrency}
    />
  )
}
