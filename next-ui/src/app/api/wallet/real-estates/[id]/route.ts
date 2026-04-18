import { NextResponse } from 'next/server'
import { updateRealEstate, deleteRealEstate } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

type Context = { params: Promise<{ id: string }> }

export async function PUT(req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const body = await req.json() as Record<string, unknown>
  const result = await updateRealEstate(userId, id, body)

  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ success: true })
}

export async function DELETE(_req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const ok = await deleteRealEstate(userId, id)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć nieruchomości' }, { status: 400 })
  return NextResponse.json({ success: true })
}
