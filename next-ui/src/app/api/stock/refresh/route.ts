import { NextResponse } from 'next/server'
import {
  getCeleryStatus,
  getManualIngestStatus,
  startManualIngest,
} from '@/lib/api/stock'

export async function GET() {
  const result = await getManualIngestStatus()
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status })
  }

  return NextResponse.json(result.data)
}

export async function POST() {
  const celery = await getCeleryStatus()
  if (!celery.ok) {
    return NextResponse.json({ error: celery.error }, { status: celery.status })
  }

  const ingest = await startManualIngest()
  if (!ingest.ok) {
    return NextResponse.json({ error: ingest.error }, { status: ingest.status })
  }

  if (!ingest.data.ok && (ingest.data.detail ?? '').toLowerCase().includes('already running')) {
    return NextResponse.json(
      {
        ok: true,
        mode: 'ingest',
        alreadyRunning: true,
        detail: ingest.data.detail,
        workers: celery.data.workers,
      },
      { status: 202 },
    )
  }

  if (!ingest.data.ok) {
    return NextResponse.json(
      { error: ingest.data.detail ?? 'Nie udało się uruchomić odświeżania notowań' },
      { status: 409 },
    )
  }

  return NextResponse.json(
    {
      ok: true,
      mode: 'ingest',
      alreadyRunning: false,
      detail: ingest.data.detail,
      workers: celery.data.workers,
    },
    { status: 202 },
  )
}
