import { NextResponse } from 'next/server'
import { getInstruments } from '@/lib/api/stock'

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
