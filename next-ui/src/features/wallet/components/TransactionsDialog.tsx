'use client'

import { useEffect, useMemo, useState, useTransition } from 'react'
import { Landmark, LoaderCircle, Save, Upload, WalletCards } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DateTimePicker } from '@/components/ui/date-time-picker'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export type TransactionAccountOpt = {
  id: string
  name: string
  walletName: string
  currency: 'PLN' | 'USD' | 'EUR'
  available?: string | null
  lastTransactionAt?: string | null
  lastBalanceAfter?: string | null
}

export type TransactionBrokerageAccountOpt = {
  id: string
  name: string
  walletName: string
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  accounts: TransactionAccountOpt[]
  brokerageAccounts: TransactionBrokerageAccountOpt[]
  initialTab?: ActiveTab
}

type ActiveTab = 'manual' | 'import' | 'brokerage'

type CapitalGainKind =
  | 'TRANSACTION'
  | 'DEPOSIT_INTEREST'
  | 'BROKER_REALIZED_PNL'
  | 'BROKER_DIVIDEND'
  | 'METAL_REALIZED_PNL'
  | 'REAL_ESTATE_REALIZED_PNL'

type ImportMode = 'transactions' | 'brokerage_events'

type ParserMeta = {
  name: string
  kind: 'CSV' | 'PDF'
  accept: string
  upload_label: string
  supports_brokerage_events: boolean
}

type ParsedTransactionRow = {
  date: string
  amount: string
  description: string
  amount_after: string
  category?: string | null
  status?: string | null
  capital_gain_kind?: string | null
}

type ParsedBrokerageRow = {
  trade_at: string
  instrument_symbol: string
  instrument_mic: string
  instrument_name?: string | null
  kind: 'BUY' | 'SELL' | 'DIV' | 'SPLIT'
  quantity: string
  price: string
  currency: 'PLN' | 'USD' | 'EUR'
  split_ratio: string
}

type MarketOpt = {
  mic: string
  name: string
}

type InstrumentOpt = {
  symbol: string
  shortname: string
}

const CAPITAL_GAIN_OPTIONS: { value: CapitalGainKind; label: string }[] = [
  { value: 'TRANSACTION', label: 'Zwykła transakcja' },
  { value: 'DEPOSIT_INTEREST', label: 'Zysk z odsetek' },
  { value: 'BROKER_REALIZED_PNL', label: 'Zysk ze sprzedaży' },
  { value: 'BROKER_DIVIDEND', label: 'Dywidenda' },
  { value: 'METAL_REALIZED_PNL', label: 'Zysk ze sprzedaży metalu' },
  { value: 'REAL_ESTATE_REALIZED_PNL', label: 'Zysk ze sprzedaży nieruchomości' },
]

async function apiJson<T>(url: string, init?: RequestInit): Promise<{ ok: boolean; data: T | null; error?: string }> {
  const res = await fetch(url, init)

  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    data = null
  }

  if (!res.ok) {
    const error =
      data && typeof data === 'object' && 'error' in data && typeof data.error === 'string'
        ? data.error
        : 'Wystąpił błąd'
    return { ok: false, data: null, error }
  }

  return { ok: true, data: data as T }
}

function toIsoString(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toISOString()
}

function formatDateLabel(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function toDecimalNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const normalized = typeof value === 'string' ? value.replace(',', '.') : value
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function formatMoneyLabel(value: string | number): string {
  const parsed = toDecimalNumber(value)
  if (parsed === null) return String(value)
  return parsed.toLocaleString('pl-PL', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function normalizeImportedTransactionRows(rows: ParsedTransactionRow[]): ParsedTransactionRow[] {
  if (rows.length <= 1) return rows

  const withTime = rows.map((row) => ({
    row,
    time: new Date(row.date).getTime(),
  }))

  const valid = withTime.every((item) => Number.isFinite(item.time))
  if (!valid) return rows

  const isAscending = withTime.every((item, index) => index === 0 || withTime[index - 1]!.time <= item.time)
  if (isAscending) return rows

  const isDescending = withTime.every((item, index) => index === 0 || withTime[index - 1]!.time >= item.time)
  if (isDescending) return [...rows].reverse()

  return [...rows].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
}

function TabButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'rounded-lg px-3 py-1.5 text-sm transition-colors',
        active ? 'bg-emerald-600/20 text-white border border-emerald-500/30' : 'text-white/55 hover:text-white hover:bg-white/8 border border-transparent',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

function ManualTab({
  accounts,
  onSuccess,
}: {
  accounts: TransactionAccountOpt[]
  onSuccess: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [capitalGainKind, setCapitalGainKind] = useState<CapitalGainKind>('TRANSACTION')
  const [balanceAfter, setBalanceAfter] = useState('')
  const [date, setDate] = useState('')
  const [error, setError] = useState<string>()

  const selectedAccount = useMemo(
    () => accounts.find((account) => account.id === accountId) ?? null,
    [accounts, accountId],
  )

  function submit(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!accountId) { setError('Wybierz konto'); return }
    if (!amount.trim()) { setError('Podaj kwotę transakcji'); return }
    if (!balanceAfter.trim()) { setError('Podaj saldo po transakcji'); return }
    if (!description.trim()) { setError('Podaj opis transakcji'); return }
    if (!date) { setError('Podaj datę transakcji'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiJson('/api/wallet/transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: accountId,
          transactions: [
            {
              date: toIsoString(date),
              amount: amount.trim().replace(',', '.'),
              description: description.trim(),
              amount_after: balanceAfter.trim().replace(',', '.'),
              capital_gain_kind: capitalGainKind === 'TRANSACTION' ? null : capitalGainKind,
            },
          ],
        }),
      })

      if (!ok) {
        setError(err || 'Nie udało się dodać transakcji')
        return
      }

      toast.success('Pomyślnie dodano transakcję')
      onSuccess()
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Konto *</Label>
        <Select value={accountId} onValueChange={setAccountId}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue placeholder="Wybierz konto" />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {accounts.map((account) => (
              <SelectItem key={account.id} value={account.id}>
                {account.walletName} · {account.name} ({account.currency})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selectedAccount && (
          <p className="text-[11px] text-white/40">
            Portfel: {selectedAccount.walletName} · Waluta konta: {selectedAccount.currency}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Kwota *</Label>
          <Input
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="np. -120.50 albo 2500"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Saldo po transakcji *</Label>
          <Input
            value={balanceAfter}
            onChange={(event) => setBalanceAfter(event.target.value)}
            placeholder="np. 5140.30"
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Opis *</Label>
        <Input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="np. Biedronka, przelew, wynagrodzenie"
          maxLength={255}
          className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
        />
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Typ *</Label>
        <Select value={capitalGainKind} onValueChange={(value: CapitalGainKind) => setCapitalGainKind(value)}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {CAPITAL_GAIN_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Data *</Label>
        <DateTimePicker value={date} onChange={setDate} placeholder="Wybierz datę i godzinę" />
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button
          type="submit"
          disabled={isPending || accounts.length === 0}
          className="bg-emerald-700 hover:bg-emerald-600 text-white gap-2"
        >
          {isPending ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {isPending ? 'Dodawanie…' : 'Dodaj transakcję'}
        </Button>
      </div>
    </form>
  )
}

function ImportTab({
  open,
  accounts,
  brokerageAccounts,
  onSuccess,
}: {
  open: boolean
  accounts: TransactionAccountOpt[]
  brokerageAccounts: TransactionBrokerageAccountOpt[]
  onSuccess: () => void
}) {
  const [parsers, setParsers] = useState<ParserMeta[]>([])
  const [parsersError, setParsersError] = useState<string>()
  const [parsersLoaded, setParsersLoaded] = useState(false)
  const [selectedParserName, setSelectedParserName] = useState('')
  const [importMode, setImportMode] = useState<ImportMode>('transactions')
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '')
  const [brokerageAccountId, setBrokerageAccountId] = useState(brokerageAccounts[0]?.id ?? '')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [parseError, setParseError] = useState<string>()
  const [txRows, setTxRows] = useState<ParsedTransactionRow[]>([])
  const [brokerRows, setBrokerRows] = useState<ParsedBrokerageRow[]>([])
  const [importSummary, setImportSummary] = useState<string>()
  const [isParsing, setIsParsing] = useState(false)
  const [isImporting, startImportTransition] = useTransition()

  useEffect(() => {
    if (!open) return
    if (parsersLoaded) return   

    let cancelled = false

    async function loadParsers() {
      const { ok, data, error } = await apiJson<ParserMeta[]>('/api/wallet/import/parsers')
      if (cancelled) return

      setParsersLoaded(true)

      if (!ok || !data) {
        setParsersError(error || 'Nie udało się pobrać parserów importu')
        return
      }

      setParsers(data)
      setSelectedParserName((current) => current || data[0]?.name || '')
    }

    void loadParsers()

    return () => {
      cancelled = true
    }
  }, [open, parsersLoaded])

  const selectedParser = useMemo(
    () => parsers.find((parser) => parser.name === selectedParserName) ?? null,
    [parsers, selectedParserName],
  )

  const selectedAccount = useMemo(
    () => accounts.find((account) => account.id === accountId) ?? null,
    [accounts, accountId],
  )

  const normalizedTxRows = useMemo(
    () => normalizeImportedTransactionRows(txRows),
    [txRows],
  )

  const importBalanceWarning = useMemo(() => {
    if (importMode !== 'transactions' || normalizedTxRows.length === 0 || !selectedAccount?.lastTransactionAt || !selectedAccount.lastBalanceAfter) {
      return null
    }

    const firstRow = normalizedTxRows[0]
    if (!firstRow) {
      return null
    }

    const firstDate = new Date(firstRow.date)
    const lastTransactionDate = new Date(selectedAccount.lastTransactionAt)

    if (Number.isNaN(firstDate.getTime()) || Number.isNaN(lastTransactionDate.getTime())) {
      return null
    }

    if (firstDate.getTime() <= lastTransactionDate.getTime()) {
      return null
    }

    const firstAmount = toDecimalNumber(firstRow.amount)
    const providedAfter = toDecimalNumber(firstRow.amount_after)
    const lastRecordedAfter = toDecimalNumber(selectedAccount.lastBalanceAfter)

    if (firstAmount === null || providedAfter === null || lastRecordedAfter === null) {
      return null
    }

    const impliedBefore = Number((providedAfter - firstAmount).toFixed(2))
    const roundedLastRecordedAfter = Number(lastRecordedAfter.toFixed(2))

    if (Math.abs(impliedBefore - roundedLastRecordedAfter) < 0.005) {
      return null
    }

    const delta = Number((roundedLastRecordedAfter - impliedBefore).toFixed(2))

    return {
      impliedBefore,
      lastRecordedAfter: roundedLastRecordedAfter,
      delta,
      firstDateLabel: formatDateLabel(firstRow.date),
      lastTransactionLabel: formatDateLabel(selectedAccount.lastTransactionAt),
    }
  }, [accountId, importMode, normalizedTxRows, selectedAccount])

  function resetParsedState() {
    setParseError(undefined)
    setImportSummary(undefined)
    setTxRows([])
    setBrokerRows([])
  }

  async function handleParse() {
    if (!selectedParserName) {
      setParseError('Wybierz format banku')
      return
    }
    if (!selectedFile) {
      setParseError('Wybierz plik do importu')
      return
    }

    resetParsedState()
    setIsParsing(true)

    const formData = new FormData()
    formData.append('parser_name', selectedParserName)
    formData.append('mode', importMode)
    formData.append('file', selectedFile)

    const { ok, data, error } = await apiJson<{ rows: ParsedTransactionRow[] | ParsedBrokerageRow[] }>('/api/wallet/import/parse', {
      method: 'POST',
      body: formData,
    })

    setIsParsing(false)

    if (!ok || !data) {
      setParseError(error || 'Nie udało się sparsować pliku')
      return
    }

    if (importMode === 'transactions') {
      setTxRows(data.rows as ParsedTransactionRow[])
      toast.success(`Sparowano ${data.rows.length} transakcji`)
      return
    }

    setBrokerRows(data.rows as ParsedBrokerageRow[])
    toast.success(`Sparowano ${data.rows.length} operacji maklerskich`)
  }

  function handleImport() {
    setParseError(undefined)
    setImportSummary(undefined)

    startImportTransition(async () => {
      if (importMode === 'transactions') {
        if (!accountId) {
          setParseError('Wybierz konto dla importowanych transakcji')
          return
        }
        if (txRows.length === 0) {
          setParseError('Najpierw sparsuj plik')
          return
        }

        const { ok, error } = await apiJson('/api/wallet/transactions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            account_id: accountId,
            transactions: normalizedTxRows,
          }),
        })

        if (!ok) {
          setParseError(error || 'Nie udało się zaimportować transakcji')
          return
        }

        toast.success(`Zaimportowano ${txRows.length} transakcji`)
        onSuccess()
        return
      }

      if (!brokerageAccountId) {
        setParseError('Wybierz rachunek maklerski dla importu')
        return
      }
      if (brokerRows.length === 0) {
        setParseError('Najpierw sparsuj plik')
        return
      }

      const { ok, data, error } = await apiJson<{ created: number; failed: number; errors: string[] }>('/api/wallet/brokerage/events/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brokerage_account_id: brokerageAccountId,
          events: brokerRows,
        }),
      })

      if (!ok || !data) {
        setParseError(error || 'Nie udało się zaimportować operacji maklerskich')
        return
      }

      setImportSummary(`Utworzono: ${data.created}, błędów: ${data.failed}`)
      if (data.failed === 0) {
        toast.success(`Zaimportowano ${data.created} operacji maklerskich`)
        onSuccess()
        return
      }

      setParseError(data.errors[0] || 'Część operacji nie została zaimportowana')
    })
  }

  if (parsersLoaded && parsersError && parsers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3 text-center">
        <div className="p-4 rounded-full bg-amber-500/10 border border-amber-500/20">
          <Upload className="w-8 h-8 text-amber-400/50" />
        </div>
        <p className="text-white/60 text-sm font-medium">Import niedostępny</p>
        <p className="text-white/35 text-xs max-w-xs">
          Serwis parserów jest chwilowo niedostępny.<br />Spróbuj ponownie później.
        </p>
        <button
          type="button"
          onClick={() => { setParsersLoaded(false); setParsersError(undefined) }}
          className="mt-1 text-xs text-emerald-400 hover:text-emerald-300 underline underline-offset-2 transition-colors"
        >
          Spróbuj ponownie
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Format banku *</Label>
          <Select
            value={selectedParserName}
            onValueChange={(value) => {
              const nextParser = parsers.find((parser) => parser.name === value) ?? null
              setSelectedParserName(value)
              setImportMode(nextParser?.supports_brokerage_events ? importMode : 'transactions')
              setSelectedFile(null)
              resetParsedState()
            }}
          >
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue placeholder="Wybierz parser" />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {parsers.map((parser) => (
                <SelectItem key={parser.name} value={parser.name}>
                  {parser.name} · {parser.kind}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {selectedParser?.supports_brokerage_events ? (
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">Tryb importu *</Label>
            <Select
              value={importMode}
              onValueChange={(value: ImportMode) => {
                setImportMode(value)
                resetParsedState()
              }}
            >
              <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-900 border-white/10 text-white">
                <SelectItem value="transactions">Import jako transakcje gotówkowe</SelectItem>
                <SelectItem value="brokerage_events">Import jako operacje maklerskie</SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : (
          <div className="rounded-xl border border-white/10 bg-slate-800/40 px-3 py-2 text-sm text-white/55">
            Ten format obsługuje import transakcji gotówkowych.
          </div>
        )}
      </div>

      {importMode === 'transactions' ? (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Konto dla importowanych transakcji *</Label>
          <Select value={accountId} onValueChange={setAccountId}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue placeholder="Wybierz konto" />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {accounts.map((account) => (
                <SelectItem key={account.id} value={account.id}>
                  {account.walletName} · {account.name} ({account.currency})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedAccount && (
            <p className="text-[11px] text-white/40">
              Bieżące saldo: {selectedAccount.available ? `${formatMoneyLabel(selectedAccount.available)} ${selectedAccount.currency}` : `0,00 ${selectedAccount.currency}`}
              {selectedAccount.lastTransactionAt && selectedAccount.lastBalanceAfter
                ? ` · ostatnia transakcja: ${formatDateLabel(selectedAccount.lastTransactionAt)} · saldo po: ${formatMoneyLabel(selectedAccount.lastBalanceAfter)} ${selectedAccount.currency}`
                : ''}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Rachunek maklerski dla operacji *</Label>
          <Select value={brokerageAccountId} onValueChange={setBrokerageAccountId}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue placeholder="Wybierz rachunek maklerski" />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              {brokerageAccounts.map((account) => (
                <SelectItem key={account.id} value={account.id}>
                  {account.walletName} · {account.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Plik *</Label>
        <input
          type="file"
          accept={selectedParser?.accept ?? '.csv,.pdf'}
          onChange={(event) => {
            setSelectedFile(event.target.files?.[0] ?? null)
            resetParsedState()
          }}
          className="block w-full rounded-lg border border-white/10 bg-slate-800/80 px-3 py-2 text-sm text-white file:mr-3 file:rounded-md file:border-0 file:bg-emerald-700/80 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-emerald-600/80"
        />
        {selectedParser && (
          <p className="text-[11px] text-white/40">
            {selectedParser.upload_label} · typ: {selectedParser.kind}
          </p>
        )}
      </div>

      {(parsersError || parseError) && (
        <p className="text-sm text-red-400 break-words overflow-hidden">{parsersError || parseError}</p>
      )}

      {importBalanceWarning && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
          Pierwsza transakcja z importu ({importBalanceWarning.firstDateLabel}) sugeruje saldo początkowe
          {' '}
          {formatMoneyLabel(importBalanceWarning.impliedBefore)}
          {' '}
          {selectedAccount?.currency}, ale ostatnie zapisane saldo tego konta to
          {' '}
          {formatMoneyLabel(importBalanceWarning.lastRecordedAfter)}
          {' '}
          {selectedAccount?.currency}
          {' '}
          po transakcji z
          {' '}
          {importBalanceWarning.lastTransactionLabel}.
          {' '}
          Różnica wynosi {formatMoneyLabel(Math.abs(importBalanceWarning.delta))} {selectedAccount?.currency}, więc import najpewniej zakończy się błędem walidacji, dopóki nie poprawisz wcześniejszej transakcji albo nie doimportujesz brakującej operacji.
        </div>
      )}

      {importSummary && <p className="text-sm text-amber-300">{importSummary}</p>}

      <div className="flex flex-wrap justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          onClick={handleParse}
          disabled={isParsing || isImporting}
          className="text-white/70 hover:text-white hover:bg-white/10 gap-2"
        >
          {isParsing ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {isParsing ? 'Parsowanie…' : 'Przetwórz plik'}
        </Button>
        <Button
          type="button"
          onClick={handleImport}
          disabled={isParsing || isImporting}
          className="bg-emerald-700 hover:bg-emerald-600 text-white gap-2"
        >
          {isImporting ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {isImporting ? 'Importowanie…' : 'Importuj'}
        </Button>
      </div>

      {importMode === 'transactions' && txRows.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-slate-800/40 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-white/10">
            <p className="text-sm font-medium text-white/85">Podgląd transakcji</p>
            <span className="text-xs text-white/45">{txRows.length} wierszy</span>
          </div>
          <div className="max-h-72 overflow-auto w-full">
            <table className="w-full text-sm min-w-0">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="px-3 py-2 text-left text-xs text-white/40 font-medium">Data</th>
                  <th className="px-3 py-2 text-left text-xs text-white/40 font-medium">Opis</th>
                  <th className="px-3 py-2 text-right text-xs text-white/40 font-medium">Kwota</th>
                  <th className="px-3 py-2 text-right text-xs text-white/40 font-medium">Saldo po</th>
                </tr>
              </thead>
              <tbody>
                {txRows.slice(0, 20).map((row, index) => (
                  <tr key={`${row.date}-${index}`} className="border-b border-white/5 last:border-0">
                    <td className="px-3 py-2 text-white/75">{row.date}</td>
                    <td className="px-3 py-2 text-white/75">{row.description}</td>
                    <td className="px-3 py-2 text-right text-white/75">{row.amount}</td>
                    <td className="px-3 py-2 text-right text-white/75">{row.amount_after}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {importMode === 'brokerage_events' && brokerRows.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-slate-800/40 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-white/10">
            <p className="text-sm font-medium text-white/85">Podgląd operacji maklerskich</p>
            <span className="text-xs text-white/45">{brokerRows.length} wierszy</span>
          </div>
          <div className="max-h-72 overflow-auto w-full">
            <table className="w-full text-sm min-w-0">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="px-3 py-2 text-left text-xs text-white/40 font-medium">Data</th>
                  <th className="px-3 py-2 text-left text-xs text-white/40 font-medium">Instrument</th>
                  <th className="px-3 py-2 text-center text-xs text-white/40 font-medium">Typ</th>
                  <th className="px-3 py-2 text-right text-xs text-white/40 font-medium">Ilość</th>
                  <th className="px-3 py-2 text-right text-xs text-white/40 font-medium">Cena</th>
                </tr>
              </thead>
              <tbody>
                {brokerRows.slice(0, 20).map((row, index) => (
                  <tr key={`${row.trade_at}-${row.instrument_symbol}-${index}`} className="border-b border-white/5 last:border-0">
                    <td className="px-3 py-2 text-white/75">{formatDateLabel(row.trade_at)}</td>
                    <td className="px-3 py-2 text-white/75">{row.instrument_symbol} · {row.instrument_name ?? row.instrument_mic}</td>
                    <td className="px-3 py-2 text-center text-white/75">{row.kind}</td>
                    <td className="px-3 py-2 text-right text-white/75">{row.quantity}</td>
                    <td className="px-3 py-2 text-right text-white/75">{row.price} {row.currency}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function BrokerageTab({
  open,
  brokerageAccounts,
  onSuccess,
}: {
  open: boolean
  brokerageAccounts: TransactionBrokerageAccountOpt[]
  onSuccess: () => void
}) {
  const [markets, setMarkets] = useState<MarketOpt[]>([])
  const [marketsError, setMarketsError] = useState<string>()
  const [instruments, setInstruments] = useState<InstrumentOpt[]>([])
  const [instrumentsError, setInstrumentsError] = useState<string>()
  const [brokerageAccountId, setBrokerageAccountId] = useState(brokerageAccounts[0]?.id ?? '')
  const [mic, setMic] = useState('')
  const [instrumentQuery, setInstrumentQuery] = useState('')
  const [instrumentSymbol, setInstrumentSymbol] = useState('')
  const [kind, setKind] = useState<'BUY' | 'SELL' | 'DIV'>('BUY')
  const [quantity, setQuantity] = useState('0')
  const [price, setPrice] = useState('0')
  const [currency, setCurrency] = useState<'PLN' | 'USD' | 'EUR'>('PLN')
  const [tradeAt, setTradeAt] = useState('')
  const [error, setError] = useState<string>()
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    if (!open) return
    if (markets.length > 0) return

    let cancelled = false

    async function loadMarkets() {
      const { ok, data, error: err } = await apiJson<MarketOpt[]>('/api/stock/markets')
      if (cancelled) return

      if (!ok || !data) {
        setMarketsError(err || 'Nie udało się pobrać rynków')
        return
      }

      setMarkets(data)
    }

    void loadMarkets()

    return () => {
      cancelled = true
    }
  }, [open, markets.length])

  useEffect(() => {
    if (!mic) return

    let cancelled = false

    async function loadInstruments() {
      setInstrumentsError(undefined)
      const qs = new URLSearchParams({ mic })
      const { ok, data, error: err } = await apiJson<InstrumentOpt[]>(`/api/stock/instruments?${qs.toString()}`)
      if (cancelled) return

      if (!ok || !data) {
        setInstruments([])
        setInstrumentsError(err || 'Nie udało się pobrać instrumentów')
        return
      }

      setInstruments(data)
    }

    void loadInstruments()

    return () => {
      cancelled = true
    }
  }, [mic])

  const filteredInstruments = useMemo(() => {
    const query = instrumentQuery.trim().toLowerCase()
    if (!query) return instruments
    return instruments.filter((item) =>
      item.symbol.toLowerCase().includes(query) || item.shortname.toLowerCase().includes(query),
    )
  }, [instrumentQuery, instruments])

  const selectedInstrument = useMemo(
    () => instruments.find((item) => item.symbol === instrumentSymbol) ?? null,
    [instruments, instrumentSymbol],
  )

  function submit(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!brokerageAccountId) { setError('Wybierz rachunek maklerski'); return }
    if (!mic) { setError('Wybierz rynek'); return }
    if (!instrumentSymbol) { setError('Wybierz instrument'); return }
    if (!tradeAt) { setError('Podaj datę operacji'); return }
    setError(undefined)

    startTransition(async () => {
      const { ok, error: err } = await apiJson('/api/wallet/brokerage/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brokerage_account_id: brokerageAccountId,
          instrument_symbol: instrumentSymbol,
          instrument_mic: mic,
          instrument_name: selectedInstrument?.shortname ?? instrumentSymbol,
          kind,
          quantity: quantity.trim().replace(',', '.'),
          price: price.trim().replace(',', '.'),
          currency,
          split_ratio: '0',
          trade_at: toIsoString(tradeAt),
        }),
      })

      if (!ok) {
        setError(err || 'Nie udało się zapisać operacji maklerskiej')
        return
      }

      toast.success('Zdarzenie maklerskie zapisane')
      onSuccess()
    })
  }

  if (brokerageAccounts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3 text-center">
        <div className="p-4 rounded-full bg-white/5 border border-white/10">
          <WalletCards className="w-8 h-8 text-white/25" />
        </div>
        <div>
          <p className="text-white/60 text-sm font-medium">Brak rachunków maklerskich</p>
          <p className="text-white/35 text-xs mt-1">
            Dodaj konto maklerskie (typ BROKERAGE) w portfelu,<br />aby móc dodawać operacje.
          </p>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Rachunek maklerski *</Label>
        <Select value={brokerageAccountId} onValueChange={setBrokerageAccountId}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue placeholder="Wybierz rachunek maklerski" />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {brokerageAccounts.map((account) => (
              <SelectItem key={account.id} value={account.id}>
                {account.walletName ? `${account.walletName} · ${account.name}` : account.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Rynek *</Label>
        <Select value={mic} onValueChange={(value) => {
          setMic(value)
          setInstrumentSymbol('')
          setInstrumentQuery('')
        }}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue placeholder="Wybierz rynek" />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {markets.map((market) => (
              <SelectItem key={market.mic} value={market.mic}>
                {market.mic} · {market.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {marketsError && <p className="text-sm text-red-400">{marketsError}</p>}
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Filtr instrumentów</Label>
        <Input
          value={instrumentQuery}
          onChange={(event) => setInstrumentQuery(event.target.value)}
          placeholder="Szukaj po symbolu lub nazwie"
          className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
        />
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Instrument *</Label>
        <Select value={instrumentSymbol} onValueChange={setInstrumentSymbol}>
          <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
            <SelectValue placeholder="Wybierz instrument" />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-white/10 text-white">
            {filteredInstruments.slice(0, 200).map((instrument) => (
              <SelectItem key={instrument.symbol} value={instrument.symbol}>
                {instrument.symbol} · {instrument.shortname}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {instrumentsError && <p className="text-sm text-red-400">{instrumentsError}</p>}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Rodzaj *</Label>
          <Select value={kind} onValueChange={(value: 'BUY' | 'SELL' | 'DIV') => setKind(value)}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              <SelectItem value="BUY">BUY</SelectItem>
              <SelectItem value="SELL">SELL</SelectItem>
              <SelectItem value="DIV">DIV</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Waluta *</Label>
          <Select value={currency} onValueChange={(value: 'PLN' | 'USD' | 'EUR') => setCurrency(value)}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              <SelectItem value="PLN">PLN</SelectItem>
              <SelectItem value="USD">USD</SelectItem>
              <SelectItem value="EUR">EUR</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Ilość</Label>
          <Input
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Cena / kwota</Label>
          <Input
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            inputMode="decimal"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-white/70 text-xs">Data *</Label>
        <DateTimePicker value={tradeAt} onChange={setTradeAt} placeholder="Wybierz datę i godzinę" />
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button
          type="submit"
          disabled={isPending || brokerageAccounts.length === 0}
          className="bg-emerald-700 hover:bg-emerald-600 text-white gap-2"
        >
          {isPending ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <WalletCards className="w-4 h-4" />}
          {isPending ? 'Zapisywanie…' : 'Dodaj operację'}
        </Button>
      </div>
    </form>
  )
}

export function TransactionsDialog({
  open,
  onOpenChange,
  accounts,
  brokerageAccounts,
  initialTab,
}: Props) {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<ActiveTab>(initialTab ?? 'manual')

  function handleSuccess() {
    router.refresh()
    onOpenChange(false)
  }

  function handleOpenChange(next: boolean) {
    if (!next) setActiveTab('manual')
    onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-md border-white/10 text-white sm:max-w-xl max-h-[90vh] overflow-y-auto overflow-x-hidden">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
              <Landmark className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <DialogTitle className="text-white text-lg">Transakcje</DialogTitle>
              <DialogDescription className="text-white/50 text-sm">
                Ręczne dodanie, import bankowy i operacje maklerskie.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="flex flex-wrap gap-2 border-b border-white/10 pb-3">
          <TabButton active={activeTab === 'manual'} label="Ręczna" onClick={() => setActiveTab('manual')} />
          <TabButton active={activeTab === 'import'} label="Import CSV" onClick={() => setActiveTab('import')} />
          <TabButton active={activeTab === 'brokerage'} label="Makler" onClick={() => setActiveTab('brokerage')} />
        </div>

        {activeTab === 'manual' && (
          <ManualTab accounts={accounts} onSuccess={handleSuccess} />
        )}

        {activeTab === 'import' && (
          <ImportTab
            open={open}
            accounts={accounts}
            brokerageAccounts={brokerageAccounts}
            onSuccess={handleSuccess}
          />
        )}

        {activeTab === 'brokerage' && (
          <BrokerageTab
            open={open}
            brokerageAccounts={brokerageAccounts}
            onSuccess={handleSuccess}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
