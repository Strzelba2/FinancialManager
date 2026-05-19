'use server'

import { cookies, headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { logger } from '@/lib/logger'
import { sessionAuthReferer, shouldUseSecureAuthCookies } from './cookie-options'

export async function logoutAction(): Promise<void> {
  const cookieStore = await cookies()
  const sessionid = cookieStore.get('sessionid')?.value
  const hmac = cookieStore.get('hmac')?.value
  const authUrl = process.env.SESSION_AUTH_URL

  if (authUrl && sessionid) {
    const reqHeaders = await headers()
    const xForwardedFor = reqHeaders.get('x-forwarded-for') ?? ''
    const clientIp =
      (xForwardedFor.split(',')[0] ?? '').trim() ||
      reqHeaders.get('x-real-ip') ||
      ''
    const userAgent = reqHeaders.get('user-agent') ?? ''
    const uaPlatform = reqHeaders.get('sec-ch-ua-platform') ?? ''
    const cookieHeader = [
      `sessionid=${sessionid}`,
      hmac ? `hmac=${hmac}` : '',
    ]
      .filter(Boolean)
      .join('; ')

    try {
      const response = await fetch(`${authUrl}/logout/`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          Referer: sessionAuthReferer('/logout'),
          Cookie: cookieHeader,
          ...(clientIp ? { 'X-Original-Client-IP': clientIp } : {}),
          ...(userAgent ? { 'User-Agent': userAgent } : {}),
          ...(uaPlatform ? { 'Sec-CH-UA-Platform': uaPlatform } : {}),
        },
        cache: 'no-store',
      })
      logger.info({ status: response.status }, 'session-auth logout response')
    } catch (err) {
      logger.error({ err }, 'session-auth logout request failed')
    }
  } else if (!authUrl) {
    logger.error('SESSION_AUTH_URL is not configured')
  }

  const secure = shouldUseSecureAuthCookies()
  const expiredCookie = {
    httpOnly: true,
    sameSite: 'lax' as const,
    path: '/',
    secure,
    maxAge: 0,
  }
  cookieStore.set('sessionid', '', expiredCookie)
  cookieStore.set('hmac', '', expiredCookie)

  redirect('/login')
}
