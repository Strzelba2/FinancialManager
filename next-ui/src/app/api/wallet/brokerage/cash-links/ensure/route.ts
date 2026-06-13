import { NextResponse } from 'next/server'
import { z } from 'zod'
import { ensureBrokerageCashLinks } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const Schema = z.object({
  brokerage_account_id: z.string().uuid(),
  cash_accounts: z.array(z.object({
    currency: z.enum(['USD', 'EUR']),
    account_number: z.string().min(1, { message: 'Podaj numer albo techniczny identyfikator subkonta' }).max(32).trim(),
    name: z.string().max(64).trim().optional(),
    iban: z.string().max(34).trim().optional(),
  })).min(1, { message: 'Dodaj co najmniej jedno subkonto' }),
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

  const { brokerage_account_id, cash_accounts } = validated.data
  const result = await ensureBrokerageCashLinks(userId, brokerage_account_id, { cash_accounts })
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 422 })
  return NextResponse.json(result.data)
}
