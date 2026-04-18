import { logger } from '@/lib/logger'

export type FxRates = {
  'USD/PLN': number
  'EUR/PLN': number
  'PLN/USD': number
  'PLN/EUR': number
  'USD/EUR': number
  'EUR/USD': number
}

const NBP_URL = 'https://api.nbp.pl/api/exchangerates/tables/A?format=json'

export async function getFxRates(): Promise<FxRates | null> {
  try {
    const res = await fetch(NBP_URL, {
      headers: { Accept: 'application/json' },
      next: { revalidate: 3600 }, 
    })

    if (!res.ok) {
      logger.warn({ status: res.status }, 'NBP API error')
      return null
    }

    const tables = await res.json() as { rates: { code: string; mid: number }[] }[]
    const rates: Record<string, number> = {}
    for (const row of tables[0]?.rates ?? []) {
      rates[row.code] = row.mid
    }

    const usdPln = rates['USD'] ?? 0
    const eurPln = rates['EUR'] ?? 0
    if (!usdPln || !eurPln) return null

    const usdEur = usdPln / eurPln

    return {
      'USD/PLN': usdPln,
      'EUR/PLN': eurPln,
      'PLN/USD': Math.round((1 / usdPln) * 1e4) / 1e4,
      'PLN/EUR': Math.round((1 / eurPln) * 1e4) / 1e4,
      'USD/EUR': Math.round(usdEur * 1e4) / 1e4,
      'EUR/USD': Math.round((1 / usdEur) * 1e4) / 1e4,
    }
  } catch (err) {
    logger.error({ err }, 'NBP API request failed')
    return null
  }
}

export function convertCurrency(
  amount: number,
  from: string,
  to: string,
  rates: FxRates,
): number {
  if (from === to) return amount
  const key = `${from}/${to}` as keyof FxRates
  const rate = rates[key]
  if (rate) return amount * rate
  // Try inverse
  const invKey = `${to}/${from}` as keyof FxRates
  const invRate = rates[invKey]
  if (invRate) return amount / invRate
  return amount
}
