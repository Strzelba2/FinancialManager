import { z } from 'zod'
import { createWallet } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'
import { logger } from '@/lib/logger'

const Schema = z.object({
  name: z.string().min(1, { message: 'Podaj nazwę portfela' }).max(40, { message: 'Maksymalnie 40 znaków' }).trim(),
})

export async function POST(request: Request) {
  const userId = await resolveWalletUserId()
  if (!userId) {
    return Response.json({ error: 'Nie udało się zidentyfikować użytkownika' }, { status: 401 })
  }

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'Nieprawidłowe żądanie' }, { status: 400 })
  }

  const validated = Schema.safeParse(body)
  if (!validated.success) {
    return Response.json({ error: validated.error.issues[0]?.message ?? 'Nieprawidłowa nazwa' }, { status: 422 })
  }

  const result = await createWallet(validated.data.name, userId)
  if (!result) {
    logger.warn({ userId }, 'createWallet route handler failed')
    return Response.json({ error: 'Nie udało się utworzyć portfela' }, { status: 500 })
  }

  logger.info({ userId, walletId: result.id, name: result.name }, 'wallet created')
  return Response.json({ success: true, walletName: result.name })
}
