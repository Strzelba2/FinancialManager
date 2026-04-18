import { NextResponse } from 'next/server'
import { z } from 'zod'
import { importBrokerageEvents } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const EventSchema = z.object({
  trade_at: z.string().min(1).trim(),
  instrument_symbol: z.string().min(1).trim(),
  instrument_mic: z.string().min(1).trim(),
  instrument_name: z.string().trim().nullish(),
  kind: z.enum(['BUY', 'SELL', 'SPLIT', 'DIV']),
  quantity: z.string().min(1).trim(),
  price: z.string().min(1).trim(),
  currency: z.enum(['PLN', 'USD', 'EUR']),
  split_ratio: z.string().min(1).trim(),
})

const Schema = z.object({
  brokerage_account_id: z.string().uuid(),
  events: z.array(EventSchema).min(1, { message: 'Dodaj co najmniej jedno zdarzenie' }),
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

  const result = await importBrokerageEvents(userId, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data)
}
