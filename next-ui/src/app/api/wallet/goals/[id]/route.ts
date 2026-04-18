import { NextResponse } from 'next/server'
import { deleteWalletGoal } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

type Context = { params: Promise<{ id: string }> }

export async function DELETE(_req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const ok = await deleteWalletGoal(userId, id)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć celu' }, { status: 400 })
  return NextResponse.json({ success: true })
}
