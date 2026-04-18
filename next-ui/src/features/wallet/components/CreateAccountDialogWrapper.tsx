'use client'

import { useRouter } from 'next/navigation'
import { CreateAccountDialog } from './CreateAccountDialog'

interface Bank {
  id: string
  name: string
  shortname: string
}

interface Props {
  open: boolean
  wallets: { id: string; name: string }[]
  banks: Bank[]
}

export function CreateAccountDialogWrapper({ open, wallets, banks }: Props) {
  const router = useRouter()
  return (
    <CreateAccountDialog
      open={open}
      onOpenChange={(next) => { if (!next) router.push('/wallet') }}
      wallets={wallets}
      banks={banks}
    />
  )
}
