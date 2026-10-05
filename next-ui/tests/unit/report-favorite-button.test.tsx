import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'

import { ReportFavoriteButton } from '@/features/reports/components/EquityReportPage'
import { nextUiUnitStory } from '../allure'
import { server } from '../msw-server'

type FavoriteItem = {
  symbol: string
  name: string
  mic: string
  alert: null
}

describe('ReportFavoriteButton', () => {
  beforeEach(() => {
    server.resetHandlers()
  })

  it('opens the favorites dialog and reflects adding and removing the report instrument', async () => {
    await nextUiUnitStory('Report favorite star manages the instrument through the favorites dialog', {
      severity: 'normal',
      tags: ['reports', 'favorites', 'api-contract', 'next-ui'],
    })

    let items: FavoriteItem[] = []
    const addedPayloads: unknown[] = []
    const deletedUrls: string[] = []

    server.use(
      http.get('*/api/wallet/favorites', ({ request }) => {
        const requestedSymbol = new URL(request.url).searchParams.get('symbol')
        if (requestedSymbol) {
          return HttpResponse.json({
            isFavorite: items.some((item) => item.symbol === requestedSymbol),
          })
        }
        return HttpResponse.json([{ id: 'list-1', name: 'GPW', description: null }])
      }),
      http.get('*/api/wallet/favorites/list-1', () => HttpResponse.json(items)),
      http.post('*/api/wallet/favorites/list-1/items', async ({ request }) => {
        addedPayloads.push(await request.json())
        items = [{ symbol: 'PKO', name: 'PKO Bank Polski', mic: 'XWAR', alert: null }]
        return HttpResponse.json({ ok: true }, { status: 201 })
      }),
      http.delete('*/api/wallet/favorites/list-1/items/PKO', ({ request }) => {
        deletedUrls.push(request.url)
        items = []
        return HttpResponse.json({ ok: true })
      }),
    )

    render(<ReportFavoriteButton symbol="PKO" name="PKO Bank Polski" mic="XWAR" />)

    const grayStar = screen.getByRole('button', { name: 'Dodaj PKO do ulubionych' })
    expect(grayStar).toHaveAttribute('aria-pressed', 'false')
    expect(grayStar).toHaveClass('text-slate-400')

    fireEvent.click(grayStar)
    expect(await screen.findByText('Ulubione i alerty')).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj bieżący' }))

    await waitFor(() => {
      const yellowStar = screen.getByRole('button', { name: 'Zarządzaj ulubionymi dla PKO' })
      expect(yellowStar).toHaveAttribute('aria-pressed', 'true')
      expect(yellowStar).toHaveClass('text-amber-400')
    })
    expect(addedPayloads).toEqual([{
      symbol: 'PKO',
      mic: 'XWAR',
      name: 'PKO Bank Polski',
    }])

    fireEvent.click(screen.getByRole('button', { name: 'Usuń bieżący' }))

    await waitFor(() => {
      const grayStarAfterRemoval = screen.getByRole('button', { name: 'Dodaj PKO do ulubionych' })
      expect(grayStarAfterRemoval).toHaveAttribute('aria-pressed', 'false')
      expect(grayStarAfterRemoval).toHaveClass('text-slate-400')
    })
    expect(deletedUrls).toHaveLength(1)
    expect(deletedUrls[0]).toContain('with_alert=true')
  })
})
