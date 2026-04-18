import { NextResponse } from 'next/server'

const UI_API_URL = process.env.UI_API_URL ?? ''

export async function POST(req: Request) {
  if (!UI_API_URL) {
    return NextResponse.json({ error: 'UI_API_URL is not configured' }, { status: 500 })
  }

  const form = await req.formData()
  const parserName = form.get('parser_name')
  const mode = form.get('mode')
  const file = form.get('file')

  if (typeof parserName !== 'string' || !parserName) {
    return NextResponse.json({ error: 'Wybierz format banku' }, { status: 422 })
  }

  if (!(file instanceof File)) {
    return NextResponse.json({ error: 'Wybierz plik do importu' }, { status: 422 })
  }

  const outbound = new FormData()
  outbound.append('parser_name', parserName)
  outbound.append('mode', typeof mode === 'string' && mode ? mode : 'transactions')
  outbound.append('file', file, file.name)

  try {
    const res = await fetch(`${UI_API_URL}/api/import/parse`, {
      method: 'POST',
      body: outbound,
      cache: 'no-store',
    })

    const text = await res.text()
    if (!res.ok) {
      try {
        const json = JSON.parse(text) as { detail?: string }
        return NextResponse.json({ error: json.detail ?? 'Nie udało się sparsować pliku' }, { status: res.status === 422 ? 422 : 400 })
      } catch {
        return NextResponse.json({ error: text || 'Nie udało się sparsować pliku' }, { status: 400 })
      }
    }

    return new NextResponse(text, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch {
    return NextResponse.json({ error: 'Nie udało się połączyć z parser service' }, { status: 400 })
  }
}
