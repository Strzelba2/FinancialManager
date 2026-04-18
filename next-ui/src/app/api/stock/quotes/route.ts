import { NextRequest, NextResponse } from 'next/server'
import { getQuotesBulkResult, processQuotes } from '@/lib/api/stock'

export async function GET(req: NextRequest) {
  const mic = req.nextUrl.searchParams.get('mic') ?? ''
  if (!mic) return NextResponse.json({ error: 'Brak parametru mic' }, { status: 400 })

  const result = await getQuotesBulkResult(mic)
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status })
  }

  const rows = processQuotes(result.data)
  if (rows.length === 0) {
    return NextResponse.json({ error: 'Brak ostatnich notowań dla wybranego rynku' }, { status: 404 })
  }

  return NextResponse.json(rows)
}
