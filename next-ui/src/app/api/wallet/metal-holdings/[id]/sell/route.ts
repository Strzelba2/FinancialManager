import { NextResponse } from 'next/server'
import { sellMetalHolding } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

type Context = { params: Promise<{ id: string }> }

export async function POST(req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const body = await req.json() as Record<string, unknown>
  const result = await sellMetalHolding(userId, id, body)

  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ success: true })
}
