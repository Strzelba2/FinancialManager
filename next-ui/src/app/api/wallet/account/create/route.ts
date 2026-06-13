import { z } from 'zod'
import { createAccount } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'
import { logger } from '@/lib/logger'

const Schema = z.object({
  walletId: z.string().uuid(),
  name: z.string().min(1, { message: 'Podaj nazwę konta' }).max(64, { message: 'Maksymalnie 64 znaki' }).trim(),
  account_type: z.enum(['CURRENT', 'SAVINGS', 'BROKERAGE', 'CREDIT']),
  currency: z.enum(['PLN', 'USD', 'EUR']),
  account_number: z.string().min(1, { message: 'Podaj numer konta' }).max(32).trim(),
  bank_id: z.string().uuid({ message: 'Wybierz bank' }),
  brokerage_cash_accounts: z.array(z.object({
    currency: z.enum(['USD', 'EUR']),
    account_number: z.string().min(1).max(32).trim(),
    name: z.string().max(64).trim().optional(),
    iban: z.string().max(34).trim().optional(),
  })).optional(),
})

function derivePolishIban(accountNumber: string): string | undefined {
  const normalized = accountNumber.replace(/\s+/g, '')
  return /^\d{26}$/.test(normalized) ? `PL${normalized}` : undefined
}

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

  const { walletId, name, account_type, currency, account_number, bank_id, brokerage_cash_accounts } = validated.data
  const iban = derivePolishIban(account_number)
  const result = await createAccount(userId, walletId, {
    name,
    account_type,
    currency,
    account_number,
    bank_id,
    ...(iban ? { iban } : {}),
    brokerage_cash_accounts,
  })

  if (!result.ok) {
    logger.warn({ userId, walletId, error: result.error }, 'createAccount route handler failed')
    return Response.json({ error: result.error }, { status: 422 })
  }

  logger.info({ userId, walletId, accountId: result.data.id, name: result.data.name }, 'account created')
  return Response.json({ success: true, accountName: result.data.name })
}
