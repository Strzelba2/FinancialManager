import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Redirect root to home — Traefik decides if /home is accessible
  if (pathname === '/') {
    return NextResponse.redirect(new URL('/home', request.url))
  }

  // X-User is injected by Traefik ForwardAuth when session is valid.
  // If user is already logged in and visits /login or /register — send them home.
  const xUser = request.headers.get('x-user')
  if (xUser && (pathname.startsWith('/login') || pathname.startsWith('/register'))) {
    return NextResponse.redirect(new URL('/home', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|api).*)'],
}
