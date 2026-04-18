import { NextResponse } from 'next/server'
import { z } from 'zod'
import { deleteDebt, updateDebt } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

type Context = { params: Promise<{ id: string }> }

const UpdateSchema = z.object({
  name: z.string().min(1, { message: 'Podaj nazwę zobowiązania' }).max(255).trim(),
  lander: z.string().min(1, { message: 'Podaj nazwę wierzyciela' }).max(255).trim(),
  amount: z.string().min(1, { message: 'Podaj kwotę zobowiązania' }).trim(),
  currency: z.enum(['PLN', 'USD', 'EUR']),
  interest_rate_pct: z.string().min(1).trim(),
  monthly_payment: z.string().min(1, { message: 'Podaj ratę miesięczną' }).trim(),
  end_date: z.string().min(1, { message: 'Podaj datę końca zobowiązania' }).trim(),
})

export async function PUT(req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const validated = UpdateSchema.safeParse(body)
  if (!validated.success) {
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })
  }

  const result = await updateDebt(userId, id, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ success: true })
}

export async function DELETE(_req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const ok = await deleteDebt(userId, id)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć zobowiązania' }, { status: 400 })
  return NextResponse.json({ success: true })
}
