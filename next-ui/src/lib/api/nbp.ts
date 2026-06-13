import { logger } from '@/lib/logger'

export type FxRates = {
  'USD/PLN': number
  'EUR/PLN': number
  'PLN/USD': number
  'PLN/EUR': number
  'USD/EUR': number
  'EUR/USD': number
  'CHF/PLN': number
  'CHF/USD': number
  'CHF/EUR': number
  'GBP/PLN': number
  'GBP/USD': number
  'GBP/EUR': number
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

    // CHF/GBP are secondary: their absence must not fail the whole table.
    // A 0 rate is treated as falsy by the conversion helpers, which then
    // return the amount unconverted (same as the pre-CHF/GBP behaviour).
    const chfPln = rates['CHF'] ?? 0
    const gbpPln = rates['GBP'] ?? 0

    return {
      'USD/PLN': usdPln,
      'EUR/PLN': eurPln,
      'PLN/USD': Math.round((1 / usdPln) * 1e4) / 1e4,
      'PLN/EUR': Math.round((1 / eurPln) * 1e4) / 1e4,
      'USD/EUR': Math.round(usdEur * 1e4) / 1e4,
      'EUR/USD': Math.round((1 / usdEur) * 1e4) / 1e4,
      'CHF/PLN': chfPln,
      'CHF/USD': chfPln ? Math.round((chfPln / usdPln) * 1e4) / 1e4 : 0,
      'CHF/EUR': chfPln ? Math.round((chfPln / eurPln) * 1e4) / 1e4 : 0,
      'GBP/PLN': gbpPln,
      'GBP/USD': gbpPln ? Math.round((gbpPln / usdPln) * 1e4) / 1e4 : 0,
      'GBP/EUR': gbpPln ? Math.round((gbpPln / eurPln) * 1e4) / 1e4 : 0,
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
