import { NextResponse } from 'next/server'
import { z } from 'zod'
import { upsertWalletGoal } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const Schema = z.object({
  wallet_id: z.string().uuid(),
  year: z.number().int().min(2000).max(2100),
  rev_target_year: z.string().min(1, { message: 'Podaj cel przychodów' }).trim(),
  exp_budget_year: z.string().min(1, { message: 'Podaj budżet wydatków' }).trim(),
  capital_gain_target_year: z.string().min(1, { message: 'Podaj cel zysku kapitałowego' }).trim().default('0.00'),
  currency: z.enum(['PLN', 'USD', 'EUR']),
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

  const result = await upsertWalletGoal(userId, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data)
}
