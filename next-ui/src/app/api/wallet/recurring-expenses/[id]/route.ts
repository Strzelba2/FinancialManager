import { NextResponse } from 'next/server'
import { z } from 'zod'
import { updateRecurringExpense, deleteRecurringExpense } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

type Context = { params: Promise<{ id: string }> }

const UpdateSchema = z.object({
  name: z.string().min(1, { message: 'Podaj nazwę wydatku' }).max(255).trim(),
  category: z.string().max(255).trim().optional(),
  amount: z.string().min(1, { message: 'Podaj kwotę' }).trim(),
  currency: z.enum(['PLN', 'USD', 'EUR']),
  due_day: z.number().int().min(1).max(31),
  account: z.string().max(255).trim().optional(),
  note: z.string().max(500).trim().optional(),
})

export async function PUT(req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  let body: unknown
  try { body = await req.json() } catch {
    return NextResponse.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const validated = UpdateSchema.safeParse(body)
  if (!validated.success)
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })

  const result = await updateRecurringExpense(userId, id, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data)
}

export async function DELETE(_req: Request, { params }: Context) {
  const { id } = await params
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const ok = await deleteRecurringExpense(userId, id)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć wydatku' }, { status: 400 })
  return NextResponse.json({ success: true })
}
