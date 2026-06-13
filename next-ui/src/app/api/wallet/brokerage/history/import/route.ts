import { NextResponse } from 'next/server'
import { z } from 'zod'
import { importBrokerageHistory } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const HistoryRowSchema = z.object({
  row_number: z.number().int().positive(),
  operation_type: z.string().min(1).trim(),
  trade_at: z.string().min(1).trim(),
  currency: z.enum(['PLN', 'USD', 'EUR']),
  amount: z.string().or(z.number()),
  amount_after: z.string().or(z.number()),
  description: z.string().min(1).trim(),
  capital_gain_kind: z.string().trim().nullish(),
  instrument_symbol: z.string().trim().nullish(),
  instrument_mic: z.string().trim().nullish(),
  instrument_name: z.string().trim().nullish(),
  event_kind: z.enum(['BUY', 'SELL', 'SPLIT', 'DIV', 'ADJUSTMENT', 'CONVERSION']).nullish(),
  quantity: z.string().or(z.number()).nullish(),
  price: z.string().or(z.number()).nullish(),
  split_ratio: z.string().or(z.number()).nullish(),
  review_reason: z.string().trim().nullish(),
})

const Schema = z.object({
  brokerage_account_id: z.string().uuid(),
  rows: z.array(HistoryRowSchema).min(1, { message: 'Dodaj co najmniej jeden wiersz historii' }),
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

  const result = await importBrokerageHistory(userId, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data)
}
