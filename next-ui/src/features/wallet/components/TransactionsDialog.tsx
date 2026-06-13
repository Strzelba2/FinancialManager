'use client'

import { useEffect, useMemo, useState, useTransition } from 'react'
import { Info, Landmark, LoaderCircle, Save, Upload, WalletCards } from 'lucide-react'
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
import type { BrokerageImportSummary } from '@/lib/api/wallet'

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

type ImportMode = 'transactions' | 'brokerage_events' | 'brokerage_history' | 'full'

type ParserInstruction = {
  title: string
  steps: string[]
  columns?: { label: string; name: string }[]
}

type ParserInstructionsByMode = {
  transactions?: ParserInstruction
  brokerage_events?: ParserInstruction
  brokerage_history?: ParserInstruction
  full?: ParserInstruction
}

const PARSER_INSTRUCTIONS: Record<string, ParserInstructionsByMode> = {
  'IngMakler CSV': {
    transactions: {
      title: 'Jak przygotować plik CSV z ING Makler (transakcje)',
      steps: [
        'Usuń kolumnę z numeracją wierszy (pierwsza kolumna z liczbami porządkowymi).',
        'Usuń pierwszy wiersz (nagłówek banku) oraz ostatni wiersz (podsumowanie).',
        'Upewnij się, że pierwszy wiersz zawiera nagłówki kolumn zgodnie z listą poniżej.',
        'Kolejność transakcji zostanie ułożona automatycznie według daty i salda po operacji.',
        'Podziel plik według waluty — jeden plik = jedno konto / jedna waluta.',
      ],
      columns: [
        { label: 'a)', name: 'Data transakcji' },
        { label: 'b)', name: 'Typ transakcji' },
        { label: 'c)', name: 'Opis transakcji' },
        { label: 'd)', name: 'Kwota transakcji' },
        { label: 'e)', name: 'Saldo po operacji' },
        { label: 'f)', name: 'Waluta' },
      ],
    },
    brokerage_events: {
      title: 'Jak przygotować plik CSV z ING Makler (operacje maklerskie)',
      steps: [
        'Użyj eksportu historii operacji z rachunku maklerskiego ING (nie wyciągu konta gotówkowego).',
        'Upewnij się, że pierwszy wiersz zawiera nagłówki kolumn zgodnie z listą poniżej — nazwy muszą być dokładne.',
        'Parser rozpoznaje tylko operacje kupna i sprzedaży — inne typy (np. prowizje, dywidendy jako oddzielne wiersze) są pomijane.',
        'Instrument w kolumnie "Instrument" musi być skrótem rozpoznawalnym przez serwis notowań (np. PKN, CDR).',
      ],
      columns: [
        { label: 'a)', name: 'Data transakcji' },
        { label: 'b)', name: 'Typ Transakcji' },
        { label: 'c)', name: 'Instrument' },
        { label: 'd)', name: 'Ilość' },
        { label: 'e)', name: 'Kwota z Prowizją' },
        { label: 'f)', name: 'Waluta' },
      ],
    },
  },
  'BossaMakler CSV': {
    brokerage_history: {
      title: 'Jak przygotować plik CSV z BoSSA',
      steps: [
        'Użyj jednego pliku historii finansowej z kolumnami gotówkowymi i maklerskimi.',
        'Plik powinien obejmować pełną historię od najstarszych wierszy na dole do najnowszych u góry.',
        'Kolumna "Saldo po operacji" może być pusta — parser wyliczy ją osobno dla PLN, USD i EUR.',
        'Backend nadal waliduje łańcuch sald osobno dla PLN, USD i EUR przed zapisem.',
        'Jeżeli plik zawiera USD lub EUR, konto maklerskie musi mieć podpięte subkonto gotówkowe w tej walucie.',
      ],
      columns: [
        { label: 'a)', name: 'data' },
        { label: 'b)', name: 'tytuł operacji' },
        { label: 'c)', name: 'szczegóły' },
        { label: 'd)', name: 'kwota' },
        { label: 'e)', name: 'Saldo po operacji (opcjonalnie)' },
        { label: 'f)', name: 'waluta' },
      ],
    },
  },
  'SaxoMakler CSV': {
    full: {
      title: 'Jak przygotować plik CSV z Saxo',
      steps: [
        'Wyeksportuj historię z Saxo i zapisz jako plik CSV.',
        'Podziel transakcje na osobne pliki według waluty — np. osobno PLN i osobno EUR (jeden plik = jedno konto / jedna waluta).',
        'Eksport zawiera już wymagane kolumny — nie zmieniaj nazw nagłówków.',
        'Tryb „Pełny import" tworzy jednocześnie transakcje gotówkowe (w walucie pliku) oraz operacje maklerskie (pozycje w walucie instrumentu).',
        'Wskaż konto gotówkowe w walucie pliku oraz pasujący rachunek maklerski.',
        'Instrumenty muszą istnieć w serwisie notowań — w razie braku dodaj je przed importem.',
      ],
      columns: [
        { label: 'a)', name: 'Data transakcji' },
        { label: 'b)', name: 'Zdarzenie' },
        { label: 'c)', name: 'Kwota' },
        { label: 'd)', name: 'Saldo po operacji' },
        { label: 'e)', name: 'Waluta' },
        { label: 'f)', name: 'Instrument' },
        { label: 'g)', name: 'Symbol instrumentu' },
        { label: 'h)', name: 'Instrument ISIN' },
        { label: 'i)', name: 'Waluta instrumentu' },
      ],
    },
  },
}

type ParserMeta = {
  name: string
  kind: 'CSV' | 'PDF'
  accept: string
  upload_label: string
  supports_brokerage_events: boolean
  supports_brokerage_history?: boolean
  supports_full_import?: boolean
}

function getImportModeForParser(parser: ParserMeta | null, currentMode: ImportMode): ImportMode {
  if (!parser) return 'transactions'
  if (parser.supports_brokerage_history) return 'brokerage_history'
  if (!parser.supports_brokerage_events) return 'transactions'
  if (currentMode === 'full') return parser.supports_full_import ? 'full' : 'transactions'
  return currentMode === 'brokerage_history' ? 'transactions' : currentMode
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

// Response of POST /api/wallet/transactions (cash import): { success, summary }.
type CashImportResult = {
  summary?: { created?: number; skipped_duplicates?: number }
}

type BrokerageKind = 'BUY' | 'SELL' | 'DIV' | 'SPLIT' | 'ADJUSTMENT'

// Instrument/quote (trade) currency — superset of the base reporting currency.
type TradeCurrency = 'PLN' | 'USD' | 'EUR' | 'GBP' | 'CHF'

type ParsedBrokerageRow = {
  trade_at: string
  instrument_symbol: string
  instrument_mic: string
  instrument_name?: string | null
  kind: BrokerageKind
  quantity: string
  price: string
  currency: TradeCurrency
  split_ratio: string
  note?: string | null
  // Account (base) settlement currency + FX rate (instrument -> settlement).
  settlement_currency?: 'PLN' | 'USD' | 'EUR' | null
  fx_rate?: string | null
}

type ParsedBrokerageHistoryRow = {
  row_number: number
  operation_type: string
  trade_at: string
  currency: 'PLN' | 'USD' | 'EUR'
  amount: string
  amount_after: string
  description: string
  capital_gain_kind?: string | null
  instrument_symbol?: string | null
  instrument_mic?: string | null
  instrument_name?: string | null
  event_kind?: BrokerageKind | 'CONVERSION' | null
  quantity?: string | null
  price?: string | null
  split_ratio?: string | null
  review_reason?: string | null
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

function toCents(value: string | number | null | undefined): number | null {
  const parsed = toDecimalNumber(value)
  return parsed === null ? null : Math.round(parsed * 100)
}

function formatMoneyLabel(value: string | number): string {
  const parsed = toDecimalNumber(value)
  if (parsed === null) return String(value)
  return parsed.toLocaleString('pl-PL', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatBrokerageImportRowError(row: BrokerageImportSummary['rows'][number]): string {
  if (row.reason_code === 'holding_quantity_exceeded') {
    const instrument = row.instrument_symbol ?? row.instrument_name ?? 'instrument'
    const kind = row.kind ?? 'operacja'
    const date = row.trade_at ? formatDateLabel(row.trade_at) : 'brak daty'
    const quantity = row.quantity !== null && row.quantity !== undefined ? formatMoneyLabel(row.quantity) : '—'
    const held = row.held_quantity !== null && row.held_quantity !== undefined ? formatMoneyLabel(row.held_quantity) : '—'
    const missing = row.missing_quantity !== null && row.missing_quantity !== undefined ? formatMoneyLabel(row.missing_quantity) : '—'
    return `Row ${row.row}: ${instrument}, ${kind} ${quantity}, ${date}, posiadane ${held}, brakuje ${missing}`
  }

  return row.message ?? `Row ${row.row}: operacja nie została zaimportowana`
}

function isHistoryTradeRow(row: ParsedBrokerageHistoryRow): boolean {
  return ['BUY', 'SELL', 'FORCED_SELL'].includes(row.operation_type.toUpperCase())
}

function formatHistoryBlockingRow(row: ParsedBrokerageHistoryRow): string {
  const instrument = row.instrument_symbol ?? row.instrument_name ?? row.description
  if (row.operation_type.toUpperCase() === 'NEEDS_REVIEW') {
    return `Row ${row.row_number}: ${instrument} — ${row.review_reason ?? 'wymaga ręcznego sprawdzenia'}`
  }
  return `Row ${row.row_number}: ${instrument} — brak symbolu lub rynku instrumentu`
}

function groupConsecutiveRowsByTime(rows: ParsedTransactionRow[]): ParsedTransactionRow[][] {
  const groups: ParsedTransactionRow[][] = []
  for (const row of rows) {
    const time = new Date(row.date).getTime()
    const lastGroup = groups.at(-1)
    if (!lastGroup || new Date(lastGroup[0]!.date).getTime() !== time) {
      groups.push([row])
    } else {
      lastGroup.push(row)
    }
  }
  return groups
}

function orderSameTimeRowsByBalanceChain(
  rows: ParsedTransactionRow[],
  openingBalance: number | null,
  preferReversedSourceOrder = false,
): ParsedTransactionRow[] {
  if (rows.length <= 1) return rows

  const nodes = rows.map((row, index) => {
    const amount = toCents(row.amount)
    const after = toCents(row.amount_after)
    if (amount === null || after === null) return null
    return { index, before: after - amount, after }
  })

  const validNodes = nodes.filter((node): node is { index: number; before: number; after: number } => node !== null)
  if (validNodes.length !== nodes.length) return rows
  const afterValues = new Set(validNodes.map((node) => node.after))
  const startNodes = openingBalance === null
    ? validNodes.filter((node) => !afterValues.has(node.before))
    : validNodes.filter((node) => node.before === openingBalance)

  const beforeByIndex = new Map(validNodes.map((node) => [node.index, node.before]))
  const afterByIndex = new Map(validNodes.map((node) => [node.index, node.after]))
  const preferredIndexes = preferReversedSourceOrder
    ? [...rows.keys()].reverse()
    : [...rows.keys()]
  const preferredPosition = new Map(preferredIndexes.map((index, position) => [index, position]))
  const orderedStartNodes = [...startNodes].sort(
    (a, b) => (preferredPosition.get(a.index) ?? a.index) - (preferredPosition.get(b.index) ?? b.index),
  )
  const walk = (currentIndex: number, used: Set<number>, ordered: number[]): number[] | null => {
    if (ordered.length === rows.length) {
      return [...ordered]
    }

    const currentAfter = afterByIndex.get(currentIndex)
    const candidates = validNodes.filter(
      (node) => !used.has(node.index) && beforeByIndex.get(node.index) === currentAfter,
    ).sort(
      (a, b) => (preferredPosition.get(a.index) ?? a.index) - (preferredPosition.get(b.index) ?? b.index),
    )

    for (const candidate of candidates) {
      used.add(candidate.index)
      ordered.push(candidate.index)
      const solution = walk(candidate.index, used, ordered)
      ordered.pop()
      used.delete(candidate.index)
      if (solution) return solution
    }

    return null
  }

  for (const startNode of orderedStartNodes) {
    const solution = walk(startNode.index, new Set([startNode.index]), [startNode.index])
    if (solution) {
      return solution.map((index) => rows[index]!)
    }
  }

  return rows
}

function flattenOrderedTimeGroups(
  groups: ParsedTransactionRow[][],
  preferReversedSourceOrder = false,
): ParsedTransactionRow[] {
  const orderedRows: ParsedTransactionRow[] = []
  let openingBalance: number | null = null

  for (const group of groups) {
    const orderedGroup = orderSameTimeRowsByBalanceChain(group, openingBalance, preferReversedSourceOrder)
    orderedRows.push(...orderedGroup)
    const lastRow = orderedGroup.at(-1)
    openingBalance = lastRow ? toCents(lastRow.amount_after) : null
  }

  return orderedRows
}

export function normalizeImportedTransactionRows(rows: ParsedTransactionRow[]): ParsedTransactionRow[] {
  if (rows.length <= 1) return rows

  const withTime = rows.map((row) => ({
    row,
    time: new Date(row.date).getTime(),
  }))

  const valid = withTime.every((item) => Number.isFinite(item.time))
  if (!valid) return rows

  const isAscending = withTime.every((item, index) => index === 0 || withTime[index - 1]!.time <= item.time)
  if (isAscending) return flattenOrderedTimeGroups(groupConsecutiveRowsByTime(rows))

  const isDescending = withTime.every((item, index) => index === 0 || withTime[index - 1]!.time >= item.time)
  if (isDescending) {
    return flattenOrderedTimeGroups(groupConsecutiveRowsByTime(rows).reverse(), true)
  }

  const sortedRows = [...rows].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
  return flattenOrderedTimeGroups(groupConsecutiveRowsByTime(sortedRows))
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
  const [historyRows, setHistoryRows] = useState<ParsedBrokerageHistoryRow[]>([])
  const [importSummary, setImportSummary] = useState<string>()
  const [isParsing, setIsParsing] = useState(false)
  const [isImporting, startImportTransition] = useTransition()
  const [showInstructions, setShowInstructions] = useState(false)

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

      const defaultParser = data[0] ?? null

      setParsers(data)
      if (!selectedParserName && defaultParser) {
        setSelectedParserName(defaultParser.name)
        setImportMode(getImportModeForParser(defaultParser, importMode))
      }
    }

    void loadParsers()

    return () => {
      cancelled = true
    }
  }, [open, parsersLoaded, selectedParserName, importMode])

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
    if ((importMode !== 'transactions' && importMode !== 'full') || normalizedTxRows.length === 0 || !selectedAccount?.lastTransactionAt || !selectedAccount.lastBalanceAfter) {
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
  }, [importMode, normalizedTxRows, selectedAccount])

  const historyBlockingRows = useMemo(() => {
    if (importMode !== 'brokerage_history') return []
    return historyRows.filter((row) => (
      row.operation_type.toUpperCase() === 'NEEDS_REVIEW' ||
      (isHistoryTradeRow(row) && (!row.instrument_symbol?.trim() || !row.instrument_mic?.trim()))
    ))
  }, [historyRows, importMode])

  const importModeOptions = useMemo(() => {
    if (selectedParser?.supports_brokerage_history) {
      return [{ value: 'brokerage_history' as const, label: 'Pełna historia maklerska' }]
    }
    if (selectedParser?.supports_brokerage_events) {
      const options: { value: ImportMode; label: string }[] = [
        { value: 'transactions', label: 'Import jako transakcje gotówkowe' },
        { value: 'brokerage_events', label: 'Import jako operacje maklerskie' },
      ]
      if (selectedParser.supports_full_import) {
        options.push({ value: 'full', label: 'Pełny import (transakcje + operacje maklerskie)' })
      }
      return options
    }
    return []
  }, [selectedParser])

  function resetParsedState() {
    setParseError(undefined)
    setImportSummary(undefined)
    setTxRows([])
    setBrokerRows([])
    setHistoryRows([])
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

    const file = selectedFile
    const parserName = selectedParserName

    const parseWithMode = (mode: ImportMode) => {
      const formData = new FormData()
      formData.append('parser_name', parserName)
      formData.append('mode', mode)
      formData.append('file', file)
      return apiJson<{ rows: ParsedTransactionRow[] | ParsedBrokerageRow[] | ParsedBrokerageHistoryRow[] }>(
        '/api/wallet/import/parse',
        { method: 'POST', body: formData },
      )
    }

    if (importMode === 'full') {
      const cash = await parseWithMode('transactions')
      const events = await parseWithMode('brokerage_events')

      setIsParsing(false)

      if (!cash.ok || !cash.data) {
        setParseError(cash.error || 'Nie udało się sparsować transakcji gotówkowych')
        return
      }
      if (!events.ok || !events.data) {
        setParseError(events.error || 'Nie udało się sparsować operacji maklerskich')
        return
      }

      const cashRows = cash.data.rows as ParsedTransactionRow[]
      const eventRows = events.data.rows as ParsedBrokerageRow[]
      setTxRows(cashRows)
      setBrokerRows(eventRows)
      toast.success(`Sparsowano ${cashRows.length} transakcji i ${eventRows.length} operacji maklerskich`)
      return
    }

    const { ok, data, error } = await parseWithMode(importMode)

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

    if (importMode === 'brokerage_history') {
      setHistoryRows(data.rows as ParsedBrokerageHistoryRow[])
      toast.success(`Sparowano ${data.rows.length} wierszy historii BoSSA`)
      return
    }

    setBrokerRows(data.rows as ParsedBrokerageRow[])
    toast.success(`Sparowano ${data.rows.length} operacji maklerskich`)
  }

  function handleImport() {
    setParseError(undefined)
    setImportSummary(undefined)

    startImportTransition(async () => {
      if (importMode === 'full') {
        if (!accountId) {
          setParseError('Wybierz konto dla transakcji gotówkowych')
          return
        }
        if (!brokerageAccountId) {
          setParseError('Wybierz rachunek maklerski dla operacji')
          return
        }
        if (normalizedTxRows.length === 0 && brokerRows.length === 0) {
          setParseError('Najpierw sparsuj plik')
          return
        }

        const messages: string[] = []

        if (normalizedTxRows.length > 0) {
          const { ok, data, error } = await apiJson<CashImportResult>('/api/wallet/transactions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              account_id: accountId,
              transactions: normalizedTxRows,
              skip_duplicates: true,
            }),
          })

          if (!ok) {
            setParseError(error || 'Nie udało się zaimportować transakcji gotówkowych')
            return
          }
          const createdCash = data?.summary?.created ?? normalizedTxRows.length
          const skippedCash = data?.summary?.skipped_duplicates ?? 0
          messages.push(`${createdCash} transakcji gotówkowych${skippedCash ? ` (pominięto ${skippedCash})` : ''}`)
        }

        if (brokerRows.length > 0) {
          const { ok, data, error } = await apiJson<BrokerageImportSummary>('/api/wallet/brokerage/events/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              brokerage_account_id: brokerageAccountId,
              events: brokerRows,
            }),
          })

          if (!ok || !data) {
            setParseError(
              (error || 'Nie udało się zaimportować operacji maklerskich')
              + (messages.length > 0 ? `\n(Transakcje gotówkowe zaimportowano: ${messages.join(', ')})` : ''),
            )
            return
          }

          const skipped = data.skipped_duplicates ?? 0
          messages.push(`${data.created} operacji maklerskich (pominięto ${skipped}, błędów ${data.failed})`)

          if (data.failed > 0) {
            setImportSummary(`Zaimportowano: ${messages.join(' i ')}`)
            const failedRows = data.rows.filter((row) => row.status === 'failed')
            setParseError(
              failedRows.length > 0
                ? failedRows.map(formatBrokerageImportRowError).join('\n')
                : data.errors.length > 0
                  ? data.errors.join('\n')
                  : 'Część operacji maklerskich nie została zaimportowana',
            )
            return
          }
        }

        const summary = `Zaimportowano: ${messages.join(' i ')}`
        setImportSummary(summary)
        toast.success(summary)
        onSuccess()
        return
      }

      if (importMode === 'transactions') {
        if (!accountId) {
          setParseError('Wybierz konto dla importowanych transakcji')
          return
        }
        if (txRows.length === 0) {
          setParseError('Najpierw sparsuj plik')
          return
        }

        const { ok, data, error } = await apiJson<CashImportResult>('/api/wallet/transactions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            account_id: accountId,
            transactions: normalizedTxRows,
            skip_duplicates: true,
          }),
        })

        if (!ok) {
          setParseError(error || 'Nie udało się zaimportować transakcji')
          return
        }

        const createdCash = data?.summary?.created ?? txRows.length
        const skippedCash = data?.summary?.skipped_duplicates ?? 0
        toast.success(
          `Zaimportowano ${createdCash} transakcji${skippedCash ? `, pominięto ${skippedCash} duplikatów` : ''}`,
        )
        onSuccess()
        return
      }

      if (!brokerageAccountId) {
        setParseError('Wybierz rachunek maklerski dla importu')
        return
      }
      if (importMode === 'brokerage_history') {
        if (historyRows.length === 0) {
          setParseError('Najpierw sparsuj plik')
          return
        }
        if (historyBlockingRows.length > 0) {
          setParseError(historyBlockingRows.map(formatHistoryBlockingRow).join('\n'))
          return
        }

        const { ok, data, error } = await apiJson<BrokerageImportSummary>('/api/wallet/brokerage/history/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            brokerage_account_id: brokerageAccountId,
            rows: historyRows,
          }),
        })

        if (!ok || !data) {
          setParseError(error || 'Nie udało się zaimportować historii BoSSA')
          return
        }

        const skipped = data.skipped_duplicates ?? 0
        const needsReview = data.needs_review ?? 0
        const cashCreated = data.cash_transactions_created ?? 0
        const total = data.total ?? (data.created + skipped + needsReview + data.failed)
        const summary = `Razem: ${total}, utworzono: ${data.created}, cash: ${cashCreated}, pominięto duplikatów: ${skipped}, do sprawdzenia: ${needsReview}, błędów: ${data.failed}`
        setImportSummary(summary)
        if (data.failed === 0) {
          toast.success(`Import BoSSA zakończony. ${summary}`)
          onSuccess()
          return
        }

        const failedRows = data.rows.filter((row) => row.status === 'failed')
        setParseError(
          failedRows.length > 0
            ? failedRows.map(formatBrokerageImportRowError).join('\n')
            : data.errors.length > 0
              ? data.errors.join('\n')
              : 'Część historii BoSSA nie została zaimportowana',
        )
        return
      }

      if (brokerRows.length === 0) {
        setParseError('Najpierw sparsuj plik')
        return
      }

      const { ok, data, error } = await apiJson<BrokerageImportSummary>('/api/wallet/brokerage/events/import', {
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

      const skipped = data.skipped_duplicates ?? 0
      const total = data.total ?? (data.created + skipped + data.failed)
      const summary = `Razem: ${total}, utworzono: ${data.created}, pominięto duplikatów: ${skipped}, błędów: ${data.failed}`
      setImportSummary(summary)
      if (data.failed === 0) {
        toast.success(`Import maklerski zakończony. ${summary}`)
        onSuccess()
        return
      }

      const failedRows = data.rows.filter((row) => row.status === 'failed')
      setParseError(
        failedRows.length > 0
          ? failedRows.map(formatBrokerageImportRowError).join('\n')
          : data.errors.length > 0
            ? data.errors.join('\n')
            : 'Część operacji nie została zaimportowana',
      )
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
          <div className="flex items-center gap-1.5">
            <Label className="text-white/70 text-xs">Format banku *</Label>
            {selectedParserName && PARSER_INSTRUCTIONS[selectedParserName] && (
              <button
                type="button"
                aria-label="Pokaż instrukcję przygotowania pliku"
                onClick={() => setShowInstructions(true)}
                className="text-sky-400 hover:text-sky-300 transition-colors"
              >
                <Info className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <Select
            value={selectedParserName}
            onValueChange={(value) => {
              const nextParser = parsers.find((parser) => parser.name === value) ?? null
              setSelectedParserName(value)
              setImportMode(getImportModeForParser(nextParser, importMode))
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

        {importModeOptions.length > 0 ? (
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
                {importModeOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <div className="rounded-xl border border-white/10 bg-slate-800/40 px-3 py-2 text-sm text-white/55">
            Ten format obsługuje import transakcji gotówkowych.
          </div>
        )}
      </div>

      {(importMode === 'transactions' || importMode === 'full') && (
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
      )}

      {(importMode === 'brokerage_events' || importMode === 'brokerage_history' || importMode === 'full') && (
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
        <p className="text-sm text-red-400 break-words overflow-hidden whitespace-pre-line">{parsersError || parseError}</p>
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
          disabled={isParsing || isImporting || (importMode === 'brokerage_history' && historyBlockingRows.length > 0)}
          className="bg-emerald-700 hover:bg-emerald-600 text-white gap-2"
        >
          {isImporting ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {isImporting ? 'Importowanie…' : 'Importuj'}
        </Button>
      </div>

      {(importMode === 'transactions' || importMode === 'full') && txRows.length > 0 && (
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
                {normalizedTxRows.map((row, index) => (
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

      {(importMode === 'brokerage_events' || importMode === 'full') && brokerRows.length > 0 && (
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
                {brokerRows.map((row, index) => (
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

      {importMode === 'brokerage_history' && historyRows.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-slate-800/40 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-white/10">
            <p className="text-sm font-medium text-white/85">Podgląd historii BoSSA</p>
            <span className="text-xs text-white/45">{historyRows.length} wierszy</span>
          </div>
          {historyBlockingRows.length > 0 && (
            <div className="border-b border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100 whitespace-pre-line">
              {historyBlockingRows.map(formatHistoryBlockingRow).join('\n')}
            </div>
          )}
          <div className="max-h-72 overflow-auto w-full">
            <table className="w-full text-sm min-w-0">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="px-3 py-2 text-left text-xs text-white/40 font-medium">Data</th>
                  <th className="px-3 py-2 text-left text-xs text-white/40 font-medium">Typ</th>
                  <th className="px-3 py-2 text-left text-xs text-white/40 font-medium">Opis</th>
                  <th className="px-3 py-2 text-right text-xs text-white/40 font-medium">Kwota</th>
                  <th className="px-3 py-2 text-right text-xs text-white/40 font-medium">Saldo po</th>
                </tr>
              </thead>
              <tbody>
                {historyRows.map((row) => (
                  <tr key={`${row.row_number}-${row.trade_at}`} className="border-b border-white/5 last:border-0">
                    <td className="px-3 py-2 text-white/75">{formatDateLabel(row.trade_at)}</td>
                    <td className="px-3 py-2 text-white/75">{row.operation_type}</td>
                    <td className="px-3 py-2 text-white/75">
                      {row.instrument_symbol ? `${row.instrument_symbol} · ` : ''}
                      {row.description}
                      {row.review_reason ? <span className="block text-amber-300/80">{row.review_reason}</span> : null}
                    </td>
                    <td className="px-3 py-2 text-right text-white/75">{row.amount} {row.currency}</td>
                    <td className="px-3 py-2 text-right text-white/75">{row.amount_after} {row.currency}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showInstructions && selectedParserName && PARSER_INSTRUCTIONS[selectedParserName] && (() => {
        const instr = PARSER_INSTRUCTIONS[selectedParserName]?.[importMode]
          ?? PARSER_INSTRUCTIONS[selectedParserName]?.full
          ?? PARSER_INSTRUCTIONS[selectedParserName]?.transactions
        if (!instr) return null
        return (
          <Dialog open={showInstructions} onOpenChange={setShowInstructions}>
            <DialogContent className="bg-slate-900 border-white/10 text-white max-w-md">
              <DialogHeader>
                <DialogTitle className="text-white">{instr.title}</DialogTitle>
                <DialogDescription className="text-white/55 text-xs">
                  Wykonaj poniższe kroki przed wgraniem pliku.
                </DialogDescription>
              </DialogHeader>
              <ol className="space-y-2 text-sm text-white/80 list-decimal list-inside">
                {instr.steps.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ol>
              {instr.columns && (
                <div className="rounded-lg border border-white/10 bg-slate-800/60 px-3 py-2 space-y-1">
                  <p className="text-xs text-white/50 mb-1.5">Wymagane nagłówki kolumn:</p>
                  {instr.columns.map((col) => (
                    <div key={col.name} className="flex gap-2 text-sm">
                      <span className="text-white/40 w-6 shrink-0">{col.label}</span>
                      <code className="text-emerald-300 font-mono text-xs">{col.name}</code>
                    </div>
                  ))}
                </div>
              )}
            </DialogContent>
          </Dialog>
        )
      })()}
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
  const [kind, setKind] = useState<BrokerageKind>('BUY')
  const [quantity, setQuantity] = useState('0')
  const [price, setPrice] = useState('0')
  const [splitRatio, setSplitRatio] = useState('0')
  const [note, setNote] = useState('')
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
    const parsedSplitRatio = toDecimalNumber(splitRatio)
    if (kind === 'SPLIT' && (parsedSplitRatio === null || parsedSplitRatio <= 0)) {
      setError('Podaj dodatni współczynnik splitu')
      return
    }
    if (kind === 'ADJUSTMENT' && !note.trim()) {
      setError('Podaj notatkę korekty')
      return
    }
    setError(undefined)

    startTransition(async () => {
      const normalizedQuantity = kind === 'SPLIT' ? '0' : quantity.trim().replace(',', '.')
      const normalizedPrice = kind === 'SPLIT' ? '0' : price.trim().replace(',', '.')
      const normalizedSplitRatio = kind === 'SPLIT' ? splitRatio.trim().replace(',', '.') : '0'
      const { ok, error: err } = await apiJson('/api/wallet/brokerage/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brokerage_account_id: brokerageAccountId,
          instrument_symbol: instrumentSymbol,
          instrument_mic: mic,
          instrument_name: selectedInstrument?.shortname ?? instrumentSymbol,
          kind,
          quantity: normalizedQuantity,
          price: normalizedPrice,
          currency,
          split_ratio: normalizedSplitRatio,
          note: note.trim() || null,
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
          <Select value={kind} onValueChange={(value: BrokerageKind) => setKind(value)}>
            <SelectTrigger className="bg-slate-800 border-white/10 text-white text-sm h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-white/10 text-white">
              <SelectItem value="BUY">BUY</SelectItem>
              <SelectItem value="SELL">SELL</SelectItem>
              <SelectItem value="DIV">DIV</SelectItem>
              <SelectItem value="SPLIT">SPLIT</SelectItem>
              <SelectItem value="ADJUSTMENT">Korekta</SelectItem>
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

      {kind === 'SPLIT' ? (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Współczynnik splitu</Label>
          <Input
            value={splitRatio}
            onChange={(event) => setSplitRatio(event.target.value)}
            inputMode="decimal"
            placeholder="2 lub 0.1"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">{kind === 'ADJUSTMENT' ? 'Ilość po korekcie' : 'Ilość'}</Label>
            <Input
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              inputMode="decimal"
              className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-white/70 text-xs">{kind === 'ADJUSTMENT' ? 'Śr. cena po korekcie' : 'Cena / kwota'}</Label>
            <Input
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              inputMode="decimal"
              className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
            />
          </div>
        </div>
      )}

      {kind === 'ADJUSTMENT' && (
        <div className="space-y-1">
          <Label className="text-white/70 text-xs">Notatka korekty *</Label>
          <Input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            placeholder="np. stara nazwa: WORKSERV"
            className="bg-slate-800 border-white/10 text-white placeholder:text-white/30 h-8 text-sm"
          />
        </div>
      )}

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
