import { Decimal } from 'decimal.js'
import { describe, expect, it } from 'vitest'

import { convertDecimalCurrency, dec, formatWholeCurrency } from '@/lib/money'
import type { Currency } from '@/lib/types/wallet'
import { nextUiUnitStory } from '../allure'

describe('money utilities', () => {
  it('turns invalid and empty values into zero decimals', async () => {
    await nextUiUnitStory('Money utilities handle invalid and empty values', {
      severity: 'blocker',
      tags: ['money', 'financial-data'],
    })

    expect(dec(null).toString()).toBe('0')
    expect(dec(undefined).toString()).toBe('0')
    expect(dec('not-a-number').toString()).toBe('0')
  })

  it('converts decimals when a deterministic FX rate is available', async () => {
    await nextUiUnitStory('Money utilities convert deterministic FX values', {
      severity: 'blocker',
      tags: ['money', 'financial-data'],
    })

    const converted = convertDecimalCurrency(
      new Decimal(100),
      'USD',
      'PLN' as Currency,
      {
        'USD/PLN': 4,
        'EUR/PLN': 4.3,
        'PLN/USD': 0.25,
        'PLN/EUR': 0.2326,
        'USD/EUR': 0.9302,
        'EUR/USD': 1.075,
      },
    )

    expect(converted.toString()).toBe('400')
  })

  it('formats whole currency values with non-breaking thousands separators', async () => {
    await nextUiUnitStory('Money utilities format whole currency values', {
      severity: 'blocker',
      tags: ['money', 'financial-data'],
    })

    expect(formatWholeCurrency(new Decimal(1234567), 'PLN' as Currency)).toBe('1\u00a0234\u00a0567 PLN')
  })
})
