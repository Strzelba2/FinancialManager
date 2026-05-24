import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import { nextUiUnitStory } from '../allure'

const mocks = vi.hoisted(() => ({
  cookieSet: vi.fn(),
  headerGet: vi.fn(),
  loggerError: vi.fn(),
  loggerInfo: vi.fn(),
  loggerWarn: vi.fn(),
  loginRequests: [] as Array<{
    body: unknown
    headers: Record<string, string>
    method: string
    url: string
  }>,
}))

vi.mock('next/headers', () => ({
  cookies: vi.fn(async () => ({
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

function formData(email = 'artur.tests@example.com', password = 'SecretPass123!'): FormData {
  const data = new FormData()
  data.set('email', email)
  data.set('password', password)
  return data
}

function responseWithSetCookies(setCookies: string[], status = 200): Response {
  const headers = new Headers({
    'Content-Type': 'application/json',
  })
  for (const cookie of setCookies) {
    headers.append('Set-Cookie', cookie)
  }

  return HttpResponse.json({ message: 'Login successful' }, { status, headers }) as Response
}

function jsonResponse(body: Parameters<typeof HttpResponse.json>[0], status: number) {
  return HttpResponse.json(body, { status })
}

function textResponse(body: string, status: number) {
  return new HttpResponse(body, {
    status,
    headers: { 'Content-Type': 'text/html' },
  })
}

function serializedLogCalls(): string {
  return JSON.stringify([
    mocks.loggerError.mock.calls,
    mocks.loggerInfo.mock.calls,
    mocks.loggerWarn.mock.calls,
  ])
}

async function loadLoginAction() {
  return (await import('@/features/auth/actions/login')).loginAction
}

const server = setupServer()

describe('loginAction', () => {
  beforeAll(() => {
    server.listen({ onUnhandledRequest: 'error' })
  })

  beforeEach(() => {
    mocks.cookieSet.mockReset()
    mocks.headerGet.mockReset()
    mocks.loggerError.mockReset()
    mocks.loggerInfo.mockReset()
    mocks.loggerWarn.mockReset()
    mocks.loginRequests = []
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

  it('stores only allowed auth cookies with secure transport settings', async () => {
    await nextUiUnitStory('Login action stores auth cookies with secure flags', {
      severity: 'critical',
      tags: ['auth', 'security', 'cookies'],
    })
    vi.stubEnv('AUTH_COOKIE_SECURE', 'true')
    server.use(http.post('http://session-auth:8000/login/', async ({ request }) => {
      mocks.loginRequests.push({
        body: await request.json(),
        headers: Object.fromEntries(request.headers.entries()),
        method: request.method,
        url: request.url,
      })
      return responseWithSetCookies([
        'sessionid=session-value; Path=/; HttpOnly; SameSite=Lax',
        'hmac_token=hmac-token-value; Path=/; HttpOnly; SameSite=Lax',
        'analytics_id=ignored; Path=/',
      ])
    }))
    const loginAction = await loadLoginAction()

    await expect(loginAction(undefined, formData())).resolves.toEqual({ success: true })

    expect(mocks.loginRequests).toHaveLength(1)
    expect(mocks.loginRequests[0]).toEqual(expect.objectContaining({
      body: { email: 'artur.tests@example.com', password: 'SecretPass123!' },
      method: 'POST',
      url: 'http://session-auth:8000/login/',
    }))
    expect(mocks.loginRequests[0]?.headers).toEqual(expect.objectContaining({
      'content-type': 'application/json',
      accept: 'application/json',
      referer: 'http://next.localhost:8081/login',
      'x-original-client-ip': '203.0.113.10',
      'user-agent': 'Vitest Browser',
      'sec-ch-ua-platform': '"Linux"',
    }))
    expect(mocks.cookieSet).toHaveBeenCalledTimes(2)
    expect(mocks.cookieSet).toHaveBeenCalledWith('sessionid', 'session-value', {
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      secure: true,
    })
    expect(mocks.cookieSet).toHaveBeenCalledWith('hmac', 'hmac-token-value', {
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      secure: true,
    })
    expect(mocks.loggerInfo).toHaveBeenCalledWith('login successful')
    expect(serializedLogCalls()).not.toContain('artur.tests@example.com')
    expect(serializedLogCalls()).not.toContain('SecretPass123!')
    expect(serializedLogCalls()).not.toContain('hmac-token-value')
    expect(serializedLogCalls()).not.toContain('session-value')
  })

  it('uses the configured Next UI protocol and domain for the session-auth referer', async () => {
    await nextUiUnitStory('Login action derives Referer from the Next UI domain', {
      severity: 'critical',
      tags: ['auth', 'security', 'api-contract'],
    })
    vi.stubEnv('NEXT_UI_DOMAIN', 'next.example.test')
    vi.stubEnv('APP_PROTOCOL', 'https')
    server.use(http.post('http://session-auth:8000/login/', async ({ request }) => {
      mocks.loginRequests.push({
        body: await request.json(),
        headers: Object.fromEntries(request.headers.entries()),
        method: request.method,
        url: request.url,
      })
      return responseWithSetCookies([
        'sessionid=session-value; Path=/; HttpOnly; SameSite=Lax',
        'hmac_token=hmac-token-value; Path=/; HttpOnly; SameSite=Lax',
      ])
    }))
    const loginAction = await loadLoginAction()

    await expect(loginAction(undefined, formData())).resolves.toEqual({ success: true })

    expect(mocks.loginRequests[0]?.headers).toEqual(expect.objectContaining({
      referer: 'https://next.example.test/login',
    }))
  })

  it('stores the pending session and returns a 2FA challenge without HMAC cookies', async () => {
    await nextUiUnitStory('Login action handles session-auth two-factor challenges', {
      severity: 'blocker',
      tags: ['auth', 'security', '2fa', 'api-contract'],
    })
    server.use(http.post('http://session-auth:8000/login/', async ({ request }) => {
      mocks.loginRequests.push({
        body: await request.json(),
        headers: Object.fromEntries(request.headers.entries()),
        method: request.method,
        url: request.url,
      })
      const headers = new Headers({ 'Content-Type': 'application/json' })
      headers.append('Set-Cookie', 'sessionid=pending-session; Path=/; HttpOnly; SameSite=Lax')
      return HttpResponse.json({ requires_two_factor: true }, { status: 202, headers })
    }))
    const loginAction = await loadLoginAction()

    await expect(loginAction(undefined, formData())).resolves.toEqual({ requiresTwoFactor: true })

    expect(mocks.cookieSet).toHaveBeenCalledTimes(1)
    expect(mocks.cookieSet).toHaveBeenCalledWith('sessionid', 'pending-session', {
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      secure: false,
    })
    expect(mocks.cookieSet).not.toHaveBeenCalledWith(
      'hmac',
      expect.any(String),
      expect.any(Object),
    )
    expect(mocks.loggerInfo).toHaveBeenCalledWith('login requires two-factor verification')
  })

  it('rejects invalid local form input before calling session-auth', async () => {
    await nextUiUnitStory('Login action validates form data before server calls', {
      severity: 'critical',
      tags: ['auth', 'validation', 'security'],
    })
    server.use(http.post('http://session-auth:8000/login/', async ({ request }) => {
      mocks.loginRequests.push({
        body: await request.json(),
        headers: Object.fromEntries(request.headers.entries()),
        method: request.method,
        url: request.url,
      })
      return HttpResponse.json({ message: 'should not be called' })
    }))
    const loginAction = await loadLoginAction()

    const result = await loginAction(undefined, formData('not-an-email', ''))

    expect(result?.errors?.email).toEqual(['Podaj poprawny adres email'])
    expect(result?.errors?.password).toEqual(['Hasło jest wymagane'])
    expect(mocks.loginRequests).toHaveLength(0)
    expect(mocks.cookieSet).not.toHaveBeenCalled()
  })

  it('fails safely when session-auth is not configured or reachable', async () => {
    await nextUiUnitStory('Login action handles auth service configuration and network failures', {
      severity: 'critical',
      tags: ['auth', 'security', 'error-state'],
    })
    vi.stubEnv('SESSION_AUTH_URL', '')
    server.use(http.post('http://session-auth:8000/login/', async ({ request }) => {
      mocks.loginRequests.push({
        body: await request.json(),
        headers: Object.fromEntries(request.headers.entries()),
        method: request.method,
        url: request.url,
      })
      return HttpResponse.json({ message: 'should not be called' })
    }))
    let loginAction = await loadLoginAction()

    await expect(loginAction(undefined, formData())).resolves.toEqual({
      message: 'Błąd konfiguracji serwera',
    })
    expect(mocks.loginRequests).toHaveLength(0)
    expect(mocks.cookieSet).not.toHaveBeenCalled()

    vi.resetModules()
    vi.stubEnv('SESSION_AUTH_URL', 'http://session-auth:8000')
    server.use(http.post('http://session-auth:8000/login/', () => HttpResponse.error()))
    loginAction = await loadLoginAction()

    await expect(loginAction(undefined, formData())).resolves.toEqual({
      message: 'Błąd połączenia z serwerem autoryzacji',
    })
    expect(mocks.cookieSet).not.toHaveBeenCalled()
  })

  it('keeps auth credentials and raw rejection body out of logs', async () => {
    await nextUiUnitStory('Login action does not leak credentials or response bodies to logs', {
      severity: 'blocker',
      tags: ['auth', 'security', 'logging'],
    })
    server.use(http.post('http://session-auth:8000/login/', () => jsonResponse({
      error: 'Incorrect email or password.',
      email: 'artur.tests@example.com',
      password: 'SecretPass123!',
      hmac: 'hmac-token-value',
      sessionid: 'session-value',
    }, 401)))
    const loginAction = await loadLoginAction()

    await expect(loginAction(undefined, formData())).resolves.toEqual({
      message: 'Incorrect email or password.',
    })

    expect(mocks.cookieSet).not.toHaveBeenCalled()
    expect(mocks.loggerWarn).toHaveBeenCalledWith(
      { status: 401 },
      'login rejected by session-auth',
    )
    const calls = serializedLogCalls()
    expect(calls).not.toContain('artur.tests@example.com')
    expect(calls).not.toContain('SecretPass123!')
    expect(calls).not.toContain('hmac-token-value')
    expect(calls).not.toContain('session-value')
    expect(calls).not.toContain('Incorrect email or password.')
  })

  it('maps security and concurrency fallback statuses safely when body is HTML', async () => {
    await nextUiUnitStory('Login action maps security and concurrency statuses', {
      severity: 'critical',
      tags: ['auth', 'security', 'api-contract'],
    })
    let calls = 0
    server.use(http.post('http://session-auth:8000/login/', () => {
      calls += 1
      return calls === 1
        ? textResponse('<html>blocked</html>', 403)
        : textResponse('<html>conflict</html>', 409)
    }))
    const loginAction = await loadLoginAction()

    await expect(loginAction(undefined, formData())).resolves.toEqual({
      message: 'Logowanie zostało zablokowane ze względów bezpieczeństwa.',
    })
    await expect(loginAction(undefined, formData())).resolves.toEqual({
      message: 'Logowanie jest już aktywne. Odśwież stronę albo spróbuj ponownie za chwilę.',
    })
    expect(mocks.cookieSet).not.toHaveBeenCalled()
  })

  it('fails closed when session-auth returns success without readable auth cookies', async () => {
    await nextUiUnitStory('Login action rejects successful responses without auth cookies', {
      severity: 'blocker',
      tags: ['auth', 'security', 'cookies'],
    })
    server.use(http.post('http://session-auth:8000/login/', () => HttpResponse.json({
      message: 'Login successful',
    })))
    const loginAction = await loadLoginAction()

    await expect(loginAction(undefined, formData())).resolves.toEqual({
      message: 'Brak danych sesji w odpowiedzi serwera autoryzacji',
    })
    expect(mocks.cookieSet).not.toHaveBeenCalled()
  })
})
