import { getQuotesBulk, processQuotes } from '@/lib/api/stock'
import { QuotesPage } from '@/features/wallet/components/QuotesPage'

export default async function StockQuotesRoute({
  params,
}: {
  params: Promise<{ mic: string }>
}) {
  const { mic } = await params
  const normalizedMic = mic.trim().toUpperCase()
  const safeMic = /^[A-Z0-9]{4}$/.test(normalizedMic) ? normalizedMic : 'XWAR'

  const raw = await getQuotesBulk(safeMic)
  const initialRows = processQuotes(raw)

  return <QuotesPage mic={safeMic} initialRows={initialRows} />
}
