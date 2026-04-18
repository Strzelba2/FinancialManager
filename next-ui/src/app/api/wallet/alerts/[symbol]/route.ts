import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { deleteAlert, getAlertBySymbol } from '@/lib/api/wallet'

function mapAlertError(message: string): string {
  if (message.includes('Instrument not found for symbol=')) {
    return 'Ten instrument nie widnieje na liście ulubionych. Dodaj go najpierw do ulubionych, a dopiero potem ustaw alert.'
  }
  return message
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { symbol } = await params
  const result = await getAlertBySymbol(userId, symbol)
  if (!result.ok) return NextResponse.json({ error: mapAlertError(result.error) }, { status: 400 })
  return NextResponse.json(result.data)
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { symbol } = await params
  const ok = await deleteAlert(userId, symbol)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć alertu' }, { status: 400 })
  return NextResponse.json({ ok: true })
}
