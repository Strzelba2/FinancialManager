'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { TrendingUp, Bell, LogOut, User, Settings, ChevronDown, Menu, PlusCircle, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet'

interface Props {
  username: string
}

// Nav link with active highlight based on current path
function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname()
  const active = pathname.startsWith(href)
  return (
    <Link
      href={href}
      className={`text-sm transition-colors ${active ? 'text-white' : 'text-white/60 hover:text-white'}`}
    >
      {label}
    </Link>
  )
}

// Reusable dropdown trigger button used in the navbar menus
function NavDropdown({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="text-white/60 hover:text-white hover:bg-white/10 gap-1 px-2">
          {label}
          <ChevronDown className="w-3.5 h-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="bg-emerald-900/95 backdrop-blur-sm border-emerald-800/50 text-white min-w-48">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// Single item inside a dropdown — styled for dark nav
function NavItem({ href, label }: { href: string; label: string }) {
  return (
    <DropdownMenuItem asChild>
      <Link href={href} className="cursor-pointer text-white/70 hover:text-white focus:text-white focus:bg-emerald-900/30">
        {label}
      </Link>
    </DropdownMenuItem>
  )
}

export function DashboardNav({ username }: Props) {
  const router = useRouter()

  return (
    <nav className="sticky top-0 z-50 backdrop-blur-md bg-white/5 border-b border-white/10">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between gap-4">

        {/* ── Left: logo + navigation ── */}
        <div className="flex items-center gap-1">
          <Link href="/wallet" className="flex items-center gap-2 text-white font-semibold text-lg mr-6">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            <span className="hidden sm:inline">FinancialManager</span>
          </Link>

          {/* Desktop nav — hidden on mobile */}
          <div className="hidden md:flex items-center gap-2">
            <NavLink href="/wallet" label="Portfolio" />

            <NavDropdown label="Portfel">
              <DropdownMenuItem
                onSelect={() => router.push('/wallet?modal=create')}
                className="cursor-pointer text-white/70 hover:text-white focus:text-white focus:bg-emerald-900/30 gap-2"
              >
                <PlusCircle className="w-4 h-4 text-emerald-400" />
                Dodaj portfel…
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => router.push('/wallet?modal=delete')}
                className="cursor-pointer text-white/70 hover:text-white focus:text-white focus:bg-red-900/30 gap-2"
              >
                <Trash2 className="w-4 h-4 text-red-400" />
                Usuń portfel…
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-white/10" />
              <DropdownMenuItem
                onSelect={() => router.push('/wallet?modal=create-account')}
                className="cursor-pointer text-white/70 hover:text-white focus:text-white focus:bg-emerald-900/30 gap-2"
              >
                <PlusCircle className="w-4 h-4 text-emerald-400" />
                Dodaj konto…
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-white/10" />
              <NavItem href="/wallet-manager" label="Zarządzaj portfelami" />
            </NavDropdown>

            <NavLink href="/transactions" label="Transakcje" />

            <NavDropdown label="Makler">
              <NavItem href="/stock/quotes/XWAR" label="Notowania" />
              <DropdownMenuSeparator className="bg-white/10" />
              <NavItem href="/stock/charts/XWAR" label="Wykresy" />
              <DropdownMenuSeparator className="bg-white/10" />
              <NavItem href="/brokerage/events" label="Operacje" />
              <DropdownMenuSeparator className="bg-white/10" />
              <NavItem href="/brokerage/holdings" label="Pozycje" />
              <DropdownMenuSeparator className="bg-white/10" />
              <NavItem href="/user/favorites" label="Ulubione" />
            </NavDropdown>
          </div>
        </div>

        {/* ── Right: alerts + user menu ── */}
        <div className="flex items-center gap-1">

          {/* Alerts bell — TODO: connect to wallet API + React Query when wallet client is built */}
          <Button variant="ghost" size="icon" className="text-white/60 hover:text-white hover:bg-white/10 relative">
            <Bell className="w-5 h-5" />
          </Button>

          {/* User dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="text-white/60 hover:text-white hover:bg-white/10 gap-2 hidden md:flex">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-sm">{username || 'User'}</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="bg-emerald-900/95 backdrop-blur-sm border-emerald-800/50 text-white min-w-44">
              <DropdownMenuItem asChild>
                <Link href="/settings/profile" className="cursor-pointer text-white/70 hover:text-white focus:text-white focus:bg-emerald-900/30 gap-2">
                  <User className="w-4 h-4" /> Profile
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/settings/preferences" className="cursor-pointer text-white/70 hover:text-white focus:text-white focus:bg-emerald-900/30 gap-2">
                  <Settings className="w-4 h-4" /> Preferences
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-white/10" />
              <DropdownMenuItem asChild>
                <Link href="/logout" className="cursor-pointer text-red-400 hover:text-red-300 focus:text-red-300 focus:bg-white/10 gap-2">
                  <LogOut className="w-4 h-4" /> Logout
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Mobile hamburger — shows full nav in a Sheet */}
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden text-white/60 hover:text-white hover:bg-white/10">
                <Menu className="w-5 h-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="bg-slate-900 border-white/10 text-white w-64 p-6">
              <div className="flex flex-col gap-4 mt-4 text-sm">
                <Link href="/wallet" className="text-white/70 hover:text-white">Portfolio</Link>
                <Link href="/transactions" className="text-white/70 hover:text-white">Transakcje</Link>
                <Link href="/stock/quotes/XWAR" className="text-white/70 hover:text-white">Notowania</Link>
                <Link href="/stock/charts/XWAR" className="text-white/70 hover:text-white">Wykresy</Link>
                <Link href="/brokerage/events" className="text-white/70 hover:text-white">Operacje</Link>
                <Link href="/brokerage/holdings" className="text-white/70 hover:text-white">Pozycje</Link>
                <Link href="/user/favorites" className="text-white/70 hover:text-white">Ulubione</Link>
                <div className="border-t border-white/10 pt-4">
                  <Link href="/settings/profile" className="block text-white/70 hover:text-white">Profile</Link>
                </div>
                <div className="border-t border-white/10 pt-4">
                  <Link href="/logout" className="text-red-400 hover:text-red-300">Logout</Link>
                </div>
              </div>
            </SheetContent>
          </Sheet>

        </div>
      </div>
    </nav>
  )
}
