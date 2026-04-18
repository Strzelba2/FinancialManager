'use server'

import { cookies, headers } from 'next/headers'
import { z } from 'zod'
import { logger } from '@/lib/logger'

const LoginSchema = z.object({
  email: z.email({ error: 'Podaj poprawny adres email' }).trim(),
  password: z.string().min(1, { error: 'Hasło jest wymagane' }),
})

export type LoginState =
  | {
      errors?: {
        email?: string[]
        password?: string[]
      }
      message?: string
      success?: boolean
    }
  | undefined

function extractSessionAuthMessage(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed.length > 0 ? trimmed : undefined
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const message = extractSessionAuthMessage(item)
      if (message) return message
    }
    return undefined
  }

  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>

    for (const key of ['error', 'detail', 'message', 'non_field_errors']) {
      const message = extractSessionAuthMessage(record[key])
      if (message) return message
    }

    for (const nested of Object.values(record)) {
      const message = extractSessionAuthMessage(nested)
      if (message) return message
    }
  }

  return undefined
}

function loginFallbackMessage(status: number): string {
  switch (status) {
    case 401:
      return 'Nieprawidłowy email lub hasło'
    case 429:
      return 'Zbyt wiele prób logowania. Spróbuj ponownie później.'
    case 500:
      return 'Wewnętrzny błąd logowania'
    default:
      return 'Logowanie nieudane'
  }
}

export async function loginAction(
  _prevState: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const validated = LoginSchema.safeParse({
    email: formData.get('email'),
    password: formData.get('password'),
  })

  if (!validated.success) {
    return { errors: validated.error.flatten((issue) => issue.message).fieldErrors }
  }

  const { email, password } = validated.data
  const authUrl = process.env.SESSION_AUTH_URL

  if (!authUrl) {
    logger.error('SESSION_AUTH_URL is not configured')
    return { message: 'Błąd konfiguracji serwera' }
  }

  const reqHeaders = await headers()
  const xForwardedFor = reqHeaders.get('x-forwarded-for') ?? ''
  const clientIp =
    (xForwardedFor.split(',')[0] ?? '').trim() ||
    reqHeaders.get('x-real-ip') ||
    ''
  const userAgent = reqHeaders.get('user-agent') ?? ''
  const uaPlatform = reqHeaders.get('sec-ch-ua-platform') ?? ''

  let response: Response
  try {
    const nextUiDomain = process.env.NEXT_UI_DOMAIN ?? 'next.localhost'
    response = await fetch(`${authUrl}/login/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Referer: `http://${nextUiDomain}/login`,
        ...(clientIp ? { 'X-Original-Client-IP': clientIp } : {}),
        ...(userAgent ? { 'User-Agent': userAgent } : {}),
        ...(uaPlatform ? { 'Sec-CH-UA-Platform': uaPlatform } : {}),
      },
      body: JSON.stringify({ email, password }),
    })
  } catch (err) {
    logger.error({ err }, 'session-auth login request failed')
    return { message: 'Błąd połączenia z serwerem autoryzacji' }
  }

  if (!response.ok) {
    const rawBody = await response.text().catch(() => '')
    let message = loginFallbackMessage(response.status)

    if (rawBody) {
      try {
        const parsed = JSON.parse(rawBody) as unknown
        message = extractSessionAuthMessage(parsed) ?? message
      } catch {
        const plainText = rawBody.trim()
        if (plainText && !plainText.startsWith('<')) {
          message = plainText
        }
      }
    }

    logger.warn({ status: response.status, email, body: rawBody, message }, 'login rejected by session-auth')
    return { message }
  }

  const cookieStore = await cookies()
  const rawSetCookie = response.headers.getSetCookie?.() ?? []

  for (const raw of rawSetCookie) {
    const [nameValue] = raw.split(';')
    const eqIdx = nameValue?.indexOf('=') ?? -1
    if (eqIdx === -1 || !nameValue) continue

    const name = nameValue.slice(0, eqIdx).trim()
    const value = nameValue.slice(eqIdx + 1).trim()

    if (name === 'sessionid' || name === 'hmac_token' || name === 'hmac') {
      cookieStore.set(name === 'hmac_token' ? 'hmac' : name, value, {
        httpOnly: true,
        sameSite: 'lax',
        path: '/',
      })
    }
  }

  logger.info({ email }, 'login successful')
  return { success: true }
}
