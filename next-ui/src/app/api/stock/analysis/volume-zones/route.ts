import { NextRequest, NextResponse } from 'next/server'
import { getVolumeZones } from '@/lib/api/stock'
import type { VolumeZonesMode } from '@/lib/api/stock'

const MODES = new Set<VolumeZonesMode>(['summary', 'full', 'backtest'])

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const mic = searchParams.get('mic')?.trim().toUpperCase()
  const symbol = searchParams.get('symbol')?.trim().toUpperCase()
  const rawMode = searchParams.get('mode')?.trim() as VolumeZonesMode | null
  const mode = rawMode && MODES.has(rawMode) ? rawMode : 'summary'

  if (!mic) {
    return NextResponse.json({ error: 'mic jest wymagany' }, { status: 400 })
  }
  if (!symbol) {
    return NextResponse.json({ error: 'symbol jest wymagany' }, { status: 400 })
  }

  const maxZonesRaw = Number(searchParams.get('max_zones') ?? '3')
  const maxZones = Number.isFinite(maxZonesRaw) ? Math.min(20, Math.max(1, Math.trunc(maxZonesRaw))) : 3
  const result = await getVolumeZones(mic, symbol, {
    mode,
    dateFrom: searchParams.get('date_from'),
    dateTo: searchParams.get('date_to'),
    includeTimeline: searchParams.get('include_timeline') === 'true',
    maxZones,
  })

  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status })
  }

  return NextResponse.json(result.data)
}
