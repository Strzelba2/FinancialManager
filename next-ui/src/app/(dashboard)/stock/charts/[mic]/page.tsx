import { getInstruments, getMarkets } from '@/lib/api/stock'
import { ChartsPage } from '@/features/wallet/components/ChartsPage'

const DEFAULT_MARKETS = [
  { mic: 'XWAR', name: 'GPW' },
  { mic: 'XNCO', name: 'NewConnect' },
  { mic: 'STCM', name: 'RAW' },
  { mic: 'PLNC', name: 'PLN' },
]

function normalizeMarkets(markets: Array<{ mic: string; name: string }>) {
  return markets
    .map((market) => ({
      mic: market.mic.trim().toUpperCase(),
      name: market.name.trim(),
    }))
    .filter((market) => /^[A-Z0-9]{4}$/.test(market.mic))
}

export default async function StockChartsRoute({
  params,
  searchParams,
}: {
  params: Promise<{ mic: string }>
  searchParams: Promise<{ symbol?: string }>
}) {
  const { mic } = await params
  const { symbol } = await searchParams
  const normalizedMic = mic.trim().toUpperCase()
  const requestedMic = /^[A-Z0-9]{4}$/.test(normalizedMic) ? normalizedMic : null
  const marketsResult = await getMarkets({ onlyWithInstruments: true })
  const marketOptions = marketsResult.ok ? normalizeMarkets(marketsResult.data) : DEFAULT_MARKETS
  const markets = marketOptions.length > 0 ? marketOptions : DEFAULT_MARKETS
  const fallbackMic = markets[0]?.mic ?? 'XWAR'
  const safeMic = requestedMic && markets.some((market) => market.mic === requestedMic)
    ? requestedMic
    : fallbackMic

  const instrumentsResult = await getInstruments(safeMic)
  const instruments = instrumentsResult.ok ? instrumentsResult.data : []

  return (
    <ChartsPage
      key={`${safeMic}:${symbol?.trim().toUpperCase() ?? ''}`}
      mic={safeMic}
      marketOptions={markets}
      instruments={instruments}
      preselectedSymbol={symbol?.trim().toUpperCase() ?? null}
    />
  )
}
