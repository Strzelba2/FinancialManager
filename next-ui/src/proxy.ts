import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const PUBLIC_PATH_PREFIXES = [
  '/home',
  '/login',
  '/logout',
  '/register',
  '/two-factor',
]

function bareHost(value: string): string {
  return value.trim().toLowerCase().split(':')[0] ?? ''
}

function configuredNextHosts(): Set<string> {
  const hosts = new Set<string>()
  const nextUiDomain = process.env.NEXT_UI_DOMAIN ?? ''
  const publicAppUrl = process.env.NEXT_PUBLIC_APP_URL ?? ''

  if (nextUiDomain) {
    hosts.add(bareHost(nextUiDomain))
  } else if (publicAppUrl) {
    try {
      hosts.add(bareHost(new URL(publicAppUrl).host))
    } catch {
      // Ignore malformed optional public URL configuration.
    }
  }

  return hosts
}

const TRUSTED_HOSTS = configuredNextHosts()

if (process.env.NODE_ENV === 'production' && TRUSTED_HOSTS.size === 0) {
  console.warn('NEXT_UI_DOMAIN and NEXT_PUBLIC_APP_URL are not configured; proxy host validation is disabled.')
}

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATH_PREFIXES.some((prefix) => (
    pathname === prefix || pathname.startsWith(`${prefix}/`)
  ))
}

function isTrustedHost(request: NextRequest): boolean {
  if (TRUSTED_HOSTS.size === 0) {
    return true
  }

  const host = bareHost(request.headers.get('host') ?? '')
  return TRUSTED_HOSTS.has(host)
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Redirect root to home — Traefik decides if /home is accessible
  if (pathname === '/') {
    return NextResponse.redirect(new URL('/home', request.url))
  }

  if (!isPublicPath(pathname) && !isTrustedHost(request)) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 })
  }

  // X-User is injected by Traefik ForwardAuth when session is valid.
  // If user is already logged in and visits /login or /register — send them home.
  const xUser = request.headers.get('x-user')
  if (
    xUser &&
    (pathname.startsWith('/login') || pathname.startsWith('/register'))
  ) {
    return NextResponse.redirect(new URL('/home', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|api).*)'],
}
