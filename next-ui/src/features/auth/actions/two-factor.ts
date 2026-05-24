'use server'

import { cookies, headers } from 'next/headers'
import { z } from 'zod'
import { logger } from '@/lib/logger'
import { storeAuthCookiesFromResponse } from './auth-cookies'
import { sessionAuthReferer } from './cookie-options'
import { readSessionAuthMessage } from './session-auth-message'

const TokenSchema = z.object({
  token: z.string()
    .trim()
    .regex(/^\d{6}$/, { message: 'Podaj 6-cyfrowy kod' }),
})

export type TwoFactorVerifyState =
  | {
      errors?: {
        token?: string[]
      }
      message?: string
      success?: boolean
    }
  | undefined

export type TwoFactorSetupState =
  | {
      image?: string
      message?: string
      success?: boolean
    }
  | undefined

export type TwoFactorTokenState =
  | {
      errors?: {
        token?: string[]
      }
      message?: string
      success?: boolean
    }
  | undefined

export interface TwoFactorStatus {
  isTwoFactorEnabled: boolean
  message?: string
}

function twoFactorFallbackMessage(status: number): string {
  switch (status) {
    case 400:
      return 'Podaj poprawny kod 2FA'
    case 401:
      return 'Nieprawidłowy kod 2FA'
    case 403:
      return 'Najpierw potwierdź logowanie 2FA'
    case 429:
      return 'Zbyt wiele prób 2FA. Zaloguj się ponownie.'
    default:
      return 'Operacja 2FA nie powiodła się'
  }
}

async function sessionAuthHeaders(path: string, includeJson = true): Promise<HeadersInit | undefined> {
  const authUrl = process.env.SESSION_AUTH_URL
  if (!authUrl) return undefined

  const cookieStore = await cookies()
  const sessionid = cookieStore.get('sessionid')?.value
  const hmac = cookieStore.get('hmac')?.value

  if (!sessionid) return undefined

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

  return {
    Accept: 'application/json',
    ...(includeJson ? { 'Content-Type': 'application/json' } : {}),
    Referer: sessionAuthReferer(path),
    Cookie: cookieHeader,
    ...(clientIp ? { 'X-Original-Client-IP': clientIp } : {}),
    ...(userAgent ? { 'User-Agent': userAgent } : {}),
    ...(uaPlatform ? { 'Sec-CH-UA-Platform': uaPlatform } : {}),
  }
}

async function sessionAuthFetch(
  path: string,
  init: Omit<RequestInit, 'headers'> & { includeJson?: boolean } = {},
): Promise<Response | undefined> {
  const authUrl = process.env.SESSION_AUTH_URL
  if (!authUrl) {
    logger.error('SESSION_AUTH_URL is not configured')
    return undefined
  }

  const { includeJson, ...requestInit } = init
  const requestHeaders = await sessionAuthHeaders(path, includeJson ?? true)
  if (!requestHeaders) {
    logger.warn('2FA action called without a session cookie')
    return undefined
  }

  return fetch(`${authUrl}${path}`, {
    ...requestInit,
    headers: requestHeaders,
    cache: 'no-store',
  })
}

export async function verifyTwoFactorAction(
  _prevState: TwoFactorVerifyState,
  formData: FormData,
): Promise<TwoFactorVerifyState> {
  const validated = TokenSchema.safeParse({
    token: formData.get('token'),
  })

  if (!validated.success) {
    return { errors: validated.error.flatten((issue) => issue.message).fieldErrors }
  }

  let response: Response | undefined
  try {
    response = await sessionAuthFetch('/two-factor/verify/', {
      method: 'POST',
      body: JSON.stringify({ token: validated.data.token }),
    })
  } catch (err) {
    logger.error({ err }, 'session-auth 2FA verify request failed')
    return { message: 'Błąd połączenia z serwerem autoryzacji' }
  }

  if (!response) {
    return { message: 'Sesja wygasła. Zaloguj się ponownie.' }
  }

  if (!response.ok) {
    const message = await readSessionAuthMessage(response, twoFactorFallbackMessage(response.status))
    logger.warn({ status: response.status }, '2FA verification rejected by session-auth')
    return { message }
  }

  const { missing } = await storeAuthCookiesFromResponse(response, { hmac: true })
  if (missing.length > 0) {
    logger.warn('2FA verification succeeded without an HMAC cookie')
    return { message: 'Brak danych sesji w odpowiedzi serwera autoryzacji' }
  }

  logger.info('2FA verification successful')
  return { success: true }
}

export async function getTwoFactorStatus(): Promise<TwoFactorStatus> {
  let response: Response | undefined
  try {
    response = await sessionAuthFetch('/two-factor/status/', {
      method: 'GET',
      includeJson: false,
    })
  } catch (err) {
    logger.warn({ err }, 'session-auth 2FA status request failed')
    return { isTwoFactorEnabled: false, message: 'Nie udało się pobrać statusu 2FA' }
  }

  if (!response?.ok) {
    return { isTwoFactorEnabled: false, message: 'Nie udało się pobrać statusu 2FA' }
  }

  const body = await response.json().catch(() => ({})) as { is_two_factor_enabled?: unknown }
  return { isTwoFactorEnabled: body.is_two_factor_enabled === true }
}

export async function setupTwoFactorAction(
  _prevState: TwoFactorSetupState,
  _formData: FormData,
): Promise<TwoFactorSetupState> {
  void _prevState
  void _formData

  let response: Response | undefined
  try {
    response = await sessionAuthFetch('/two-factor/setup/', {
      method: 'POST',
      body: JSON.stringify({}),
    })
  } catch (err) {
    logger.error({ err }, 'session-auth 2FA setup request failed')
    return { message: 'Błąd połączenia z serwerem autoryzacji' }
  }

  if (!response) {
    return { message: 'Sesja wygasła. Zaloguj się ponownie.' }
  }

  if (!response.ok) {
    const message = await readSessionAuthMessage(response, twoFactorFallbackMessage(response.status))
    logger.warn({ status: response.status }, '2FA setup rejected by session-auth')
    return { message }
  }

  const body = await response.json().catch(() => ({})) as { image?: unknown }
  if (typeof body.image !== 'string' || body.image.length === 0) {
    return { message: 'Serwer nie zwrócił kodu QR' }
  }

  return { image: body.image, success: true }
}

export async function enableTwoFactorAction(
  _prevState: TwoFactorTokenState,
  formData: FormData,
): Promise<TwoFactorTokenState> {
  return changeTwoFactorState('/two-factor/enable/', formData, '2FA zostało włączone')
}

export async function disableTwoFactorAction(
  _prevState: TwoFactorTokenState,
  formData: FormData,
): Promise<TwoFactorTokenState> {
  return changeTwoFactorState('/two-factor/disable/', formData, '2FA zostało wyłączone')
}

async function changeTwoFactorState(
  path: '/two-factor/enable/' | '/two-factor/disable/',
  formData: FormData,
  successMessage: string,
): Promise<TwoFactorTokenState> {
  const validated = TokenSchema.safeParse({
    token: formData.get('token'),
  })

  if (!validated.success) {
    return { errors: validated.error.flatten((issue) => issue.message).fieldErrors }
  }

  let response: Response | undefined
  try {
    response = await sessionAuthFetch(path, {
      method: 'POST',
      body: JSON.stringify({ token: validated.data.token }),
    })
  } catch (err) {
    logger.error({ err }, 'session-auth 2FA state request failed')
    return { message: 'Błąd połączenia z serwerem autoryzacji' }
  }

  if (!response) {
    return { message: 'Sesja wygasła. Zaloguj się ponownie.' }
  }

  if (!response.ok) {
    const message = await readSessionAuthMessage(response, twoFactorFallbackMessage(response.status))
    logger.warn({ status: response.status }, '2FA state change rejected by session-auth')
    return { message }
  }

  logger.info({ path }, '2FA state change successful')
  return { success: true, message: successMessage }
}
