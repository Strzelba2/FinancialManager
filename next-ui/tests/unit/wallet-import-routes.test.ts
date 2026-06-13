import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'

import { nextUiUnitStory } from '../allure'

async function loadParsersRoute() {
  vi.resetModules()
  process.env.UI_API_URL = 'http://nice-ui:8501'
  return import('@/app/api/wallet/import/parsers/route')
}

async function loadParseRoute() {
  vi.resetModules()
  process.env.UI_API_URL = 'http://nice-ui:8501'
  return import('@/app/api/wallet/import/parse/route')
}

describe('wallet import proxy routes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })

  afterEach(() => {
    vi.resetModules()
    delete process.env.UI_API_URL
  })
  it('forwards parser metadata JSON from the parser service', async () => {
    await nextUiUnitStory('Wallet import route forwards parser metadata JSON', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'api-route'],
    })
    const parserPayload = [
      {
        name: 'mBank CSV',
        kind: 'CSV',
        accept: '.csv',
        upload_label: 'Drop CSV here or click',
        supports_brokerage_events: false,
      },
      {
        name: 'IngBank CSV',
        kind: 'CSV',
        accept: '.csv',
        upload_label: 'Drop CSV here or click',
        supports_brokerage_events: false,
      },
      {
        name: 'Velo Bank PDF',
        kind: 'PDF',
        accept: '.pdf',
        upload_label: 'Drop PDF here or click',
        supports_brokerage_events: false,
      },
    ]
    const requests: Request[] = []
    server.use(http.get('http://nice-ui:8501/api/import/parsers', ({ request }) => {
      requests.push(request)
      return HttpResponse.json(parserPayload)
    }))
    const { GET } = await loadParsersRoute()

    const response = await GET()

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual(parserPayload)
    expect(requests).toHaveLength(1)
    expect(requests[0]?.headers.get('Accept')).toBe('application/json')
  })

  it.each([
    ['IngBank CSV', 'ing.csv', 'text/csv', 'Data księgowania;Kwota transakcji (waluta rachunku)\n'],
    ['Velo Bank PDF', 'velo.pdf', 'application/pdf', '%PDF-1.4\n'],
  ])('forwards %s parser uploads to parser service', async (parserName, fileName, contentType, content) => {
    await nextUiUnitStory(`Wallet import route forwards ${parserName} uploads`, {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'api-route'],
    })
    const outboundRequests: FormData[] = []
    server.use(http.post('http://nice-ui:8501/api/import/parse', async ({ request }) => {
      outboundRequests.push(await request.formData())
      return HttpResponse.json({ mode: 'transactions', count: 1, rows: [] })
    }))
    const { POST } = await loadParseRoute()
    const form = new FormData()
    form.append('parser_name', parserName)
    form.append('mode', 'transactions')
    form.append('file', new Blob([content], { type: contentType }), fileName)

    const response = await POST({
      formData: async () => form,
    } as unknown as Request)

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ mode: 'transactions', count: 1, rows: [] })
    const outbound = outboundRequests[0]!
    expect(outbound.get('parser_name')).toBe(parserName)
    expect(outbound.get('mode')).toBe('transactions')
    await expect((outbound.get('file') as File).text()).resolves.toBe(content)
  })

  it('returns a safe parser-list error when the parser service sends HTML', async () => {
    await nextUiUnitStory('Wallet import route hides parser service HTML errors', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'api-route', 'error-state'],
    })
    server.use(http.get('http://nice-ui:8501/api/import/parsers', () => (
      new HttpResponse('<html>bad gateway</html>', { status: 502 })
    )))
    const { GET } = await loadParsersRoute()

    const response = await GET()

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({
      error: 'Nie udało się pobrać listy parserów importu',
    })
  })

  it('maps parser validation errors from CSV parse requests', async () => {
    await nextUiUnitStory('Wallet import route maps CSV parser validation errors', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'api-route', 'validation'],
    })
    server.use(http.post('http://nice-ui:8501/api/import/parse', () => (
      HttpResponse.json({ detail: 'Missing required columns: Kwota' }, { status: 422 })
    )))
    const { POST } = await loadParseRoute()
    const form = new FormData()
    form.append('parser_name', 'mBank CSV')
    form.append('mode', 'transactions')
    form.append('file', new File(['Data;Kwota\n'], 'transactions.csv', { type: 'text/csv' }))

    const response = await POST({
      formData: async () => form,
    } as unknown as Request)

    expect(response.status).toBe(422)
    await expect(response.json()).resolves.toEqual({ error: 'Missing required columns: Kwota' })
  })

  it('rejects parse requests without parser name or file before calling parser service', async () => {
    await nextUiUnitStory('Wallet import route validates parser upload form data', {
      severity: 'critical',
      tags: ['wallet', 'transactions', 'import', 'api-route', 'validation'],
    })
    let parserServiceCalled = false
    server.use(http.post('http://nice-ui:8501/api/import/parse', () => {
      parserServiceCalled = true
      return HttpResponse.json({ mode: 'transactions', count: 0, rows: [] })
    }))
    const { POST } = await loadParseRoute()

    const response = await POST(new Request('http://localhost/api/wallet/import/parse', {
      method: 'POST',
      body: new FormData(),
    }))

    expect(response.status).toBe(422)
    await expect(response.json()).resolves.toEqual({ error: 'Wybierz format banku' })
    expect(parserServiceCalled).toBe(false)
  })
})
