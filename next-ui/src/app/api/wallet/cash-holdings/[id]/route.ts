import { NextResponse } from 'next/server'
import { z } from 'zod'
import { deleteCashHolding, updateCashHolding } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

type Context = { params: Promise<{ id: string }> }

const UpdateSchema = z.object({
  name: z.string().trim().min(1, { message: 'Podaj nazwę pozycji' }).max(255),
  amount: z.string().trim().regex(/^\d+(\.\d+)?$/, { message: 'Podaj kwotę większą lub równą 0' }),
  currency: z.enum(['PLN', 'USD', 'EUR', 'GBP', 'CHF']),
  note: z.string().trim().max(255),
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

  const result = await updateCashHolding(userId, id, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ success: true })
}

export async function DELETE(_req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const ok = await deleteCashHolding(userId, id)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć pozycji gotówki' }, { status: 400 })
  return NextResponse.json({ success: true })
}
