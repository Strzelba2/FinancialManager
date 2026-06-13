import { NextResponse } from 'next/server'
import { z } from 'zod'
import { createInstrument, getInstruments } from '@/lib/api/stock'

const InstrumentSchema = z.object({
  market_mic: z.string().trim().regex(/^[A-Za-z0-9]{4}$/, 'MIC musi mieć 4 znaki'),
  symbol: z.string().trim().min(1, 'Podaj symbol').max(12, 'Symbol może mieć maksymalnie 12 znaków'),
  shortname: z.string().trim().min(1, 'Podaj skrót').max(40, 'Skrót może mieć maksymalnie 40 znaków'),
  name: z.string().trim().nullish(),
  type: z.string().trim().min(1).default('ETF'),
  status: z.string().trim().min(1).default('ACTIVE'),
  currency: z.enum(['PLN', 'USD', 'EUR', 'GBP', 'CHF']),
  isin: z.string().trim().nullish(),
  historical_source: z.string().trim().nullish(),
  quote_source: z.string().trim().url('Podaj pełny URL źródła notowań').nullish(),
})

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const mic = searchParams.get('mic') ?? ''

  if (!mic) {
    return NextResponse.json({ error: 'Brak parametru mic' }, { status: 400 })
  }

  const result = await getInstruments(mic)
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

  const validated = InstrumentSchema.safeParse(body)
  if (!validated.success) {
    return NextResponse.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' }, { status: 422 })
  }

  const data = validated.data
  const result = await createInstrument({
    ...data,
    market_mic: data.market_mic.toUpperCase(),
    symbol: data.symbol.toUpperCase(),
    shortname: data.shortname.toUpperCase(),
    name: data.name || null,
    isin: data.isin || null,
    historical_source: data.historical_source || null,
    quote_source: data.quote_source || null,
  })
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status })
  return NextResponse.json(result.data, { status: 201 })
}
