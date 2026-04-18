import { NextResponse } from 'next/server'
import { z } from 'zod'
import { createRecurringExpense } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const Schema = z.object({
  wallet_id: z.string().uuid(),
  name: z.string().min(1, { message: 'Podaj nazwę wydatku' }).max(255).trim(),
  category: z.string().max(255).trim().optional(),
  amount: z.string().min(1, { message: 'Podaj kwotę' }).trim(),
  currency: z.enum(['PLN', 'USD', 'EUR']),
  due_day: z.number().int().min(1).max(31),
  account: z.string().max(255).trim().optional(),
  note: z.string().max(500).trim().optional(),
})

export async function POST(req: Request) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  let body: unknown
  try { body = await req.json() } catch {
    return NextResponse.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const validated = Schema.safeParse(body)
  if (!validated.success)
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })

  const result = await createRecurringExpense(userId, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data)
}
