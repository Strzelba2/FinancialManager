import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MarketDataNotice } from '@/features/wallet/components/MarketDataNotice'
import { nextUiUnitStory } from '../allure'

describe('MarketDataNotice', () => {
  it('warns dashboard users that unavailable quotes can understate wallet value and real asset charts', async () => {
    await nextUiUnitStory('Wallet dashboard market data notice explains quote outage valuation risk', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'quotes', 'financial-data', 'next-ui'],
    })

    render(<MarketDataNotice affectedPositions={3} scope="dashboard" />)

    expect(screen.getByRole('status')).toHaveTextContent('Dane rynkowe są tymczasowo niedostępne')
    expect(screen.getByRole('status')).toHaveTextContent(
      'Wartość netto, inwestycje, alokacja oraz wykres aktywów nominalnie vs realnie mogą być niepełne lub zaniżone.',
    )
    expect(screen.getAllByText('3 pozycji nie ma aktualnego notowania.')).toHaveLength(2)

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Dane rynkowe niedostępne')).toBeInTheDocument()
    expect(within(dialog).getByText(/wartość majątku, inwestycje/)).toBeInTheDocument()
  })

  it('allows the user to dismiss the quote outage banner without hiding the underlying page', async () => {
    await nextUiUnitStory('Wallet market data notice can be dismissed by the user', {
      severity: 'normal',
      tags: ['wallet', 'brokerage', 'quotes', 'next-ui'],
    })

    render(<MarketDataNotice scope="dashboard" defaultOpen={false} />)

    fireEvent.click(screen.getByRole('button', { name: 'Ukryj komunikat o danych rynkowych' }))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
