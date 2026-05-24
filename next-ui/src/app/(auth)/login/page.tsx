'use client'

import { useActionState, useEffect } from 'react'
import Link from 'next/link'
import { TrendingUp, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { loginAction } from '@/features/auth/actions/login'

export default function LoginPage() {
  const [state, action, isPending] = useActionState(loginAction, undefined)

  useEffect(() => {
    if (state?.requiresTwoFactor) {
      window.location.href = '/two-factor'
      return
    }

    if (state?.success) {
      window.location.href = '/wallet'
    }
  }, [state])

  return (
    <Card className="w-full max-w-sm backdrop-blur-md bg-white/10 border-white/20 text-white shadow-2xl">
      <CardHeader className="text-center">
        <div className="flex justify-center mb-2">
          <div className="flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/20 border border-emerald-400/30">
            <TrendingUp className="w-6 h-6 text-emerald-400" />
          </div>
        </div>
        <CardTitle className="text-2xl text-white">FinancialManager</CardTitle>
        <CardDescription className="text-white/60">Zaloguj się do swojego konta</CardDescription>
      </CardHeader>

      <CardContent>
        <form action={action} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email" className="text-white/80">Email</Label>
            <Input
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50"
              id="email"
              name="email"
              type="email"
              placeholder="jan@example.com"
              autoComplete="email"
            />
            {state?.errors?.email && (
              <p className="text-sm text-destructive">{state.errors.email[0]}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password" className="text-white/80">Hasło</Label>
            <Input
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50"
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
            />
            {state?.errors?.password && (
              <p className="text-sm text-destructive">{state.errors.password[0]}</p>
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
                Logowanie…
              </>
            ) : (
              'Zaloguj się'
            )}
          </Button>
        </form>

        <p className="text-center text-sm text-white/50 mt-4">
          Nie masz konta?{' '}
          <Link href="/register" className="text-emerald-400 hover:text-emerald-300 hover:underline">
            Zarejestruj się
          </Link>
        </p>
      </CardContent>
    </Card>
  )
}
