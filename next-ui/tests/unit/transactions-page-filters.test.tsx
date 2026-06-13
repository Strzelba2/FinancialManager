import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'

import { TransactionsPage } from '@/features/wallet/components/TransactionsPage'
import { nextUiUnitStory } from '../allure'

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: vi.fn(),
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

describe('TransactionsPage filters', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })
  it('offers tax category and status filters for transaction classification', async () => {
    await nextUiUnitStory('Wallet transactions page exposes tax category and status filters', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'filters', 'next-ui'],
    })

    const requestedUrls: string[] = []
    server.use(http.get('*/api/wallet/transactions', ({ request }) => {
      requestedUrls.push(request.url)
      return HttpResponse.json({
        items: [],
        total: 0,
        page: 1,
        size: 40,
        sum_by_ccy: {},
      })
    }))

    render(<TransactionsPage accounts={[]} brokerageAccounts={[]} />)

    fireEvent.click(screen.getByRole('button', { name: /Kategorie/i }))
    fireEvent.click(screen.getByRole('button', { name: 'ZUS i podatki' }))

    fireEvent.click(screen.getByRole('button', { name: /Status/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Podatki' }))

    expect(screen.getAllByRole('button', { name: /ZUS i podatki/i }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /^Podatki/i }).length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(requestedUrls.some((url) => url.includes('category=ZUS_TAXES'))).toBe(true)
      expect(requestedUrls.some((url) => url.includes('status=TAXES'))).toBe(true)
    })
  })
})
