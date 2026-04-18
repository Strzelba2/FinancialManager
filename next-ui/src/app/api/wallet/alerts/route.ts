import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { upsertAlert } from '@/lib/api/wallet'

function mapAlertError(message: string): string {
  if (message.includes('Instrument not found for symbol=')) {
    return 'Ten instrument nie widnieje na liście ulubionych. Dodaj go najpierw do ulubionych, a dopiero potem ustaw alert.'
  }
  return message
}

export async function POST(req: NextRequest) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({})) as {
    symbol?: string
    below_price?: string | null
    above_price?: string | null
    enabled?: boolean
    one_shot?: boolean
    expires_at?: string | null
  }

  if (!body.symbol?.trim()) {
    return NextResponse.json({ error: 'symbol jest wymagany' }, { status: 400 })
  }
  if (!body.below_price && !body.above_price) {
    return NextResponse.json({ error: 'Podaj below_price lub above_price' }, { status: 400 })
  }

  const result = await upsertAlert(userId, {
    symbol: body.symbol.trim().toUpperCase(),
    below_price: body.below_price ?? null,
    above_price: body.above_price ?? null,
    enabled: body.enabled ?? true,
    one_shot: body.one_shot ?? false,
    expires_at: body.expires_at ?? null,
  })

  if (!result.ok) return NextResponse.json({ error: mapAlertError(result.error) }, { status: 400 })
  return NextResponse.json(result.data)
}
