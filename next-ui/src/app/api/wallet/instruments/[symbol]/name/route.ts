import { NextResponse } from 'next/server'
import { z } from 'zod'

import { resolveWalletUserId } from '@/lib/api/session'
import { synchronizeInstrumentName } from '@/lib/api/wallet'


const ParamsSchema = z.object({
  symbol: z.string().trim().min(1).max(12),
})

const BodySchema = z.object({
  mic: z.string().trim().regex(/^[A-Za-z0-9]{4}$/, 'MIC musi mieć 4 znaki'),
  name: z.string().trim().min(1, 'Nazwa nie może być pusta').max(40, 'Nazwa może mieć maksymalnie 40 znaków'),
})


export async function PUT(
  req: Request,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const parsedParams = ParamsSchema.safeParse(await params)
  if (!parsedParams.success) {
    return NextResponse.json({ error: 'Nieprawidłowy symbol instrumentu' }, { status: 422 })
  }

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const parsedBody = BodySchema.safeParse(body)
  if (!parsedBody.success) {
    return NextResponse.json(
      { error: parsedBody.error.issues[0]?.message ?? 'Nieprawidłowe dane' },
      { status: 422 },
    )
  }

  const result = await synchronizeInstrumentName(
    userId,
    parsedParams.data.symbol.toUpperCase(),
    {
      mic: parsedBody.data.mic.toUpperCase(),
      name: parsedBody.data.name,
    },
  )
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status })
  return NextResponse.json(result.data)
}
