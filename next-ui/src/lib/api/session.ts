import { headers, cookies } from 'next/headers'
import { syncUser } from '@/lib/api/wallet'
import { logger } from '@/lib/logger'

const SESSION_AUTH_URL = process.env.SESSION_AUTH_URL ?? ''

export async function saveWalletUserId(userId: string): Promise<void> {
  if (!SESSION_AUTH_URL || !userId) return

  const cookieStore = await cookies()
  const sessionId = cookieStore.get('sessionid')?.value ?? ''
  const hmac = cookieStore.get('hmac')?.value ?? ''

  if (!sessionId) return

  try {
    const res = await fetch(`${SESSION_AUTH_URL}/wallet-user-id/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': `sessionid=${sessionId}; hmac=${hmac}`,
      },
      body: JSON.stringify({ wallet_user_id: userId }),
      cache: 'no-store',
    })
    if (!res.ok) {
      logger.warn({ status: res.status }, 'saveWalletUserId: session-auth responded with error')
    }
  } catch (err) {
    logger.warn({ err }, 'saveWalletUserId: request failed')
  }
}

export async function resolveWalletUserId(): Promise<string> {
  const headerStore = await headers()
  const existingUserId = headerStore.get('x-user-id') ?? ''
  if (existingUserId) return existingUserId

  const username = headerStore.get('x-user') ?? ''
  if (!username) {
    logger.warn('resolveWalletUserId: x-user header missing')
    return ''
  }

  const first_name = headerStore.get('x-first-name') ?? ''
  const email = headerStore.get('x-email') ?? ''
  const data = await syncUser({ username, first_name, email })

  if (!data?.user_id) {
    logger.warn({ username }, 'resolveWalletUserId: syncUser failed')
    return ''
  }

  await saveWalletUserId(data.user_id)
  return data.user_id
}
