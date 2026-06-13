import { NextResponse } from 'next/server'
import { z } from 'zod'
import { createMarket, getMarkets } from '@/lib/api/stock'

const MarketSchema = z.object({
  mic: z.string().trim().regex(/^[A-Za-z0-9]{4}$/, 'MIC musi mieć 4 znaki'),
  name: z.string().trim().min(1, 'Podaj nazwę marketu'),
  country: z.string().trim().min(1, 'Podaj kraj'),
  timezone: z.string().trim().min(1, 'Podaj strefę czasową'),
  active: z.boolean().default(true),
  currency: z.enum(['PLN', 'USD', 'EUR', 'GBP', 'CHF']),
})

export async function GET(req: Request) {
  const url = new URL(req.url)
  const onlyWithInstruments = url.searchParams.get('only_with_instruments') === 'true'
  const result = await getMarkets({ onlyWithInstruments })
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data)
}

export async function POST(req: Request) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const validated = MarketSchema.safeParse(body)
  if (!validated.success) {
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })
  }

  const payload = {
    ...validated.data,
    mic: validated.data.mic.toUpperCase(),
  }
  const result = await createMarket(payload)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status })
  return NextResponse.json(result.data, { status: 201 })
}
