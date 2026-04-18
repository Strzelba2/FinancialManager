// Minimal layout for login/register — no navbar, centered content
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen flex items-center justify-center px-4
    bg-gradient-to-br from-slate-900 via-emerald-950 to-slate-900">
    {children}
  </main>

  )
}
