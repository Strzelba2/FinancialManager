import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import { nextUiUnitStory } from '../allure'

const mocks = vi.hoisted(() => ({
  cookieGet: vi.fn(),
  cookieSet: vi.fn(),
  headerGet: vi.fn(),
  loggerError: vi.fn(),
  loggerInfo: vi.fn(),
  loggerWarn: vi.fn(),
  requests: [] as Array<{
    body: unknown
    headers: Record<string, string>
    method: string
    url: string
  }>,
}))

vi.mock('next/headers', () => ({
  cookies: vi.fn(async () => ({
    get: mocks.cookieGet,
    set: mocks.cookieSet,
  })),
  headers: vi.fn(async () => ({
    get: mocks.headerGet,
  })),
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: mocks.loggerError,
    info: mocks.loggerInfo,
    warn: mocks.loggerWarn,
  },
}))

function tokenForm(token = '123456'): FormData {
  const data = new FormData()
  data.set('token', token)
  return data
}

async function loadActions() {
  return import('@/features/auth/actions/two-factor')
}

const server = setupServer()

describe('two-factor auth actions', () => {
  beforeAll(() => {
    server.listen({ onUnhandledRequest: 'error' })
  })

  beforeEach(() => {
    mocks.cookieGet.mockReset()
    mocks.cookieSet.mockReset()
    mocks.headerGet.mockReset()
    mocks.loggerError.mockReset()
    mocks.loggerInfo.mockReset()
    mocks.loggerWarn.mockReset()
    mocks.requests = []
    mocks.cookieGet.mockImplementation((name: string) => {
      if (name === 'sessionid') return { value: 'session-value' }
      if (name === 'hmac') return { value: 'hmac-value' }
      return undefined
    })
    mocks.headerGet.mockImplementation((name: string) => {
      const normalized = name.toLowerCase()
      if (normalized === 'x-forwarded-for') return '203.0.113.10, 10.0.0.1'
      if (normalized === 'user-agent') return 'Vitest Browser'
      if (normalized === 'sec-ch-ua-platform') return '"Linux"'
      return ''
    })
    vi.stubEnv('SESSION_AUTH_URL', 'http://session-auth:8000')
    vi.stubEnv('NEXT_UI_DOMAIN', 'next.localhost:8081')
    vi.stubEnv('NEXT_PUBLIC_APP_URL', '')
    vi.stubEnv('APP_PROTOCOL', 'http')
    server.resetHandlers()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  afterAll(() => {
    server.close()
  })

  it('verifies a pending 2FA session and stores only auth cookies from session-auth', async () => {
    await nextUiUnitStory('Two-factor action completes pending login with HMAC cookie', {
      severity: 'blocker',
      tags: ['auth', 'security', '2fa', 'cookies'],
    })
    server.use(http.post('http://session-auth:8000/two-factor/verify/', async ({ request }) => {
      mocks.requests.push({
        body: await request.json(),
        headers: Object.fromEntries(request.headers.entries()),
        method: request.method,
        url: request.url,
      })
      const headers = new Headers({ 'Content-Type': 'application/json' })
      headers.append('Set-Cookie', 'hmac_token=fresh-hmac; Path=/; HttpOnly; SameSite=Lax')
      headers.append('Set-Cookie', 'analytics_id=ignored; Path=/')
      return HttpResponse.json({ message: 'Two-factor verification successful' }, { headers })
    }))
    const { verifyTwoFactorAction } = await loadActions()

    await expect(verifyTwoFactorAction(undefined, tokenForm())).resolves.toEqual({ success: true })

    expect(mocks.requests).toHaveLength(1)
    expect(mocks.requests[0]).toEqual(expect.objectContaining({
      body: { token: '123456' },
      method: 'POST',
      url: 'http://session-auth:8000/two-factor/verify/',
    }))
    expect(mocks.requests[0]?.headers).toEqual(expect.objectContaining({
      accept: 'application/json',
      'content-type': 'application/json',
      cookie: 'sessionid=session-value; hmac=hmac-value',
      referer: 'http://next.localhost:8081/two-factor/verify/',
      'x-original-client-ip': '203.0.113.10',
      'user-agent': 'Vitest Browser',
    }))
    expect(mocks.cookieSet).toHaveBeenCalledTimes(1)
    expect(mocks.cookieSet).toHaveBeenCalledWith('hmac', 'fresh-hmac', {
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      secure: false,
    })
  })

  it('rejects malformed 2FA codes before calling session-auth', async () => {
    await nextUiUnitStory('Two-factor action validates token shape before server calls', {
      severity: 'critical',
      tags: ['auth', 'security', '2fa', 'validation'],
    })
    server.use(http.post('http://session-auth:8000/two-factor/verify/', async ({ request }) => {
      mocks.requests.push({
        body: await request.json(),
        headers: Object.fromEntries(request.headers.entries()),
        method: request.method,
        url: request.url,
      })
      return HttpResponse.json({ message: 'should not be called' })
    }))
    const { verifyTwoFactorAction } = await loadActions()

    const result = await verifyTwoFactorAction(undefined, tokenForm('12x'))

    expect(result?.errors?.token).toEqual(['Podaj 6-cyfrowy kod'])
    expect(mocks.requests).toHaveLength(0)
    expect(mocks.cookieSet).not.toHaveBeenCalled()
  })

  it('fails closed when verification is called without a pending session cookie', async () => {
    await nextUiUnitStory('Two-factor verify action requires the pending session cookie', {
      severity: 'blocker',
      tags: ['auth', 'security', '2fa', 'cookies'],
    })
    mocks.cookieGet.mockImplementation((name: string) => (
      name === 'hmac' ? { value: 'hmac-value' } : undefined
    ))
    const { verifyTwoFactorAction } = await loadActions()

    await expect(verifyTwoFactorAction(undefined, tokenForm())).resolves.toEqual({
      message: 'Sesja wygasła. Zaloguj się ponownie.',
    })

    expect(mocks.requests).toHaveLength(0)
    expect(mocks.cookieSet).not.toHaveBeenCalled()
  })

  it('returns the QR image from session-auth setup without enabling 2FA in next-ui', async () => {
    await nextUiUnitStory('Two-factor setup action renders session-auth QR payload', {
      severity: 'critical',
      tags: ['auth', 'security', '2fa', 'api-contract'],
    })
    server.use(http.post('http://session-auth:8000/two-factor/setup/', async ({ request }) => {
      mocks.requests.push({
        body: await request.json(),
        headers: Object.fromEntries(request.headers.entries()),
        method: request.method,
        url: request.url,
      })
      return HttpResponse.json({ image: 'svg-base64', is_two_factor_enabled: false })
    }))
    const { setupTwoFactorAction } = await loadActions()

    await expect(setupTwoFactorAction(undefined, new FormData())).resolves.toEqual({
      image: 'svg-base64',
      success: true,
    })

    expect(mocks.requests).toHaveLength(1)
    expect(mocks.requests[0]?.body).toEqual({})
    expect(mocks.cookieSet).not.toHaveBeenCalled()
  })

  it('maps invalid enable codes without changing client cookies', async () => {
    await nextUiUnitStory('Two-factor enable action maps invalid token errors', {
      severity: 'blocker',
      tags: ['auth', 'security', '2fa', 'error-state'],
    })
    server.use(http.post('http://session-auth:8000/two-factor/enable/', () => (
      HttpResponse.json({ error: 'Invalid 2FA code.' }, { status: 401 })
    )))
    const { enableTwoFactorAction } = await loadActions()

    await expect(enableTwoFactorAction(undefined, tokenForm())).resolves.toEqual({
      message: 'Invalid 2FA code.',
    })
    expect(mocks.cookieSet).not.toHaveBeenCalled()
  })
})
