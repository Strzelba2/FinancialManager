import { getInstruments } from '@/lib/api/stock'
import { ChartsPage } from '@/features/wallet/components/ChartsPage'

const VALID_MICS = ['XWAR', 'XNCO', 'STCM'] as const

export default async function StockChartsRoute({
  params,
  searchParams,
}: {
  params: Promise<{ mic: string }>
  searchParams: Promise<{ symbol?: string }>
}) {
  const { mic } = await params
  const { symbol } = await searchParams
  const safeMic = VALID_MICS.includes(mic as (typeof VALID_MICS)[number]) ? mic : 'XWAR'

  const instrumentsResult = await getInstruments(safeMic)
  const instruments = instrumentsResult.ok ? instrumentsResult.data : []

  return (
    <ChartsPage
      mic={safeMic}
      instruments={instruments}
      preselectedSymbol={symbol?.trim().toUpperCase() ?? null}
    />
  )
}
