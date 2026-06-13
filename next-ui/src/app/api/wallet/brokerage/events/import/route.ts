import { NextResponse } from 'next/server'
import { z } from 'zod'
import { importBrokerageEvents } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const EventSchema = z.object({
  trade_at: z.string().min(1).trim(),
  instrument_symbol: z.string().min(1).trim(),
  instrument_mic: z.string().min(1).trim(),
  instrument_name: z.string().trim().nullish(),
  kind: z.enum(['BUY', 'SELL', 'SPLIT', 'DIV', 'ADJUSTMENT']),
  quantity: z.string().min(1).trim(),
  price: z.string().min(1).trim(),
  // Instrument/quote (trade) currency — may be a non-base currency (e.g. CHF, GBP).
  currency: z.enum(['PLN', 'USD', 'EUR', 'GBP', 'CHF']),
  split_ratio: z.string().min(1).trim(),
  note: z.string().max(500).trim().nullish(),
  // Cash settlement (account/base) currency + FX rate (instrument -> settlement).
  settlement_currency: z.enum(['PLN', 'USD', 'EUR']).nullish(),
  fx_rate: z.string().trim().nullish(),
}).superRefine((data, ctx) => {
  if (data.kind === 'ADJUSTMENT' && !data.note?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['note'],
      message: 'Podaj notatkę korekty',
    })
  }
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
    const detail = validated.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(body)'}: ${issue.message}`)
      .join('; ')
    return NextResponse.json({ error: detail || 'Nieprawidłowe dane' }, { status: 422 })
  }

  const result = await importBrokerageEvents(userId, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data)
}
