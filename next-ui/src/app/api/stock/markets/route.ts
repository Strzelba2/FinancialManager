import { NextResponse } from 'next/server'
import { getMarkets } from '@/lib/api/stock'

export async function GET() {
  const result = await getMarkets()
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json(result.data)
}
