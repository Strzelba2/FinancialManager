import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getVolumeZones } from '@/lib/api/stock'
import { GET as getVolumeZonesRoute } from '@/app/api/stock/analysis/volume-zones/route'
import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/stock', () => ({
  getVolumeZones: vi.fn(),
}))

describe('stock volume-zone route handler', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requires mic and symbol before calling the stock service', async () => {
    await nextUiUnitStory('Stock volume-zone route validates required identifiers', {
      severity: 'normal',
      tags: ['stock', 'volume-zones', 'api-route', 'validation'],
    })

    const response = await getVolumeZonesRoute(new NextRequest('http://localhost/api/stock/analysis/volume-zones?mic=XWAR'))

    expect(response.status).toBe(400)
    expect(getVolumeZones).not.toHaveBeenCalled()
  })

  it('forwards normalized query parameters and preserves backend status', async () => {
    await nextUiUnitStory('Stock volume-zone route forwards deterministic analysis options', {
      severity: 'critical',
      tags: ['stock', 'volume-zones', 'api-route', 'api-contract'],
    })
    vi.mocked(getVolumeZones).mockResolvedValue({
      ok: false,
      error: 'At least 25 valid daily candles are required for volume-zone analysis.',
      status: 422,
    })

    const response = await getVolumeZonesRoute(new NextRequest(
      'http://localhost/api/stock/analysis/volume-zones?mic=xwar&symbol=pko&mode=full&include_timeline=true&max_zones=99',
    ))

    expect(response.status).toBe(422)
    await expect(response.json()).resolves.toEqual({
      error: 'At least 25 valid daily candles are required for volume-zone analysis.',
    })
    expect(getVolumeZones).toHaveBeenCalledWith('XWAR', 'PKO', {
      mode: 'full',
      dateFrom: null,
      dateTo: null,
      includeTimeline: true,
      maxZones: 20,
    })
  })
})
