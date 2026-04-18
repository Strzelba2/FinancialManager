'use server'

import { redirect } from 'next/navigation'
import { z } from 'zod'
import { logger } from '@/lib/logger'

const RegisterSchema = z.object({
  first_name: z.string().min(1, { error: 'Imię jest wymagane' }).trim(),
  last_name: z.string().min(1, { error: 'Nazwisko jest wymagane' }).trim(),
  username: z.string().min(3, { error: 'Nazwa użytkownika musi mieć min. 3 znaki' }).trim(),
  email: z.email({ error: 'Podaj poprawny adres email' }).trim(),
  password: z.string().min(8, { error: 'Hasło musi mieć min. 8 znaków' }),
})

export type RegisterState =
  | {
      errors?: {
        first_name?: string[]
        last_name?: string[]
        username?: string[]
        email?: string[]
        password?: string[]
      }
      message?: string
    }
  | undefined

export async function registerAction(
  _prevState: RegisterState,
  formData: FormData,
): Promise<RegisterState> {
  const validated = RegisterSchema.safeParse({
    first_name: formData.get('first_name'),
    last_name: formData.get('last_name'),
    username: formData.get('username'),
    email: formData.get('email'),
    password: formData.get('password'),
  })

  if (!validated.success) {
    return { errors: validated.error.flatten((issue) => issue.message).fieldErrors }
  }

  const authUrl = process.env.SESSION_AUTH_URL
  if (!authUrl) {
    logger.error('SESSION_AUTH_URL is not configured')
    return { message: 'Błąd konfiguracji serwera' }
  }

  let response: Response
  try {
    const nextUiDomain = process.env.NEXT_UI_DOMAIN ?? 'next.localhost'
    response = await fetch(`${authUrl}/register/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Referer: `http://${nextUiDomain}/register`,
      },
      body: JSON.stringify(validated.data),
    })
  } catch (err) {
    logger.error({ err }, 'session-auth register request failed')
    return { message: 'Błąd połączenia z serwerem' }
  }

  if (response.status !== 201) {
    logger.warn({ status: response.status }, 'registration rejected by session-auth')
    const body = await response.json().catch(() => ({}))
    const detail = typeof body?.detail === 'string' ? body.detail : 'Rejestracja nieudana'
    return { message: detail }
  }

  logger.info({ email: validated.data.email }, 'registration successful')

  redirect('/login')
}
