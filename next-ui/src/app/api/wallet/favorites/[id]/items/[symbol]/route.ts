import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { removeFavoriteItem, deleteAlert } from '@/lib/api/wallet'

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string; symbol: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id: listId, symbol } = await params
  const withAlert = req.nextUrl.searchParams.get('with_alert') !== 'false'

  const ok = await removeFavoriteItem(userId, listId, symbol)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć z listy' }, { status: 400 })

  if (withAlert) {
    await deleteAlert(userId, symbol)
  }

  return NextResponse.json({ ok: true })
}
