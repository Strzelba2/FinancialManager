import { NextResponse } from 'next/server'
import { deleteTransaction } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const { id } = await params
  const ok = await deleteTransaction(userId, id)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć transakcji' }, { status: 400 })

  return NextResponse.json({ success: true })
}
