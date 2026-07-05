import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'

import { PriceAlertModal } from '@/features/wallet/components/PriceAlertModal'
import { nextUiUnitStory } from '../allure'

describe('PriceAlertModal', () => {
  it('accepts comma and dot decimal separators in price alert fields', async () => {
    await nextUiUnitStory('Price alert modal accepts Polish and canonical decimal separators', {
      severity: 'critical',
      tags: ['wallet', 'alerts', 'prices', 'next-ui'],
    })
    const onSaved = vi.fn()
    let payload: unknown = null

    server.use(
      http.post('*/api/wallet/alerts', async ({ request }) => {
        payload = await request.json()
        return HttpResponse.json({ id: 'alert-1' })
      }),
    )

    render(
      <PriceAlertModal
        symbol="PKO"
        name="PKO BP"
        initial={null}
        onClose={vi.fn()}
        onSaved={onSaved}
        onDeleted={vi.fn()}
      />,
    )

    const belowInput = screen.getByLabelText('Below price')
    const aboveInput = screen.getByLabelText('Above price')

    fireEvent.change(belowInput, { target: { value: '10,99' } })
    fireEvent.change(aboveInput, { target: { value: '12.50' } })

    expect(belowInput).toHaveValue('10,99')
    expect(aboveInput).toHaveValue('12.50')

    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))
    expect(payload).toMatchObject({
      symbol: 'PKO',
      below_price: '10,99',
      above_price: '12.50',
    })
  })
})
