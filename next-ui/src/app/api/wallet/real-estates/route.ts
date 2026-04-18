import { NextResponse } from 'next/server'
import { createRealEstate } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

export async function POST(req: Request) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const body = await req.json() as Record<string, unknown>
  const result = await createRealEstate(userId, body)

  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ success: true })
}
