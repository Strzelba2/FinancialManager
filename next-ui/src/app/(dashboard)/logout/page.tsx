import { cookies, headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { logger } from '@/lib/logger'

export default async function LogoutPage() {
  const cookieStore = await cookies()
  const sessionid = cookieStore.get('sessionid')?.value
  const hmac = cookieStore.get('hmac')?.value

  const authUrl = process.env.SESSION_AUTH_URL

  if (authUrl) {
    const reqHeaders = await headers()
    const xForwardedFor = reqHeaders.get('x-forwarded-for') ?? ''
    const clientIp =
      (xForwardedFor.split(',')[0] ?? '').trim() ||
      reqHeaders.get('x-real-ip') ||
      ''
    const userAgent = reqHeaders.get('user-agent') ?? ''
    const uaPlatform = reqHeaders.get('sec-ch-ua-platform') ?? ''
    const nextUiDomain = process.env.NEXT_UI_DOMAIN ?? 'next.localhost'

    const cookieHeader = [
      sessionid ? `sessionid=${sessionid}` : '',
      hmac ? `hmac=${hmac}` : '',
    ]
      .filter(Boolean)
      .join('; ')

    try {
      const res = await fetch(`${authUrl}/logout/`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          Referer: `http://${nextUiDomain}/logout`,
          ...(cookieHeader ? { Cookie: cookieHeader } : {}),
          ...(clientIp ? { 'X-Original-Client-IP': clientIp } : {}),
          ...(userAgent ? { 'User-Agent': userAgent } : {}),
          ...(uaPlatform ? { 'Sec-CH-UA-Platform': uaPlatform } : {}),
        },
      })
      logger.info({ status: res.status }, 'session-auth logout response')
    } catch (err) {
      logger.error({ err }, 'session-auth logout request failed')
    }
  } else {
    logger.error('SESSION_AUTH_URL is not configured')
  }

  redirect('/login')
}
