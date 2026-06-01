import { describe, expect, it } from 'vitest'

import { normalizeImportedTransactionRows } from '@/features/wallet/components/TransactionsDialog'
import { nextUiUnitStory } from '../allure'

describe('TransactionsDialog import ordering', () => {
  it('reverses descending date groups without reordering split same-day rows', async () => {
    await nextUiUnitStory('Wallet import preview preserves split same-day row order', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'money', 'next-ui'],
    })

    const normalized = normalizeImportedTransactionRows([
      {
        date: '2026-05-02T00:00:00.000Z',
        amount: '10000.00',
        amount_after: '10955.56',
        description: 'newer principal',
      },
      {
        date: '2026-05-02T00:00:00.000Z',
        amount: '1741.26',
        amount_after: '12696.82',
        description: 'newer interest',
        capital_gain_kind: 'DEPOSIT_INTEREST',
      },
      {
        date: '2026-05-01T00:00:00.000Z',
        amount: '500.00',
        amount_after: '500.00',
        description: 'older principal',
      },
      {
        date: '2026-05-01T00:00:00.000Z',
        amount: '10.00',
        amount_after: '510.00',
        description: 'older interest',
        capital_gain_kind: 'DEPOSIT_INTEREST',
      },
    ])

    expect(normalized.map((row) => row.description)).toEqual([
      'older principal',
      'older interest',
      'newer principal',
      'newer interest',
    ])
  })

  it('orders same-day rows by their balance chain before import', async () => {
    await nextUiUnitStory('Wallet import preview orders same-day rows by running balance', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'money', 'next-ui'],
    })

    const normalized = normalizeImportedTransactionRows([
      {
        date: '2026-05-03T00:00:00.000Z',
        amount: '10.00',
        amount_after: '20.00',
        description: 'later',
      },
      {
        date: '2026-05-02T00:00:00.000Z',
        amount: '-110.00',
        amount_after: '10.00',
        description: 'same-day withdrawal',
      },
      {
        date: '2026-05-02T00:00:00.000Z',
        amount: '100.00',
        amount_after: '100.00',
        description: 'same-day principal',
      },
      {
        date: '2026-05-02T00:00:00.000Z',
        amount: '20.00',
        amount_after: '120.00',
        description: 'same-day interest',
        capital_gain_kind: 'DEPOSIT_INTEREST',
      },
    ])

    expect(normalized.map((row) => row.description)).toEqual([
      'same-day principal',
      'same-day interest',
      'same-day withdrawal',
      'later',
    ])
  })

  it('orders credit card rows with negative balances by their balance chain', async () => {
    await nextUiUnitStory('Wallet import preview orders credit card booking-date rows by running balance', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'money', 'next-ui'],
    })

    const normalized = normalizeImportedTransactionRows([
      {
        date: '2026-05-25',
        amount: '-39.69',
        amount_after: '-780.61',
        description: 'credit card later row',
      },
      {
        date: '2026-05-25',
        amount: '-20.31',
        amount_after: '-740.92',
        description: 'credit card earlier row',
      },
    ])

    expect(normalized.map((row) => row.description)).toEqual([
      'credit card earlier row',
      'credit card later row',
    ])
  })

  it('backtracks when same-day balance values repeat', async () => {
    await nextUiUnitStory('Wallet import preview resolves repeated same-day balances by complete chain', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'money', 'next-ui'],
    })

    const normalized = normalizeImportedTransactionRows([
      {
        date: '2025-06-12',
        amount: '-2500.00',
        amount_after: '1999.41',
        description: 'latest withdrawal',
      },
      {
        date: '2025-06-12',
        amount: '-1500.00',
        amount_after: '4499.41',
        description: 'middle withdrawal',
      },
      {
        date: '2025-06-12',
        amount: '1500.00',
        amount_after: '5999.41',
        description: 'middle income',
      },
      {
        date: '2025-06-12',
        amount: '3500.00',
        amount_after: '4499.41',
        description: 'earliest income',
      },
    ])

    expect(normalized.map((row) => row.description)).toEqual([
      'earliest income',
      'middle income',
      'middle withdrawal',
      'latest withdrawal',
    ])
  })

  it('prefers bottom-to-top rows for descending imports when same-day balances loop', async () => {
    await nextUiUnitStory('Wallet import preview resolves Velo PDF same-day balance loop order', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'money', 'next-ui', 'velo-bank'],
    })

    const normalized = normalizeImportedTransactionRows([
      {
        date: '2025-11-25',
        amount: '5.00',
        amount_after: '639.79',
        description: 'newer row',
      },
      {
        date: '2025-11-23',
        amount: '-98000.00',
        amount_after: '634.79',
        description: 'return later',
      },
      {
        date: '2025-11-23',
        amount: '98000.00',
        amount_after: '98634.79',
        description: 'return earlier',
      },
      {
        date: '2025-11-23',
        amount: '-50000.00',
        amount_after: '634.79',
        description: 'second withdrawal',
      },
      {
        date: '2025-11-23',
        amount: '-50000.00',
        amount_after: '50634.79',
        description: 'first withdrawal',
      },
      {
        date: '2025-11-23',
        amount: '100000.00',
        amount_after: '100634.79',
        description: 'deposit',
      },
      {
        date: '2025-11-20',
        amount: '10.00',
        amount_after: '634.79',
        description: 'older row',
      },
    ])

    expect(normalized.map((row) => row.description)).toEqual([
      'older row',
      'deposit',
      'first withdrawal',
      'second withdrawal',
      'return earlier',
      'return later',
      'newer row',
    ])
  })
})
