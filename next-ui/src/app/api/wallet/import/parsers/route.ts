import { NextResponse } from 'next/server'

const UI_API_URL = process.env.UI_API_URL ?? ''

export async function GET() {
  if (!UI_API_URL) {
    return NextResponse.json({ error: 'UI_API_URL is not configured' }, { status: 500 })
  }

  try {
    const res = await fetch(`${UI_API_URL}/api/import/parsers`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })

    const text = await res.text()
    if (!res.ok) {
      // Don't expose raw HTML pages (e.g. Traefik 502/404) as error text
      let errorMsg = 'Nie udało się pobrać listy parserów importu'
      if (!text.trimStart().startsWith('<')) {
        try {
          const json = JSON.parse(text) as { error?: string; detail?: string }
          errorMsg = json.error || json.detail || errorMsg
        } catch { /* keep generic */ }
      }
      return NextResponse.json({ error: errorMsg }, { status: 400 })
    }

    // Sanity-check: make sure we forward JSON, not an HTML error page
    if (text.trimStart().startsWith('<')) {
      return NextResponse.json({ error: 'Serwis parserów nie odpowiedział poprawnie' }, { status: 502 })
    }

    return new NextResponse(text, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch {
    return NextResponse.json({ error: 'Nie udało się połączyć z parser service' }, { status: 400 })
  }
}
