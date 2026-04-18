'use server'

import { headers } from 'next/headers'
import { z } from 'zod'
import { createWallet } from '@/lib/api/wallet'
import { logger } from '@/lib/logger'

const Schema = z.object({
  name: z.string().min(1, { message: 'Podaj nazwę portfela' }).max(40, { message: 'Maksymalnie 40 znaków' }).trim(),
})

export type CreateWalletState = { error?: string; success?: boolean; walletName?: string } | undefined

export async function createWalletAction(
  _prev: CreateWalletState,
  formData: FormData,
): Promise<CreateWalletState> {
  const validated = Schema.safeParse({ name: formData.get('name') })
  if (!validated.success) {
    return { error: validated.error.issues[0]?.message ?? 'Nieprawidłowa nazwa portfela' }
  }

  const userId = (await headers()).get('x-user-id') ?? ''
  if (!userId) {
    logger.warn('createWalletAction: x-user-id header missing')
    return { error: 'Nie udało się zidentyfikować użytkownika' }
  }

  const result = await createWallet(validated.data.name, userId)
  if (!result) {
    logger.warn({ userId }, 'createWalletAction: createWallet failed')
    return { error: 'Nie udało się utworzyć portfela' }
  }

  logger.info({ userId, walletId: result.id, name: result.name }, 'wallet created')
  return { success: true, walletName: result.name }
}
