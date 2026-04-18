import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { fetchHoldings } from '@/lib/api/holdings'

export async function GET(req: NextRequest) {
  const userId = await resolveWalletUserId()
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const url = new URL(req.url)
  const q = url.searchParams.get('q') ?? undefined
  const accountIds = url.searchParams.getAll('account_id')
  const groupMode = (url.searchParams.get('group_mode') ?? 'SYMBOL') as 'SYMBOL' | 'ACCOUNT'
  const viewCcy = url.searchParams.get('view_ccy') ?? 'PLN'

  const result = await fetchHoldings({
    userId,
    q: q || undefined,
    brokerage_account_id: accountIds.length ? accountIds : undefined,
    group_mode: groupMode,
    view_ccy: viewCcy,
  })

  return NextResponse.json(result)
}
