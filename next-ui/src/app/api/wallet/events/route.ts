import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { fetchEventsPage } from '@/lib/api/brokerageEvents'
import { batchUpdateBrokerageEvents } from '@/lib/api/wallet'

export async function GET(req: NextRequest) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const sp = req.nextUrl.searchParams

  const result = await fetchEventsPage({
    userId,
    page: Number(sp.get('page') ?? 1),
    size: Number(sp.get('size') ?? 40),
    view_ccy: sp.get('view_ccy') ?? 'PLN',
    brokerage_account_id: sp.getAll('account_id'),
    kind: sp.getAll('kind'),
    currency: sp.getAll('currency'),
    date_from: sp.get('date_from') ?? undefined,
    date_to: sp.get('date_to') ?? undefined,
    q: sp.get('q') ?? undefined,
  })

  return NextResponse.json(result)
}

export async function PATCH(req: NextRequest) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({ items: [] })) as {
    items?: Array<{ id: string; kind?: string; quantity?: string; price?: string }>
  }

  const items = body.items ?? []
  if (!items.length) return NextResponse.json({ error: 'Brak zmian' }, { status: 400 })

  const result = await batchUpdateBrokerageEvents(userId, items)
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ ok: true })
}
