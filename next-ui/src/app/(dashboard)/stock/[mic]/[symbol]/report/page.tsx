import { EquityReportPage } from '@/features/reports/components/EquityReportPage'
import { getEquityReport } from '@/lib/api/stock'
import { notFound } from 'next/navigation'

export default async function StockReportRoute({
  params,
  searchParams,
}: {
  params: Promise<{ mic: string; symbol: string }>
  searchParams: Promise<{ period?: string | string[] }>
}) {
  const { mic, symbol } = await params
  const resolvedSearchParams = await searchParams
  const period = Array.isArray(resolvedSearchParams.period)
    ? resolvedSearchParams.period[0]
    : resolvedSearchParams.period

  const result = await getEquityReport(mic, symbol, period ?? null)
  if (result.ok) {
    return <EquityReportPage report={result.data.report} availablePeriods={result.data.availablePeriods} />
  }

  if (result.status === 404) {
    notFound()
  }

  throw new Error(result.error)
}
