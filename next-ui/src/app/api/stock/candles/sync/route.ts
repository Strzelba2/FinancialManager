import { NextRequest, NextResponse } from 'next/server'
import { syncDailyCandles } from '@/lib/api/stock'
import type { SyncCandlesPayload } from '@/lib/api/stock'

type Body = SyncCandlesPayload & { symbol?: string }

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({})) as Body

  if (!body.symbol?.trim()) {
    return NextResponse.json({ error: 'symbol jest wymagany' }, { status: 400 })
  }

  const result = await syncDailyCandles(body.symbol.trim().toUpperCase(), {
    date_from: body.date_from ?? null,
    date_to: body.date_to ?? null,
    return_all: body.return_all ?? true,
    overlap_days: body.overlap_days ?? 7,
    include_items: true,
  })

  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status })
  }

  return NextResponse.json(result.data)
}
