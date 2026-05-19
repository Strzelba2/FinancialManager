import Link from 'next/link'
import { LogOut } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { logoutAction } from '@/features/auth/actions/logout'

export default function LogoutPage() {
  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-md items-center px-4">
      <Card className="w-full border-white/10 bg-white/10 text-white shadow-2xl backdrop-blur-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full border border-red-400/30 bg-red-500/20">
            <LogOut className="h-6 w-6 text-red-300" />
          </div>
          <CardTitle className="text-xl text-white">Wylogować z konta?</CardTitle>
          <CardDescription className="text-white/65">
            Sesja zostanie zakończona po potwierdzeniu.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <form action={logoutAction}>
            <Button
              type="submit"
              variant="destructive"
              className="h-9 w-full"
            >
              <LogOut className="h-4 w-4" />
              Wyloguj się
            </Button>
          </form>
          <Button asChild variant="outline" className="h-9 w-full border-white/20 bg-white/10 text-white hover:bg-white/15">
            <Link href="/wallet">Wróć do portfela</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
