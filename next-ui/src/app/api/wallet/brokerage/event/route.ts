import { NextResponse } from 'next/server'
import { z } from 'zod'
import { createBrokerageEvent } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const Schema = z.object({
  brokerage_account_id: z.string().uuid(),
  instrument_symbol: z.string().min(1).trim(),
  instrument_mic: z.string().min(1).trim(),
  instrument_name: z.string().min(1).trim(),
  kind: z.enum(['BUY', 'SELL', 'DIV', 'SPLIT', 'ADJUSTMENT', 'CONVERSION']),
  quantity: z.string().min(1).trim(),
  price: z.string().min(1).trim(),
  // Instrument/quote (trade) currency — may be a non-base currency (e.g. CHF, GBP).
  currency: z.enum(['PLN', 'USD', 'EUR', 'GBP', 'CHF']),
  split_ratio: z.string().min(1).trim(),
  note: z.string().max(500).trim().nullish(),
  target_instrument_symbol: z.string().trim().optional(),
  target_instrument_mic: z.string().trim().optional(),
  target_instrument_name: z.string().trim().optional(),
  trade_at: z.string().min(1).trim(),
}).superRefine((data, ctx) => {
  if (data.kind === 'ADJUSTMENT' && !data.note?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['note'],
      message: 'Podaj notatkę korekty',
    })
  }
  if (data.kind === 'CONVERSION') {
    if (!data.note?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['note'],
        message: 'Podaj notatkę konwersji',
      })
    }
    if (!data.target_instrument_symbol?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['target_instrument_symbol'],
        message: 'Podaj symbol instrumentu docelowego',
      })
    }
    if (!data.target_instrument_mic?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['target_instrument_mic'],
        message: 'Podaj rynek instrumentu docelowego',
      })
    }
  }
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
