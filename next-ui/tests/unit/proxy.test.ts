import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

import { nextUiUnitStory } from '../allure'

function request(path: string, host = 'next.localhost', headers: Record<string, string> = {}) {
  return new NextRequest(`http://${host}${path}`, {
    headers: {
      host,
      ...headers,
    },
  })
}

async function loadProxy() {
  return (await import('@/proxy')).proxy
}

describe('next-ui proxy', () => {
  beforeEach(() => {
    vi.stubEnv('NEXT_UI_DOMAIN', 'next.localhost:8081')
    vi.stubEnv('NEXT_PUBLIC_APP_URL', 'http://wallet.localhost')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
    vi.restoreAllMocks()
  })

  it('redirects the root route to the public home page', async () => {
    await nextUiUnitStory('Proxy redirects root route to public home', {
      severity: 'normal',
      tags: ['next-ui', 'routing'],
    })

    const proxy = await loadProxy()
    const response = proxy(request('/'))

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('http://next.localhost/home')
  })

  it('allows public authentication routes without injected auth headers', async () => {
    await nextUiUnitStory('Proxy allows public auth routes without auth headers', {
      severity: 'critical',
      tags: ['next-ui', 'auth', 'routing'],
    })

    const proxy = await loadProxy()
    const response = proxy(request('/login', 'next-ui:3000'))
    const logoutResponse = proxy(request('/logout', 'next-ui:3000'))
    const twoFactorResponse = proxy(request('/two-factor', 'next-ui:3000'))
    const homeResponse = proxy(request('/home', 'next-ui:3000'))

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-next')).toBe('1')
    expect(logoutResponse.status).toBe(200)
    expect(logoutResponse.headers.get('x-middleware-next')).toBe('1')
    expect(twoFactorResponse.status).toBe(200)
    expect(twoFactorResponse.headers.get('x-middleware-next')).toBe('1')
    expect(homeResponse.status).toBe(200)
    expect(homeResponse.headers.get('x-middleware-next')).toBe('1')
  })

  it('blocks protected routes on untrusted direct service hosts even with spoofed identity headers', async () => {
    await nextUiUnitStory('Proxy blocks direct protected route header spoofing', {
      severity: 'blocker',
      tags: ['next-ui', 'auth', 'security', 'routing'],
    })

    const proxy = await loadProxy()
    const response = proxy(request('/wallet', 'next-ui:3000', {
      'x-user': 'spoofed-user',
      'x-user-id': 'spoofed-wallet-user',
      'x-email': 'spoofed@example.com',
    }))

    expect(response.status).toBe(403)
    await expect(response.json()).resolves.toEqual({ error: 'Forbidden' })
  })

  it('redirects authenticated users away from login and register routes', async () => {
    await nextUiUnitStory('Proxy redirects authenticated users away from auth forms', {
      severity: 'critical',
      tags: ['next-ui', 'auth', 'routing'],
    })

    const proxy = await loadProxy()
    const loginResponse = proxy(request('/login', 'next.localhost', { 'x-user': 'artur' }))
    const registerResponse = proxy(request('/register', 'next.localhost', { 'x-user': 'artur' }))

    expect(loginResponse.status).toBe(307)
    expect(loginResponse.headers.get('location')).toBe('http://next.localhost/home')
    expect(registerResponse.status).toBe(307)
    expect(registerResponse.headers.get('location')).toBe('http://next.localhost/home')
  })

  it('keeps the two-factor route public even if an identity header is present', async () => {
    await nextUiUnitStory('Proxy keeps the two-factor challenge route public', {
      severity: 'critical',
      tags: ['next-ui', 'auth', 'routing', '2fa'],
    })

    const proxy = await loadProxy()
    const response = proxy(request('/two-factor', 'next.localhost', { 'x-user': 'artur' }))

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-next')).toBe('1')
  })

  it('allows protected routes from any host when no trusted host config is present', async () => {
    await nextUiUnitStory('Proxy allows hosts when trusted host configuration is empty', {
      severity: 'critical',
      tags: ['next-ui', 'auth', 'routing', 'configuration'],
    })
    vi.stubEnv('NEXT_UI_DOMAIN', '')
    vi.stubEnv('NEXT_PUBLIC_APP_URL', '')
    const proxy = await loadProxy()

    const response = proxy(request('/wallet', 'next-ui:3000'))

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-next')).toBe('1')
  })

  it('warns in production when trusted host configuration is empty', async () => {
    await nextUiUnitStory('Proxy warns when production host validation is unconfigured', {
      severity: 'critical',
      tags: ['next-ui', 'auth', 'routing', 'configuration'],
    })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.stubEnv('NEXT_UI_DOMAIN', '')
    vi.stubEnv('NEXT_PUBLIC_APP_URL', '')
    vi.stubEnv('NODE_ENV', 'production')

    const proxy = await loadProxy()
    const response = proxy(request('/wallet', 'next-ui:3000'))

    expect(response.status).toBe(200)
    expect(warn).toHaveBeenCalledWith(
      'NEXT_UI_DOMAIN and NEXT_PUBLIC_APP_URL are not configured; proxy host validation is disabled.',
    )
  })
})
