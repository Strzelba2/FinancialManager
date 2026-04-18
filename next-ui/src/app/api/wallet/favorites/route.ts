import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { listFavoriteLists, createFavoriteList } from '@/lib/api/wallet'

export async function GET() {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const lists = await listFavoriteLists(userId)
  return NextResponse.json(lists)
}

export async function POST(req: NextRequest) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({})) as { name?: string; description?: string | null }
  if (!body.name?.trim()) {
    return NextResponse.json({ error: 'Nazwa listy jest wymagana' }, { status: 400 })
  }

  const result = await createFavoriteList(userId, { name: body.name.trim(), description: body.description ?? null })
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data, { status: 201 })
}
