import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { deleteBrokerageEvent } from '@/lib/api/wallet'

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id } = await params
  const ok = await deleteBrokerageEvent(userId, id)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć operacji' }, { status: 400 })
  return NextResponse.json({ ok: true })
}
