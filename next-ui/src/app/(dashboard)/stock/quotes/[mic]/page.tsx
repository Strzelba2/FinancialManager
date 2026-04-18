import { getQuotesBulk, processQuotes } from '@/lib/api/stock'
import { QuotesPage } from '@/features/wallet/components/QuotesPage'

const VALID_MICS = ['XWAR', 'XNCO', 'STCM'] as const

export default async function StockQuotesRoute({
  params,
}: {
  params: Promise<{ mic: string }>
}) {
  const { mic } = await params
  const safeMic = VALID_MICS.includes(mic as (typeof VALID_MICS)[number]) ? mic : 'XWAR'

  const raw = await getQuotesBulk(safeMic)
  const initialRows = processQuotes(raw)

  return <QuotesPage mic={safeMic} initialRows={initialRows} />
}
