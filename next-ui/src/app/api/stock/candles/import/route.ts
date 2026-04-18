import { NextRequest, NextResponse } from 'next/server'
import { importDailyCandlesCsv } from '@/lib/api/stock'
import type { ImportCandlesPayload } from '@/lib/api/stock'

type Body = ImportCandlesPayload & { symbol?: string }

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({})) as Body

  if (!body.symbol?.trim()) {
    return NextResponse.json({ error: 'symbol jest wymagany' }, { status: 400 })
  }

  if (!body.content_b64?.trim()) {
    return NextResponse.json({ error: 'content_b64 jest wymagany' }, { status: 400 })
  }

  const result = await importDailyCandlesCsv(body.symbol.trim().toUpperCase(), {
    filename: body.filename ?? null,
    content_b64: body.content_b64,
    date_from: body.date_from ?? null,
    date_to: body.date_to ?? null,
    return_all: body.return_all ?? true,
    include_items: true,
  })

  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status })
  }

  return NextResponse.json(result.data)
}
