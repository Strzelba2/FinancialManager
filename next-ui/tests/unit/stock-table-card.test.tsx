import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ObservedStocksCard } from '@/features/wallet/components/StockTableCard'
import type { FavoriteItem } from '@/lib/types/wallet'
import { nextUiUnitStory } from '../allure'

describe('ObservedStocksCard', () => {
  it('formats observed quote change percentages without multiplying them by one hundred', async () => {
    await nextUiUnitStory('Wallet dashboard observed stocks format quote change percentage points', {
      severity: 'critical',
      tags: ['wallet', 'favorites', 'quotes', 'money', 'next-ui'],
    })

    const items: FavoriteItem[] = [
      {
        sym: 'PKN',
        pl_pct: '3.55',
        pl_abs: '70.40',
        currency: 'PLN',
      },
    ]

    render(<ObservedStocksCard items={items} viewCurrency="PLN" href="/user/favorites" />)

    expect(screen.getByRole('columnheader', { name: 'Cena (PLN)' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'P/L (PLN)' })).not.toBeInTheDocument()
    expect(screen.getByText('+3,55%')).toBeInTheDocument()
    expect(screen.queryByText('+355,00%')).not.toBeInTheDocument()
    expect(screen.getByText('70.40 PLN')).toBeInTheDocument()
    expect(screen.queryByText('+70.40 PLN')).not.toBeInTheDocument()
  })
})
