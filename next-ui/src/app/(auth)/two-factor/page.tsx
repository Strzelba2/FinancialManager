'use client'

import { useActionState, useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { verifyTwoFactorAction } from '@/features/auth/actions/two-factor'

export default function TwoFactorPage() {
  const [state, action, isPending] = useActionState(verifyTwoFactorAction, undefined)
  const [token, setToken] = useState('')

  useEffect(() => {
    if (state?.success) {
      window.location.href = '/wallet'
    }
  }, [state])

  return (
    <Card className="w-full max-w-sm backdrop-blur-md bg-white/10 border-white/20 text-white shadow-2xl">
      <CardHeader className="text-center">
        <div className="flex justify-center mb-2">
          <div className="flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/20 border border-emerald-400/30">
            <ShieldCheck className="w-6 h-6 text-emerald-400" />
          </div>
        </div>
        <CardTitle className="text-2xl text-white">Weryfikacja 2FA</CardTitle>
        <CardDescription className="text-white/60">Potwierdź logowanie kodem jednorazowym</CardDescription>
      </CardHeader>

      <CardContent>
        <form action={action} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="token" className="text-white/80">Kod 2FA</Label>
            <Input
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50 text-center tracking-[0.3em]"
              id="token"
              name="token"
              inputMode="numeric"
              maxLength={6}
              pattern="[0-9]*"
              autoComplete="one-time-code"
              placeholder="000000"
              value={token}
              onChange={(event) => setToken(event.target.value.replace(/\D/g, '').slice(0, 6))}
            />
            {state?.errors?.token && (
              <p className="text-sm text-destructive">{state.errors.token[0]}</p>
            )}
          </div>

          {state?.message && (
            <p className="text-sm text-destructive text-center">{state.message}</p>
          )}

          <Button
            type="submit"
            className="w-full bg-emerald-500 hover:bg-emerald-400 text-white"
            disabled={isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Sprawdzanie…
              </>
            ) : (
              'Potwierdź kod'
            )}
          </Button>
        </form>

        <p className="text-center text-sm text-white/50 mt-4">
          Nie możesz potwierdzić?{' '}
          <Link href="/logout" className="text-emerald-400 hover:text-emerald-300 hover:underline">
            Wróć do logowania
          </Link>
        </p>
      </CardContent>
    </Card>
  )
}
