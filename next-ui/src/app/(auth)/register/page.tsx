'use client'

import { useActionState, useState } from 'react'
import Link from 'next/link'
import { UserPlus, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { registerAction } from '@/features/auth/actions/register'

export default function RegisterPage() {
  const [state, action, isPending] = useActionState(registerAction, undefined)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  return (
    <Card className="w-full max-w-sm backdrop-blur-md bg-white/10 border-white/20 text-white shadow-2xl">
      <CardHeader className="text-center">
        <div className="flex justify-center mb-2">
          <div className="flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/20 border border-emerald-400/30">
            <UserPlus className="w-6 h-6 text-emerald-400" />
          </div>
        </div>
        <CardTitle className="text-2xl text-white">Rejestracja</CardTitle>
        <CardDescription className="text-white/60">Utwórz nowe konto</CardDescription>
      </CardHeader>

      <CardContent>
        <form action={action} className="space-y-3">

          <div className="space-y-3">
            <Label htmlFor="first_name" className="text-white/80">Imię</Label>
            <Input
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50"
              id="first_name"
              name="first_name"
              placeholder="Jan"
              autoComplete="given-name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
            />
            {state?.errors?.first_name && (
              <p className="text-sm text-red-400">{state.errors.first_name[0]}</p>
            )}
          </div>

          <div className="space-y-3">
            <Label htmlFor="last_name" className="text-white/80">Nazwisko</Label>
            <Input
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50"
              id="last_name"
              name="last_name"
              placeholder="Kowalski"
              autoComplete="family-name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
            />
            {state?.errors?.last_name && (
              <p className="text-sm text-red-400">{state.errors.last_name[0]}</p>
            )}
          </div>

          <div className="space-y-3">
            <Label htmlFor="username" className="text-white/80">Nazwa użytkownika</Label>
            <Input
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50"
              id="username"
              name="username"
              placeholder="jankowalski"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            {state?.errors?.username && (
              <p className="text-sm text-red-400">{state.errors.username[0]}</p>
            )}
          </div>

          <div className="space-y-3">
            <Label htmlFor="email" className="text-white/80">Email</Label>
            <Input
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50"
              id="email"
              name="email"
              type="email"
              placeholder="jan@example.com"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            {state?.errors?.email && (
              <p className="text-sm text-red-400">{state.errors.email[0]}</p>
            )}
          </div>

          <div className="space-y-3">
            <Label htmlFor="password" className="text-white/80">Hasło</Label>
            <Input
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50"
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {state?.errors?.password && (
              <p className="text-sm text-red-400">{state.errors.password[0]}</p>
            )}
          </div>

          {state?.message && (
            <p className="text-sm text-red-400 text-center">{state.message}</p>
          )}

          <Button
            type="submit"
            className="w-full bg-emerald-500 hover:bg-emerald-400 text-white"
            disabled={isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Rejestracja…
              </>
            ) : (
              'Zarejestruj się'
            )}
          </Button>
        </form>

        <p className="text-center text-sm text-white/50 mt-4">
          Masz już konto?{' '}
          <Link href="/login" className="text-emerald-400 hover:text-emerald-300 hover:underline">
            Zaloguj się
          </Link>
        </p>
      </CardContent>
    </Card>
  )
}
