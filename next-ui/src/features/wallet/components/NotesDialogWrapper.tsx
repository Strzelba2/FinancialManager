'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { NotesDialog } from './NotesDialog'

type Props = {
  open: boolean
}

export function NotesDialogWrapper({ open }: Props) {
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

  return <NotesDialog open={isOpen} onOpenChange={handleOpenChange} />
}
