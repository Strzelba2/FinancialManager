'use client'

import { useRouter } from 'next/navigation'
import { DeleteWalletDialog } from './DeleteWalletDialog'

interface Props {
  open: boolean
  wallets: { id: string; name: string }[]
}

export function DeleteWalletDialogWrapper({ open, wallets }: Props) {
  const router = useRouter()
  return (
    <DeleteWalletDialog
      open={open}
      onOpenChange={(next) => { if (!next) router.push('/wallet') }}
      wallets={wallets}
    />
  )
}
