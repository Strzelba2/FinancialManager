'use client'

import { useRouter } from 'next/navigation'
import { CreateWalletDialog } from './CreateWalletDialog'

interface Props {
  open: boolean
}

export function CreateWalletDialogWrapper({ open }: Props) {
  const router = useRouter()
  return (
    <CreateWalletDialog
      open={open}
      onOpenChange={(next) => { if (!next) router.push('/wallet') }}
    />
  )
}
