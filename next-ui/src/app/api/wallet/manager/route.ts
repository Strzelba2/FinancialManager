import { NextRequest, NextResponse } from 'next/server'
import { resolveWalletUserId } from '@/lib/api/session'
import { getFxRates } from '@/lib/api/nbp'
import { logger } from '@/lib/logger'

const WALLET_API = process.env.WALLET_API_URL ?? ''

async function walletPost<T>(path: string, userId: string, body: unknown): Promise<{ ok: true; data: T } | { ok: false; error: string }> {
  try {
    const res = await fetch(`${WALLET_API}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    if (!res.ok) {
      const text = await res.text()
      logger.warn({ status: res.status, path, body: text }, 'wallet manager API error')
      return { ok: false, error: `Błąd serwera (${res.status})` }
    }
    const data = await res.json() as T
    return { ok: true, data }
  } catch (err) {
    logger.error({ err, path }, 'wallet manager API request failed')
    return { ok: false, error: 'Nie można połączyć się z serwisem portfela' }
  }
}

async function walletPatch<T>(path: string, userId: string, body: unknown): Promise<{ ok: true; data: T } | { ok: false; error: string }> {
  try {
    const res = await fetch(`${WALLET_API}${path}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    if (!res.ok) {
      const text = await res.text()
      logger.warn({ status: res.status, path, body: text }, 'wallet manager PATCH error')
      return { ok: false, error: `Błąd serwera (${res.status})` }
    }
    const data = await res.json() as T
    return { ok: true, data }
  } catch (err) {
    logger.error({ err, path }, 'wallet manager PATCH request failed')
    return { ok: false, error: 'Nie można połączyć się z serwisem portfela' }
  }
}

// POST /api/wallet/manager/snapshot — mirrors create_monthly_snapshot()
export async function POST(req: NextRequest) {
  const { action, walletId, name } = await req.json().catch(() => ({})) as {
    action?: string
    walletId?: string
    name?: string
  }

  const userId = await resolveWalletUserId()
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  if (action === 'rename' && walletId && name) {
    const result = await walletPatch<{ id: string; name: string }>(
      `/wallet/${walletId}/name`,
      userId,
      { name },
    )
    if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
    return NextResponse.json(result.data)
  }

  const rates = await getFxRates()
  const currencyRate: Record<string, string> = {}
  if (rates) {
    for (const [k, v] of Object.entries(rates)) {
      currencyRate[k] = String(v)
    }
  }

  const now = new Date()
  const monthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`

  const result = await walletPost<{ month_key?: string }>(
    '/wallet/snapshots/monthly',
    userId,
    { month_key: monthKey, currency_rate: currencyRate },
  )

  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 })
  return NextResponse.json({ ok: true, month_key: result.data.month_key ?? monthKey })
}
