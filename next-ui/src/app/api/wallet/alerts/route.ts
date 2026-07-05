import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { upsertAlert } from '@/lib/api/wallet'

function mapAlertError(message: string): string {
  if (message.includes('Instrument not found for symbol=')) {
    return 'Ten instrument nie widnieje na liście ulubionych. Dodaj go najpierw do ulubionych, a dopiero potem ustaw alert.'
  }
  return message
}

function normalizeAlertPrice(value: string | number | null | undefined, field: string): { value: string | null; error?: string } {
  const raw = value == null ? '' : String(value).trim()
  if (!raw) return { value: null }

  const normalized = raw.replace(',', '.')
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) {
    return { value: null, error: `${field} musi być liczbą, np. 10,99 albo 10.99` }
  }

  return { value: normalized }
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
  const below = normalizeAlertPrice(body.below_price, 'below_price')
  if (below.error) return NextResponse.json({ error: below.error }, { status: 400 })
  const above = normalizeAlertPrice(body.above_price, 'above_price')
  if (above.error) return NextResponse.json({ error: above.error }, { status: 400 })

  if (!below.value && !above.value) {
    return NextResponse.json({ error: 'Podaj below_price lub above_price' }, { status: 400 })
  }

  const result = await upsertAlert(userId, {
    symbol: body.symbol.trim().toUpperCase(),
    below_price: below.value,
    above_price: above.value,
    enabled: body.enabled ?? true,
    one_shot: body.one_shot ?? false,
    expires_at: body.expires_at ?? null,
  })

  if (!result.ok) return NextResponse.json({ error: mapAlertError(result.error) }, { status: 400 })
  return NextResponse.json(result.data)
}
