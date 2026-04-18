import { NextResponse } from 'next/server'
import { z } from 'zod'
import { createBrokerageEvent } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const Schema = z.object({
  brokerage_account_id: z.string().uuid(),
  instrument_symbol: z.string().min(1).trim(),
  instrument_mic: z.string().min(1).trim(),
  instrument_name: z.string().min(1).trim(),
  kind: z.enum(['BUY', 'SELL', 'DIV']),
  quantity: z.string().min(1).trim(),
  price: z.string().min(1).trim(),
  currency: z.enum(['PLN', 'USD', 'EUR']),
  split_ratio: z.string().min(1).trim(),
  trade_at: z.string().min(1).trim(),
})

export async function POST(req: Request) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const validated = Schema.safeParse(body)
  if (!validated.success) {
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })
  }

  const result = await createBrokerageEvent(userId, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ success: true, data: result.data })
}
