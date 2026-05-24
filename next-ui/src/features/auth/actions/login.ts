'use server'

import { headers } from 'next/headers'
import { z } from 'zod'
import { logger } from '@/lib/logger'
import { storeAuthCookiesFromResponse } from './auth-cookies'
import { sessionAuthReferer } from './cookie-options'
import { readSessionAuthMessage } from './session-auth-message'

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
      requiresTwoFactor?: boolean
      success?: boolean
    }
  | undefined

function loginFallbackMessage(status: number): string {
  switch (status) {
    case 403:
      return 'Logowanie zostało zablokowane ze względów bezpieczeństwa.'
    case 401:
      return 'Nieprawidłowy email lub hasło'
    case 409:
      return 'Logowanie jest już aktywne. Odśwież stronę albo spróbuj ponownie za chwilę.'
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
    response = await fetch(`${authUrl}/login/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Referer: sessionAuthReferer('/login'),
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

  if (response.status === 202) {
    let requiresTwoFactor = false
    try {
      const body = await response.json() as { requires_two_factor?: unknown }
      requiresTwoFactor = body.requires_two_factor === true
    } catch {
      requiresTwoFactor = false
    }

    if (!requiresTwoFactor) {
      logger.warn({ status: response.status }, 'login challenge missing 2FA marker')
      return { message: 'Nieprawidłowa odpowiedź serwera autoryzacji' }
    }

    const { missing } = await storeAuthCookiesFromResponse(response, { sessionid: true })
    if (missing.length > 0) {
      logger.warn('2FA login challenge did not include a session cookie')
      return { message: 'Brak danych sesji w odpowiedzi serwera autoryzacji' }
    }

    logger.info('login requires two-factor verification')
    return { requiresTwoFactor: true }
  }

  if (!response.ok) {
    const message = await readSessionAuthMessage(response, loginFallbackMessage(response.status))

    logger.warn({ status: response.status }, 'login rejected by session-auth')
    return { message }
  }

  const { missing } = await storeAuthCookiesFromResponse(response, {
    sessionid: true,
    hmac: true,
  })
  if (missing.length > 0) {
    logger.warn('login succeeded without required auth cookies')
    return { message: 'Brak danych sesji w odpowiedzi serwera autoryzacji' }
  }

  logger.info('login successful')
  return { success: true }
}
