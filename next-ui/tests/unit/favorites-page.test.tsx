import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'

import { FavoritesPage } from '@/features/wallet/components/FavoritesPage'
import type { FavoriteItemRow } from '@/app/api/wallet/favorites/[id]/route'
import type { FavoriteList } from '@/lib/api/wallet'
import { nextUiUnitStory } from '../allure'

const routerPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('@/features/wallet/components/PriceAlertModal', () => ({
  PriceAlertModal: ({
    symbol,
    name,
    onClose,
    onSaved,
  }: {
    symbol: string
    name: string
    onClose: () => void
    onSaved: () => void
  }) => (
    <div role="dialog" aria-label={`Alert ${symbol}`}>
      <p>{name}</p>
      <button onClick={onSaved}>Zapisz alert</button>
      <button onClick={onClose}>Zamknij alert</button>
    </div>
  ),
}))

const favoriteLists: FavoriteList[] = [
  { id: 'list-1', name: 'GPW', description: null },
  { id: 'list-2', name: 'USA', description: null },
]

function item(overrides: Partial<FavoriteItemRow>): FavoriteItemRow {
  return {
    symbol: 'PKO',
    name: 'PKO Bank Polski',
    mic: 'XWAR',
    price: '64,20',
    changePct: 1.25,
    changePctFmt: '+1,25%',
    volume: 1200,
    lastTradeDateFmt: '2026-06-26',
    lastTradeTimeFmt: '17:00',
    alert: null,
    ...overrides,
  }
}

function renderFavorites(initialItems: FavoriteItemRow[] = [
  item({ symbol: 'CCC', name: 'CCC SA', changePct: -2.5, changePctFmt: '-2,50%' }),
  item({ symbol: 'PKO', name: 'PKO Bank Polski', changePct: 1.25, changePctFmt: '+1,25%' }),
]) {
  return render(
    <FavoritesPage
      initialLists={favoriteLists}
      initialListId="list-1"
      initialItems={initialItems}
    />,
  )
}

describe('FavoritesPage', () => {
  beforeEach(() => {
    routerPush.mockClear()
    server.resetHandlers()
  })

  it('filters favorites by instrument name and sorts percentage changes descending', async () => {
    await nextUiUnitStory('Wallet favorites page filters and sorts observed instruments', {
      severity: 'normal',
      tags: ['wallet', 'favorites', 'quotes', 'next-ui'],
    })

    renderFavorites()

    fireEvent.change(screen.getByPlaceholderText(/Szukaj symbol/i), {
      target: { value: 'bank' },
    })

    expect(screen.getByText('PKO')).toBeInTheDocument()
    expect(screen.queryByText('CCC')).not.toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText(/Szukaj symbol/i), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Zmiana %/i }))

    const symbols = screen.getAllByText(/^(PKO|CCC)$/).map((el) => el.textContent)
    expect(symbols).toEqual(['PKO', 'CCC'])
  })

  it('loads another favorite list through the local API and shows connection errors', async () => {
    await nextUiUnitStory('Wallet favorites page loads selected list items through the Next API route', {
      severity: 'normal',
      tags: ['wallet', 'favorites', 'api-contract', 'error-state', 'next-ui'],
    })
    const requests: string[] = []
    server.use(
      http.get('*/api/wallet/favorites/list-2', ({ request }) => {
        requests.push(request.url)
        return HttpResponse.json([item({ symbol: 'AAPL', name: 'Apple Inc.', mic: 'XNAS' })])
      }),
      http.get('*/api/wallet/favorites/list-1', () => HttpResponse.error()),
    )

    renderFavorites()

    fireEvent.click(screen.getByRole('button', { name: 'USA' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(await screen.findByText('AAPL')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'GPW' }))

    expect(await screen.findByText('Błąd połączenia')).toBeInTheDocument()
  })

  it('validates and creates a new favorite list without losing existing lists', async () => {
    await nextUiUnitStory('Wallet favorites page validates and creates favorite lists', {
      severity: 'normal',
      tags: ['wallet', 'favorites', 'form-validation', 'next-ui'],
    })
    server.use(
      http.post('*/api/wallet/favorites', async ({ request }) => {
        await expect(request.json()).resolves.toEqual({
          name: 'Dywidendy',
          description: 'Spolki dywidendowe',
        })
        return HttpResponse.json({ id: 'list-3', name: 'Dywidendy', description: 'Spolki dywidendowe' })
      }),
    )

    renderFavorites()

    fireEvent.click(screen.getByRole('button', { name: /Dodaj listę/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Utwórz' }))
    expect(screen.getByText('Podaj nazwę')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Nazwa/i), { target: { value: 'Dywidendy' } })
    fireEvent.change(screen.getByLabelText(/Opis/i), { target: { value: 'Spolki dywidendowe' } })
    fireEvent.click(screen.getByRole('button', { name: 'Utwórz' }))

    expect(await screen.findByRole('button', { name: 'Dywidendy' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'GPW' })).toBeInTheDocument()
  })

  it('deletes an alert from the row action menu and reloads the selected list', async () => {
    await nextUiUnitStory('Wallet favorites page deletes price alerts from row actions', {
      severity: 'critical',
      tags: ['wallet', 'favorites', 'alerts', 'api-contract', 'next-ui'],
    })
    const reloads: string[] = []
    const deletes: string[] = []
    server.use(
      http.delete('*/api/wallet/alerts/PKO', ({ request }) => {
        deletes.push(request.url)
        return HttpResponse.json({ ok: true })
      }),
      http.get('*/api/wallet/favorites/list-1', ({ request }) => {
        reloads.push(request.url)
        return HttpResponse.json([item({ symbol: 'PKO', alert: null })])
      }),
    )
    renderFavorites([
      item({
        symbol: 'PKO',
        alert: {
          id: 'alert-1',
          below_price: '60.00',
          above_price: '70.00',
          enabled: true,
          one_shot: false,
          expires_at: null,
        },
      }),
    ])

    const row = screen.getByText('PKO').closest('tr')
    expect(row).not.toBeNull()
    fireEvent.click(within(row as HTMLTableRowElement).getAllByRole('button')[0]!)
    fireEvent.click(await screen.findByRole('button', { name: /Usuń alert/i }))

    await waitFor(() => expect(deletes).toHaveLength(1))
    await waitFor(() => expect(reloads).toHaveLength(1))
  })
})
