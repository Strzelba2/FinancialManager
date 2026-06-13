import { NextResponse } from 'next/server'
import { deleteBrokerageAccount } from '@/lib/api/wallet'
import { resolveWalletUserId } from '@/lib/api/session'

type Context = {
  params: Promise<{ id: string }>
}

export async function DELETE(_req: Request, context: Context) {
  const userId = await resolveWalletUserId()
  if (!userId) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })

  const { id } = await context.params
  if (!id) return NextResponse.json({ error: 'Missing brokerage account id' }, { status: 400 })

  const ok = await deleteBrokerageAccount(userId, id)
  if (!ok) return NextResponse.json({ error: 'Nie udało się usunąć rachunku maklerskiego' }, { status: 400 })
  return NextResponse.json({ ok: true })
}
