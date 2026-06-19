import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { listFavoriteItemsWithAlerts, deleteFavoriteList } from '@/lib/api/wallet'
import { getQuotesBulk } from '@/lib/api/stock'
import type { FavoriteItemWithAlert } from '@/lib/api/wallet'

/**
 * Resolve the display name for a favorite row.
 *
 * Many favorites were stored with `name` equal to the symbol (add-time fallback),
 * so we prefer the live instrument name from the quote feed and only fall back to
 * the stored name, then the symbol.
 */
export function resolveFavoriteName(
  symbol: string,
  storedName: string | null | undefined,
  quoteName: string | null | undefined,
): string {
  const sym = symbol.toUpperCase()
  const qn = (quoteName ?? '').trim()
  if (qn && qn.toUpperCase() !== sym) return qn
  const sn = (storedName ?? '').trim()
  if (sn && sn.toUpperCase() !== sym) return sn
  return '—'
}

export type FavoriteItemRow = {
  symbol: string
  name: string
  mic: string
  price: string | null
  changePct: number | null
  changePctFmt: string | null
  volume: number | null
  lastTradeDateFmt: string | null
  lastTradeTimeFmt: string | null
  alert: {
    id?: string
    below_price: string | null
    above_price: string | null
    enabled: boolean
    one_shot: boolean
    expires_at: string | null
  } | null
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id: listId } = await params
  const items: FavoriteItemWithAlert[] = await listFavoriteItemsWithAlerts(userId, listId)

  // Group by MIC, fetch bulk quotes per MIC
  const micGroups = new Map<string, string[]>()
  for (const it of items) {
    const sym = (it.symbol ?? '').toUpperCase().trim()
    const mic = (it.mic ?? 'XWAR').trim()
    if (!sym) continue
    const group = micGroups.get(mic) ?? []
    group.push(sym)
    micGroups.set(mic, group)
  }

  // Fetch quotes for each MIC in parallel
  const bulkMaps = await Promise.all(
    [...micGroups.keys()].map(async (mic) => ({ mic, data: await getQuotesBulk(mic) }))
  )
  const quoteMap = new Map<string, ReturnType<typeof getQuotesBulk> extends Promise<Record<string, infer V>> ? V : never>()
  for (const { data } of bulkMaps) {
    for (const [sym, q] of Object.entries(data)) {
      quoteMap.set(sym.toUpperCase(), q)
    }
  }

  const rows: FavoriteItemRow[] = items.map((it) => {
    const sym = (it.symbol ?? '').toUpperCase().trim()
    const q = quoteMap.get(sym)
    const al = it.alert ?? null

    return {
      symbol: sym || '—',
      name: resolveFavoriteName(sym, it.name, q?.name),
      mic: (it.mic ?? 'XWAR').trim(),
      price: q?.last_price_fmt ?? (q?.last_price != null ? String(q.last_price) : null),
      changePct: q?.change_pct != null ? Number(q.change_pct) : null,
      changePctFmt: q?.change_pct_fmt ?? null,
      volume: q?.volume ?? null,
      lastTradeDateFmt: q?.last_trade_date_fmt ?? null,
      lastTradeTimeFmt: q?.last_trade_time_fmt ?? null,
      alert: al ? {
        id: al.id,
        below_price: al.below_price ?? null,
        above_price: al.above_price ?? null,
        enabled: al.enabled ?? true,
        one_shot: al.one_shot ?? false,
        expires_at: al.expires_at ?? null,
      } : null,
    }
  })

  return NextResponse.json(rows)
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id: listId } = await params
  const ok = await deleteFavoriteList(userId, listId)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć listy' }, { status: 400 })
  return NextResponse.json({ ok: true })
}
