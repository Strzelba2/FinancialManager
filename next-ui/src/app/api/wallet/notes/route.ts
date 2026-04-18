import { NextResponse } from 'next/server'
import { z } from 'zod'
import { getMyNote, upsertMyNote } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

const UpsertSchema = z.object({
  text: z.string(),
})

export async function GET() {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const result = await getMyNote(userId)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })

  return NextResponse.json(result.data)
}

export async function PUT(req: Request) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const validated = UpsertSchema.safeParse(body)
  if (!validated.success) {
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })
  }

  const result = await upsertMyNote(userId, validated.data.text)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })

  return NextResponse.json(result.data)
}
