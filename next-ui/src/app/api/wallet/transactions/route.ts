import { NextResponse } from 'next/server'
import { z } from 'zod'
import { createTransactions, listTransactions, batchUpdateTransactions } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const TransactionRowSchema = z.object({
  date: z.string().min(1, { message: 'Podaj datę transakcji' }).trim(),
  amount: z.string().min(1, { message: 'Podaj kwotę transakcji' }).trim(),
  description: z.string().min(1, { message: 'Podaj opis transakcji' }).max(255).trim(),
  amount_after: z.string().min(1, { message: 'Podaj saldo po transakcji' }).trim(),
  capital_gain_kind: z.enum([
    'DEPOSIT_INTEREST',
    'BROKER_REALIZED_PNL',
    'BROKER_DIVIDEND',
    'METAL_REALIZED_PNL',
    'REAL_ESTATE_REALIZED_PNL',
  ]).nullable().optional(),
})

const CreateSchema = z.object({
  account_id: z.string().uuid(),
  transactions: z.array(TransactionRowSchema).min(1, { message: 'Dodaj co najmniej jedną transakcję' }),
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

  const validated = CreateSchema.safeParse(body)
  if (!validated.success) {
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })
  }

  const result = await createTransactions(userId, validated.data)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status })

  return NextResponse.json({ success: true, summary: result.data })
}

export async function GET(req: Request) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const url = new URL(req.url)
  const p = url.searchParams

  const params = {
    page: p.get('page') ? Number(p.get('page')) : 1,
    size: p.get('size') ? Number(p.get('size')) : 40,
    account_id: p.getAll('account_id').filter(Boolean),
    category: p.getAll('category').filter(Boolean),
    status: p.getAll('status').filter(Boolean),
    date_from: p.get('date_from') ?? undefined,
    date_to: p.get('date_to') ?? undefined,
    q: p.get('q') ?? undefined,
  }

  const result = await listTransactions(userId, params)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status })

  return NextResponse.json(result.data)
}

// ── PATCH: batch-update transactions ─────────────────────────────────────────

const PatchItemSchema = z.object({
  id: z.string().uuid(),
  description: z.string().max(255).trim().optional(),
  category: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
}).strict()

const PatchSchema = z.object({
  items: z.array(PatchItemSchema).min(1),
})

export async function PATCH(req: Request) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const validated = PatchSchema.safeParse(body)
  if (!validated.success) {
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })
  }

  const result = await batchUpdateTransactions(userId, validated.data.items)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status })

  return NextResponse.json(result.data)
}
