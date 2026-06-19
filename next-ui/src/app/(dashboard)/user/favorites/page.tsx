import { headers } from 'next/headers'
import { syncUser, listFavoriteLists, listFavoriteItemsWithAlerts } from '@/lib/api/wallet'
import { saveWalletUserId } from '@/lib/api/session'
import { getQuotesBulk } from '@/lib/api/stock'
import { FavoritesPage } from '@/features/wallet/components/FavoritesPage'
import { resolveFavoriteName, type FavoriteItemRow } from '@/app/api/wallet/favorites/[id]/route'

export default async function FavoritesRoute() {
  const headerStore = await headers()
  const username = headerStore.get('x-user') ?? ''
  const first_name = headerStore.get('x-first-name') ?? ''
  const email = headerStore.get('x-email') ?? ''
  const existingUserId = headerStore.get('x-user-id') ?? ''

  const data = await syncUser({ username, first_name, email })

  if (data && !existingUserId) {
    await saveWalletUserId(data.user_id)
  }

  if (!data) {
    return (
      <div className="p-8 text-white">
        <p className="text-red-400">Nie udało się pobrać danych portfela. Spróbuj ponownie.</p>
      </div>
    )
  }

  const lists = await listFavoriteLists(data.user_id)
  const firstList = lists[0] ?? null

  // Load items for the first list (if any)
  let initialItems: FavoriteItemRow[] = []
  if (firstList) {
    const items = await listFavoriteItemsWithAlerts(data.user_id, firstList.id)

    // Group by MIC for bulk quote fetch
    const micGroups = new Map<string, string[]>()
    for (const it of items) {
      const sym = (it.symbol ?? '').toUpperCase().trim()
      const mic = (it.mic ?? 'XWAR').trim()
      if (!sym) continue
      const group = micGroups.get(mic) ?? []
      group.push(sym)
      micGroups.set(mic, group)
    }

    const bulkResults = await Promise.all(
      [...micGroups.keys()].map(async (mic) => ({ mic, data: await getQuotesBulk(mic) }))
    )
    const quoteMap = new Map<string, { last_price_fmt?: string | null; last_price?: string | number | null; change_pct?: string | number | null; change_pct_fmt?: string | null; volume?: number | null; last_trade_date_fmt?: string | null; last_trade_time_fmt?: string | null; name?: string | null }>()
    for (const { data: bd } of bulkResults) {
      for (const [sym, q] of Object.entries(bd)) {
        quoteMap.set(sym.toUpperCase(), q)
      }
    }

    initialItems = items.map((it) => {
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
      } satisfies FavoriteItemRow
    })
  }

  return (
    <FavoritesPage
      initialLists={lists}
      initialListId={firstList?.id ?? null}
      initialItems={initialItems}
    />
  )
}
