import { Decimal } from 'decimal.js'
import { convertCurrency, type FxRates } from '@/lib/api/nbp'
import type { Currency } from '@/lib/types/wallet'

export type NullableFxRates = FxRates | null

export function dec(value: string | number | null | undefined): Decimal {
  try {
    return new Decimal(value ?? '0')
  } catch {
    return new Decimal(0)
  }
}

export function convertDecimalCurrency(
  amount: Decimal,
  from: string,
  to: Currency,
  rates: NullableFxRates,
): Decimal {
  if (!rates || from === to) return amount
  return new Decimal(convertCurrency(amount.toNumber(), from, to, rates))
}

export function formatWholeCurrency(value: Decimal, currency: Currency): string {
  return `${value.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0')} ${currency}`
}
