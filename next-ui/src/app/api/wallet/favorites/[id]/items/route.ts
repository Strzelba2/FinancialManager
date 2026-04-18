import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { addFavoriteItem } from '@/lib/api/wallet'

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id: listId } = await params
  const body = await req.json().catch(() => ({})) as { symbol?: string; mic?: string; name?: string }

  if (!body.symbol?.trim()) {
    return NextResponse.json({ error: 'symbol jest wymagany' }, { status: 400 })
  }

  const ok = await addFavoriteItem(
    userId,
    listId,
    body.symbol.trim().toUpperCase(),
    (body.mic ?? 'XWAR').trim().toUpperCase(),
    (body.name ?? body.symbol).trim(),
  )

  if (!ok) return NextResponse.json({ error: 'Nie udało się dodać do listy' }, { status: 400 })
  return NextResponse.json({ ok: true }, { status: 201 })
}
