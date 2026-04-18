import { z } from 'zod'
import { deleteWallet } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'
import { logger } from '@/lib/logger'

const Schema = z.object({
  walletIds: z.array(z.string().uuid()).min(1, { message: 'Wybierz co najmniej jeden portfel' }),
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
    return Response.json(
      { error: validated.error.issues[0]?.message ?? 'Nieprawidłowe dane' },
      { status: 422 },
    )
  }

  const { walletIds } = validated.data
  const failed: string[] = []

  for (const walletId of walletIds) {
    const ok = await deleteWallet(userId, walletId)
    if (!ok) failed.push(walletId)
  }

  if (failed.length > 0) {
    logger.warn({ userId, failed }, 'deleteWallet: some wallets failed to delete')
    if (failed.length === walletIds.length) {
      return Response.json({ error: 'Nie udało się usunąć portfeli' }, { status: 500 })
    }
    return Response.json({ success: true, partial: true, failed })
  }

  logger.info({ userId, walletIds }, 'wallets deleted')
  return Response.json({ success: true })
}
