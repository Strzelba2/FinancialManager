import { cookies } from 'next/headers'
import { shouldUseSecureAuthCookies } from './cookie-options'

export type AuthCookieName = 'sessionid' | 'hmac'

export interface StoreAuthCookiesResult {
  stored: Set<AuthCookieName>
  missing: AuthCookieName[]
}

export function extractAuthCookies(response: Response): Array<{ name: AuthCookieName; value: string }> {
  const rawSetCookie = response.headers.getSetCookie?.() ?? []
  const authCookies: Array<{ name: AuthCookieName; value: string }> = []

  for (const raw of rawSetCookie) {
    const [nameValue] = raw.split(';')
    const eqIdx = nameValue?.indexOf('=') ?? -1
    if (eqIdx === -1 || !nameValue) continue

    const name = nameValue.slice(0, eqIdx).trim()
    const value = nameValue.slice(eqIdx + 1).trim()

    if (name === 'sessionid' || name === 'hmac_token' || name === 'hmac') {
      authCookies.push({ name: name === 'sessionid' ? 'sessionid' : 'hmac', value })
    }
  }

  return authCookies
}

export async function storeAuthCookiesFromResponse(
  response: Response,
  required: Partial<Record<AuthCookieName, boolean>>,
): Promise<StoreAuthCookiesResult> {
  const cookieStore = await cookies()
  const secure = shouldUseSecureAuthCookies()
  const stored = new Set<AuthCookieName>()

  for (const cookie of extractAuthCookies(response)) {
    cookieStore.set(cookie.name, cookie.value, {
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      secure,
    })
    stored.add(cookie.name)
  }

  const missing = (Object.keys(required) as AuthCookieName[]).filter((name) => (
    Boolean(required[name]) && !stored.has(name)
  ))

  return { stored, missing }
}
