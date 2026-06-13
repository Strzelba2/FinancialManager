'use client'

import { useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Landmark } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { logger } from '@/lib/logger'

const ACCOUNT_TYPES = [
  { value: 'CURRENT', label: 'Konto bankowe' },
  { value: 'SAVINGS', label: 'Konto oszczędnościowe' },
  { value: 'BROKERAGE', label: 'Konto maklerskie' },
  { value: 'CREDIT', label: 'Karta kredytowa' },
]

const CURRENCIES = [
  { value: 'PLN', label: 'PLN' },
  { value: 'USD', label: 'USD' },
  { value: 'EUR', label: 'EUR' },
]

interface Bank {
  id: string
  name: string
  shortname: string
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  wallets: { id: string; name: string }[]
  banks: Bank[]
}

export function CreateAccountDialog({ open, onOpenChange, wallets, banks }: Props) {
  const router = useRouter()
  const formRef = useRef<HTMLFormElement>(null)
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string>()

  const [selectedWalletId, setSelectedWalletId] = useState<string>(wallets[0]?.id ?? '')
  const [accountType, setAccountType] = useState('CURRENT')
  const [currency, setCurrency] = useState('PLN')
  const [bankId, setBankId] = useState<string>('')
  const walletId = wallets.some((wallet) => wallet.id === selectedWalletId)
    ? selectedWalletId
    : (wallets[0]?.id ?? '')

  function handleAccountTypeChange(value: string) {
    setAccountType(value)
    if (value === 'BROKERAGE') setCurrency('PLN')
  }

  function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const name = (fd.get('name') as string | null)?.trim() ?? ''
    const account_number = (fd.get('account_number') as string | null)?.trim() ?? ''
    const usdAccountNumber = (fd.get('brokerage_usd_account_number') as string | null)?.trim() ?? ''
    const eurAccountNumber = (fd.get('brokerage_eur_account_number') as string | null)?.trim() ?? ''

    if (!name) { setError('Podaj nazwę konta'); return }
    if (!account_number) { setError('Podaj numer konta'); return }
    if (!walletId) { setError('Wybierz portfel'); return }
    if (!bankId) { setError('Wybierz bank'); return }
    setError(undefined)

    startTransition(async () => {
      const brokerage_cash_accounts =
        accountType === 'BROKERAGE'
          ? [
              usdAccountNumber ? { currency: 'USD', account_number: usdAccountNumber, name: `${name} · USD` } : null,
              eurAccountNumber ? { currency: 'EUR', account_number: eurAccountNumber, name: `${name} · EUR` } : null,
            ].filter(Boolean)
          : undefined

      const res = await fetch('/api/wallet/account/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          walletId,
          name,
          account_type: accountType,
          currency: accountType === 'BROKERAGE' ? 'PLN' : currency,
          account_number,
          bank_id: bankId,
          brokerage_cash_accounts,
        }),
      })
      let data: { error?: string; success?: boolean; accountName?: string } = {}
      try {
        data = await res.json()
        logger.info({ data: data }, 'create account response')
      } catch {
        setError('Nie udało się odczytać odpowiedzi serwera')
        return
      }

      if (!res.ok || data.error) {
        setError(data.error || 'Nie udało się utworzyć konta')
        return
      }

      toast.success(`Konto „${data.accountName}" zostało dodane`)
      onOpenChange(false)
      formRef.current?.reset()
      setAccountType('CURRENT')
      setCurrency('PLN')
      setBankId('')
      router.refresh()
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-emerald-950/95 backdrop-blur-md border-emerald-800/50 text-white max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="p-2.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
              <Landmark className="w-5 h-5 text-emerald-400" />
            </div>
            <DialogTitle className="text-white text-lg">Dodaj konto do portfela</DialogTitle>
          </div>
          <DialogDescription className="text-white/50 text-sm">
            Wypełnij wymagane pola, reszta jest opcjonalna.
          </DialogDescription>
        </DialogHeader>

        <form ref={formRef} onSubmit={handleSubmit} className="space-y-3 mt-2">

          <div className="space-y-1.5">
            <Label htmlFor="acc-name" className="text-white/70 text-sm">Nazwa konta *</Label>
            <Input
              id="acc-name"
              name="name"
              placeholder="np. mBank – ROR"
              maxLength={64}
              autoFocus
              className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:ring-emerald-500/50"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">Typ *</Label>
              <Select value={accountType} onValueChange={handleAccountTypeChange}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-emerald-950 border-emerald-800/50 text-white">
                  {ACCOUNT_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">Waluta *</Label>
              <Select value={currency} onValueChange={setCurrency} disabled={accountType === 'BROKERAGE'}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-emerald-950 border-emerald-800/50 text-white">
                  {CURRENCIES.map(c => (
                    <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5 min-w-0">
              <Label className="text-white/70 text-sm">Portfel *</Label>
              <Select value={walletId} onValueChange={setSelectedWalletId} disabled={wallets.length === 0}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white">
                  <SelectValue placeholder={wallets.length === 0 ? 'Brak portfeli' : 'Wybierz portfel'} />
                </SelectTrigger>
                <SelectContent className="bg-emerald-950 border-emerald-800/50 text-white">
                  {wallets.map((wallet) => (
                    <SelectItem key={wallet.id} value={wallet.id}>{wallet.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {wallets.length === 0 && (
                <p className="text-white/45 text-xs">Najpierw dodaj portfel, a potem konto.</p>
              )}
            </div>

            <div className="space-y-1.5 min-w-0">
              <Label className="text-white/70 text-sm">Bank *</Label>
              <Select value={bankId} onValueChange={setBankId}>
                <SelectTrigger className="bg-white/5 border-white/10 text-white">
                  <SelectValue placeholder="Wybierz bank" />
                </SelectTrigger>
                <SelectContent className="bg-emerald-950 border-emerald-800/50 text-white">
                  {banks.map(b => (
                    <SelectItem key={b.id} value={b.id}>{b.shortname}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="acc-number" className="text-white/70 text-sm">Numer konta *</Label>
            <Input
              id="acc-number"
              name="account_number"
              placeholder="np. 12345678901234567890123456"
              maxLength={32}
              className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:ring-emerald-500/50"
            />
          </div>

          {accountType === 'BROKERAGE' && (
            <div className="space-y-2 rounded-md border border-white/10 bg-white/[0.03] p-3">
              <p className="text-white/65 text-sm">
                PLN jest głównym subkontem gotówkowym. USD/EUR dodaj opcjonalnie, wpisując numer albo techniczny identyfikator.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="brokerage-usd-number" className="text-white/70 text-sm">Subkonto USD</Label>
                  <Input
                    id="brokerage-usd-number"
                    name="brokerage_usd_account_number"
                    placeholder="np. BOSSA-IKE-USD"
                    maxLength={32}
                    className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:ring-emerald-500/50"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="brokerage-eur-number" className="text-white/70 text-sm">Subkonto EUR</Label>
                  <Input
                    id="brokerage-eur-number"
                    name="brokerage_eur_account_number"
                    placeholder="np. BOSSA-IKE-EUR"
                    maxLength={32}
                    className="bg-white/5 border-white/10 text-white placeholder:text-white/30 focus-visible:ring-emerald-500/50"
                  />
                </div>
              </div>
            </div>
          )}

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              className="text-white/60 hover:text-white hover:bg-white/10"
            >
              Anuluj
            </Button>
            <Button
              type="submit"
              disabled={isPending || wallets.length === 0}
              className="bg-emerald-600 hover:bg-emerald-500 text-white"
            >
              {isPending ? 'Dodawanie…' : 'Dodaj konto'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
