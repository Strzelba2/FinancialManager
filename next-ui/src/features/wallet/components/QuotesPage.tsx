'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import {
  Search, RefreshCw, TrendingUp, TrendingDown,
  ChevronUp, ChevronDown as ChevdownIcon, Minus,
  MoreVertical, Bell, BarChart2, Star, FileText,
  Plus, Save, LoaderCircle,
} from 'lucide-react'
import type { QuoteRow } from '@/lib/api/stock'
import { FavoritesDialog } from './FavoritesDialog'
import { PriceAlertModal, type PriceAlertModalData } from './PriceAlertModal'

const MIC_LABELS: Record<string, string> = {
  XWAR: 'GPW',
  XNCO: 'NewConnect',
  STCM: 'RAW',
  PLNC: 'PLN',
  GLIX: 'Indeksy',
}

const MICS = ['XWAR', 'XNCO', 'STCM', 'PLNC', 'GLIX'] as const
const DEFAULT_MARKETS = MICS.map((marketMic) => ({
  mic: marketMic,
  name: MIC_LABELS[marketMic] ?? marketMic,
}))
const AUTO_REFRESH_MS = 10 * 60 * 1000
const INGEST_POLL_MS = 2_000
const NO_QUOTES_MESSAGE = 'Brak ostatnich notowań dla tego rynku. Auto-odświeżanie zostało wstrzymane.'

type SortField = 'symbol' | 'name' | 'lastPrice' | 'changePct' | 'volume'
type SortDir = 'asc' | 'desc'
type RefreshStartResponse = {
  ok: boolean
  mode?: 'reload' | 'ingest'
  detail?: string
  workers?: string[]
  alreadyRunning?: boolean
  error?: string
}
type RefreshStatusResponse = {
  state?: 'idle' | 'running' | 'done' | 'error'
  detail?: string
  started_at?: string
  processed?: string | number
  quote_source_processed?: string | number
  quote_source_failed?: string | number
  quote_source_errors?: Array<{ symbol?: string; mic?: string; detail?: string }>
  error?: string
}
type MarketOption = {
  mic: string
  name: string
}
type Currency = 'PLN' | 'USD' | 'EUR' | 'GBP' | 'CHF'
type MarketForm = {
  mic: string
  name: string
  country: string
  timezone: string
  active: boolean
  currency: Currency
}
type InstrumentForm = {
  market_mic: string
  symbol: string
  shortname: string
  name: string
  type: string
  status: string
  currency: Currency
  isin: string
  historical_source: string
  quote_source: string
}

function sortRows(rows: QuoteRow[], field: SortField, dir: SortDir): QuoteRow[] {
  return [...rows].sort((a, b) => {
    const av = a[field] ?? ''
    const bv = b[field] ?? ''
    if (typeof av === 'string') {
      return dir === 'asc'
        ? (av as string).localeCompare(bv as string)
        : (bv as string).localeCompare(av as string)
    }
    return dir === 'asc' ? (av as number) - (bv as number) : (bv as number) - (av as number)
  })
}

function SortIcon({ field, current, dir }: { field: SortField; current: SortField; dir: SortDir }) {
  if (field !== current) return <Minus className="w-3 h-3 text-white/20" />
  return dir === 'asc'
    ? <ChevronUp className="w-3 h-3 text-blue-400" />
    : <ChevdownIcon className="w-3 h-3 text-blue-400" />
}

function countLabel(value: string | number | undefined): number {
  if (value === undefined || value === null || value === '') return 0
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function formatQuoteSourceErrors(errors: RefreshStatusResponse['quote_source_errors']): string | null {
  if (!errors?.length) return null
  const preview = errors.slice(0, 3).map((error) => {
    const label = [error.symbol, error.mic ? `(${error.mic})` : null].filter(Boolean).join(' ')
    return [label, error.detail].filter(Boolean).join(': ')
  }).filter(Boolean)
  if (!preview.length) return null
  const suffix = errors.length > preview.length ? ` oraz ${errors.length - preview.length} więcej` : ''
  return `Błędy ręcznych źródeł notowań: ${preview.join('; ')}${suffix}`
}

function ThBtn({
  label, field, sort, dir, onSort, className = 'text-right',
}: {
  label: string; field: SortField; sort: SortField; dir: SortDir
  onSort: (f: SortField) => void; className?: string
}) {
  return (
    <button
      onClick={() => onSort(field)}
      className={`flex items-center gap-1 text-xs text-white/40 uppercase tracking-wide hover:text-white/70 transition-colors ${className}`}
    >
      {label}
      <SortIcon field={field} current={sort} dir={dir} />
    </button>
  )
}

function RowMenu({
  symbol, mic, top, right, onClose, onFavorites, onAlert,
}: {
  symbol: string; mic: string; top: number; right: number
  onClose: () => void; onFavorites: () => void; onAlert: () => void
}) {
  const router = useRouter()
  const canOpenReport = mic !== 'STCM'
  return (
    <div
      style={{ position: 'fixed', top, right, zIndex: 9999 }}
      className="bg-slate-900 border border-white/10 rounded-xl shadow-xl py-1 min-w-[160px] backdrop-blur-md"
      data-row-menu
      onClick={(e) => e.stopPropagation()}
    >
      <button
        className="w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
        onClick={() => { onClose(); onAlert() }}
      >
        <Bell className="w-4 h-4" />
        Utwórz alert
      </button>
      <button
        className="w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
        onClick={() => {
          onClose()
          const qs = new URLSearchParams({ symbol })
          router.push(`/stock/charts/${mic}?${qs.toString()}`)
        }}
      >
        <BarChart2 className="w-4 h-4" />
        Wykresy
      </button>
      {canOpenReport && (
        <button
          className="w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
          onClick={() => {
            onClose()
            router.push(`/stock/${encodeURIComponent(mic)}/${encodeURIComponent(symbol)}/report`)
          }}
        >
          <FileText className="w-4 h-4" />
          Raport AI
        </button>
      )}
      <div className="my-1 border-t border-white/5" />
      <button
        className="w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
        onClick={() => { onClose(); onFavorites() }}
      >
        <Star className="w-4 h-4" />
        Ulubione
      </button>
    </div>
  )
}

type Props = {
  mic: string
  initialRows: QuoteRow[]
}

export function QuotesPage({ mic, initialRows }: Props) {
  const router = useRouter()

  const [rows, setRows] = useState<QuoteRow[]>(initialRows)
  const [allMarketOptions, setAllMarketOptions] = useState<MarketOption[]>(DEFAULT_MARKETS)
  const [quoteMarketOptions, setQuoteMarketOptions] = useState<MarketOption[]>(DEFAULT_MARKETS)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<SortField>('symbol')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [openMenu, setOpenMenu] = useState<{ symbol: string; top: number; right: number } | null>(null)
  const [favoritesTarget, setFavoritesTarget] = useState<{ symbol: string; name: string | null } | null>(null)
  const [alertTarget, setAlertTarget] = useState<{ symbol: string; name: string; alert: PriceAlertModalData | null } | null>(null)
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(initialRows.length > 0)
  const [refreshMessage, setRefreshMessage] = useState<string | null>(
    initialRows.length > 0 ? null : NO_QUOTES_MESSAGE,
  )
  const [showMarketDialog, setShowMarketDialog] = useState(false)
  const [showInstrumentDialog, setShowInstrumentDialog] = useState(false)
  const [stockFormError, setStockFormError] = useState<string | null>(null)
  const [savingStockForm, setSavingStockForm] = useState(false)
  const [editingNameSymbol, setEditingNameSymbol] = useState<string | null>(null)
  const [editNameValue, setEditNameValue] = useState('')
  const [pendingNames, setPendingNames] = useState<Record<string, string>>({})
  const [savingNames, setSavingNames] = useState<Record<string, boolean>>({})
  const editNameInputRef = useRef<HTMLInputElement>(null)
  const [marketForm, setMarketForm] = useState<MarketForm>({
    mic: '',
    name: '',
    country: '',
    timezone: 'Europe/Warsaw',
    active: true,
    currency: 'PLN',
  })
  const [instrumentForm, setInstrumentForm] = useState<InstrumentForm>({
    market_mic: mic,
    symbol: '',
    shortname: '',
    name: '',
    type: 'ETF',
    status: 'ACTIVE',
    currency: 'USD',
    isin: '',
    historical_source: '',
    quote_source: '',
  })

  const [flashMap, setFlashMap] = useState<Record<string, 'up' | 'down'>>({})
  const prevPricesRef = useRef<Record<string, number>>({})
  const fetchInFlightRef = useRef(false)
  const ingestPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const ingestPollInFlightRef = useRef(false)

  useEffect(() => {
    if (!editingNameSymbol) return
    editNameInputRef.current?.focus()
    editNameInputRef.current?.select()
  }, [editingNameSymbol])

  const stopIngestPolling = useCallback(() => {
    if (ingestPollRef.current !== null) {
      clearInterval(ingestPollRef.current)
      ingestPollRef.current = null
    }
    ingestPollInFlightRef.current = false
  }, [])

  const loadMarkets = useCallback(async () => {
    const normalizeMarkets = (payload: MarketOption[]) => (
      payload
        .map((market) => ({
          mic: (market.mic || '').trim().toUpperCase(),
          name: (market.name || '').trim(),
        }))
        .filter((market) => market.mic)
    )

    try {
      const [allResponse, quoteResponse] = await Promise.all([
        fetch('/api/stock/markets', { cache: 'no-store' }),
        fetch('/api/stock/markets?only_with_instruments=true', { cache: 'no-store' }),
      ])
      const allPayload = await allResponse.json().catch(() => null) as MarketOption[] | { error?: string } | null
      const quotePayload = await quoteResponse.json().catch(() => null) as MarketOption[] | { error?: string } | null

      if (allResponse.ok && Array.isArray(allPayload)) {
        const markets = normalizeMarkets(allPayload)
        if (markets.length > 0) setAllMarketOptions(markets)
      }
      if (quoteResponse.ok && Array.isArray(quotePayload)) {
        const markets = normalizeMarkets(quotePayload)
        if (markets.length > 0) setQuoteMarketOptions(markets)
      }
    } catch {
      /* keep defaults */
    }
  }, [])

  useEffect(() => {
    void loadMarkets()
  }, [loadMarkets])

  useEffect(() => {
    setInstrumentForm((current) => ({ ...current, market_mic: mic }))
  }, [mic])

  const applyRows = useCallback((data: QuoteRow[]) => {
    const newFlash: Record<string, 'up' | 'down'> = {}
    const prev = prevPricesRef.current

    for (const r of data) {
      const old = prev[r.symbol]
      if (old != null && Math.abs(old - r.lastPrice) > 1e-9) {
        newFlash[r.symbol] = r.lastPrice > old ? 'up' : 'down'
      }
      prev[r.symbol] = r.lastPrice
    }

    setRows(data)
    setLastRefresh(new Date())
    setAutoRefreshEnabled(true)
    setRefreshMessage(null)

    if (Object.keys(newFlash).length > 0) {
      setFlashMap(newFlash)
      setTimeout(() => setFlashMap({}), 700)
    }
  }, [])

  const clearRows = useCallback((message: string = NO_QUOTES_MESSAGE) => {
    prevPricesRef.current = {}
    setRows([])
    setLastRefresh(null)
    setFlashMap({})
    setAutoRefreshEnabled(false)
    setRefreshMessage(message)
  }, [])

  const fetchRows = useCallback(async (targetMic: string, options?: { manual?: boolean }) => {
    if (fetchInFlightRef.current) return false

    fetchInFlightRef.current = true
    setLoading(true)

    try {
      const res = await fetch(`/api/stock/quotes?mic=${encodeURIComponent(targetMic)}`, {
        cache: 'no-store',
      })
      const payload = await res.json().catch(() => null) as QuoteRow[] | { error?: string } | null

      if (!res.ok) {
        const error = payload && !Array.isArray(payload) ? payload.error : undefined

        if (res.status === 404) {
          clearRows(NO_QUOTES_MESSAGE)
          if (options?.manual) {
            toast.warning('Brak ostatnich notowań dla wybranego rynku')
          }
          return false
        }

        const message = error ?? 'Nie udało się pobrać notowań'
        setAutoRefreshEnabled(false)
        setRefreshMessage(`${message}. Auto-odświeżanie zostało wstrzymane.`)
        if (options?.manual) {
          toast.error(message)
        }
        return false
      }

      const data = Array.isArray(payload) ? payload : []
      if (data.length === 0) {
        clearRows(NO_QUOTES_MESSAGE)
        if (options?.manual) {
          toast.warning('Brak ostatnich notowań dla wybranego rynku')
        }
        return false
      }

      applyRows(data)
      return true
    } catch {
      setAutoRefreshEnabled(false)
      setRefreshMessage('Nie udało się pobrać notowań. Auto-odświeżanie zostało wstrzymane.')
      if (options?.manual) {
        toast.error('Nie udało się pobrać notowań')
      }
      return false
    } finally {
      fetchInFlightRef.current = false
      setLoading(false)
    }
  }, [applyRows, clearRows])

  const startIngestPolling = useCallback((targetMic: string) => {
    stopIngestPolling()

    ingestPollRef.current = setInterval(async () => {
      if (ingestPollInFlightRef.current) return
      ingestPollInFlightRef.current = true

      try {
        const res = await fetch('/api/stock/refresh', { cache: 'no-store' })
        const payload = await res.json().catch(() => null) as RefreshStatusResponse | null

        if (!res.ok) {
          const message = payload?.error ?? 'Nie udało się sprawdzić statusu odświeżania'
          stopIngestPolling()
          setRefreshing(false)
          setRefreshMessage(message)
          toast.error(message)
          return
        }

        const state = payload?.state ?? 'idle'
        if (state === 'running' || state === 'idle') {
          setRefreshMessage('Trwa odświeżanie notowań…')
          return
        }

        if (state === 'error') {
          const detail = payload?.detail?.trim()
          stopIngestPolling()
          setRefreshing(false)
          setRefreshMessage(detail ? `Odświeżanie nie powiodło się: ${detail}` : 'Odświeżanie nie powiodło się')
          toast.error(detail ? `Odświeżanie nie powiodło się: ${detail}` : 'Odświeżanie nie powiodło się')
          return
        }

        stopIngestPolling()
        setRefreshing(false)
        const loaded = await fetchRows(targetMic)
        if (loaded) {
          const manualOk = countLabel(payload?.quote_source_processed)
          const manualFailed = countLabel(payload?.quote_source_failed)
          const manualSuffix = manualOk || manualFailed
            ? ` Ręczne: ${manualOk}, błędów: ${manualFailed}.`
            : ''
          toast.success(`Notowania zostały odświeżone.${manualSuffix}`)
        } else {
          const manualErrorMessage = formatQuoteSourceErrors(payload?.quote_source_errors)
          const message = manualErrorMessage ?? 'Odświeżanie zakończone, ale nadal brak ostatnich notowań'
          setRefreshMessage(message)
          toast.warning(message)
        }
      } finally {
        ingestPollInFlightRef.current = false
      }
    }, INGEST_POLL_MS)
  }, [fetchRows, stopIngestPolling])

  const handleManualRefresh = useCallback(async () => {
    stopIngestPolling()
    setRefreshing(true)
    setRefreshMessage('Sprawdzanie trybu odświeżania…')

    try {
      const res = await fetch('/api/stock/refresh', {
        method: 'POST',
        cache: 'no-store',
      })
      const payload = await res.json().catch(() => null) as RefreshStartResponse | null

      if (!res.ok) {
        const message = payload?.error ?? 'Nie udało się uruchomić odświeżania notowań'
        setRefreshing(false)
        setRefreshMessage(message)
        toast.error(message)
        return
      }

      if (payload?.mode === 'reload') {
        const workers = payload.workers?.length ? ` (${payload.workers.join(', ')})` : ''
        toast.info(`Worker online${workers}. Pobieram notowania…`)
        const loaded = await fetchRows(mic, { manual: true })
        if (loaded) {
          toast.success('Notowania zostały pobrane')
        }
        setRefreshing(false)
        return
      }

      setAutoRefreshEnabled(false)
      setRefreshMessage(
        payload?.alreadyRunning
          ? 'Odświeżanie notowań już trwa…'
          : 'Uruchomiono odświeżanie notowań. To może potrwać kilka minut.',
      )
      toast.info(
        payload?.alreadyRunning
          ? 'Odświeżanie notowań już trwa. Czekam na wynik…'
          : 'Uruchomiono odświeżanie notowań. Czekam na wynik…',
      )
      startIngestPolling(mic)
    } catch {
      setRefreshing(false)
      setRefreshMessage('Nie udało się uruchomić odświeżania notowań')
      toast.error('Nie udało się uruchomić odświeżania notowań')
    }
  }, [fetchRows, mic, startIngestPolling, stopIngestPolling])

  const handleCreateMarket = useCallback(async () => {
    setStockFormError(null)
    setSavingStockForm(true)
    try {
      const response = await fetch('/api/stock/markets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...marketForm,
          mic: marketForm.mic.trim().toUpperCase(),
        }),
      })
      const payload = await response.json().catch(() => null) as { error?: string; mic?: string } | null
      if (!response.ok) {
        setStockFormError(payload?.error ?? 'Nie udało się dodać marketu')
        return
      }
      toast.success('Market został dodany')
      setShowMarketDialog(false)
      setMarketForm({
        mic: '',
        name: '',
        country: '',
        timezone: 'Europe/Warsaw',
        active: true,
        currency: 'PLN',
      })
      await loadMarkets()
    } catch {
      setStockFormError('Nie udało się dodać marketu')
    } finally {
      setSavingStockForm(false)
    }
  }, [loadMarkets, marketForm])

  const handleCreateInstrument = useCallback(async () => {
    setStockFormError(null)
    setSavingStockForm(true)
    try {
      const response = await fetch('/api/stock/instruments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...instrumentForm,
          market_mic: instrumentForm.market_mic.trim().toUpperCase(),
          symbol: instrumentForm.symbol.trim().toUpperCase(),
          shortname: instrumentForm.shortname.trim().toUpperCase(),
          name: instrumentForm.name.trim() || null,
          isin: instrumentForm.isin.trim() || null,
          historical_source: instrumentForm.historical_source.trim() || null,
          quote_source: instrumentForm.quote_source.trim() || null,
        }),
      })
      const payload = await response.json().catch(() => null) as { error?: string } | null
      if (!response.ok) {
        setStockFormError(payload?.error ?? 'Nie udało się dodać instrumentu')
        return
      }
      toast.success('Instrument został dodany')
      setShowInstrumentDialog(false)
      setInstrumentForm({
        market_mic: mic,
        symbol: '',
        shortname: '',
        name: '',
        type: 'ETF',
        status: 'ACTIVE',
        currency: 'USD',
        isin: '',
        historical_source: '',
        quote_source: '',
      })
      await loadMarkets()
      await fetchRows(mic, { manual: true })
    } catch {
      setStockFormError('Nie udało się dodać instrumentu')
    } finally {
      setSavingStockForm(false)
    }
  }, [fetchRows, instrumentForm, loadMarkets, mic])

  useEffect(() => {
    stopIngestPolling()
    setRefreshing(false)

    const prev: Record<string, number> = {}
    for (const r of initialRows) prev[r.symbol] = r.lastPrice
    prevPricesRef.current = prev
    setRows(initialRows)
    setLastRefresh(initialRows.length > 0 ? new Date() : null)
    setAutoRefreshEnabled(initialRows.length > 0)
    setRefreshMessage(initialRows.length > 0 ? null : NO_QUOTES_MESSAGE)
    setEditingNameSymbol(null)
    setPendingNames({})
  }, [initialRows, stopIngestPolling])

  useEffect(() => {
    if (!autoRefreshEnabled || refreshing) return

    const id = setInterval(() => {
      void fetchRows(mic)
    }, AUTO_REFRESH_MS)

    return () => clearInterval(id)
  }, [autoRefreshEnabled, fetchRows, mic, refreshing])

  useEffect(() => () => stopIngestPolling(), [stopIngestPolling])

  useEffect(() => {
    if (!openMenu) return
    function handler(e: MouseEvent) {
      const target = e.target as HTMLElement
      if (!target.closest('[data-row-menu]')) setOpenMenu(null)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [openMenu])

  const handleSort = (field: SortField) => {
    if (field === sort) setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    else { setSort(field); setSortDir('asc') }
  }

  const startNameEdit = (row: QuoteRow) => {
    setEditingNameSymbol(row.symbol)
    setEditNameValue(pendingNames[row.symbol] ?? row.name ?? row.symbol)
  }

  const commitNameEdit = (row: QuoteRow) => {
    const nextName = editNameValue.trim()
    const persistedName = rows.find((item) => item.symbol === row.symbol)?.name ?? ''
    setEditingNameSymbol(null)
    if (!nextName) {
      toast.error('Nazwa instrumentu nie może być pusta')
      return
    }

    setPendingNames((current) => {
      const next = { ...current }
      if (nextName === persistedName) delete next[row.symbol]
      else next[row.symbol] = nextName
      return next
    })
  }

  const saveInstrumentName = async (row: QuoteRow) => {
    const name = pendingNames[row.symbol]
    if (!name || savingNames[row.symbol]) return

    setSavingNames((current) => ({ ...current, [row.symbol]: true }))
    try {
      const response = await fetch(`/api/wallet/instruments/${encodeURIComponent(row.symbol)}/name`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mic, name }),
      })
      const payload = await response.json().catch(() => null) as { name?: string; error?: string } | null
      if (!response.ok || !payload?.name) {
        toast.error(payload?.error ?? 'Nie udało się zapisać nazwy instrumentu')
        return
      }

      setRows((current) => current.map((item) => (
        item.symbol === row.symbol ? { ...item, name: payload.name ?? item.name } : item
      )))
      setPendingNames((current) => {
        const next = { ...current }
        delete next[row.symbol]
        return next
      })
      toast.success('Nazwa instrumentu została zapisana')
    } catch {
      toast.error('Nie udało się połączyć z serwisem')
    } finally {
      setSavingNames((current) => {
        const next = { ...current }
        delete next[row.symbol]
        return next
      })
    }
  }

  const q = query.trim().toLowerCase()
  const displayRows = rows.map((row) => ({
    ...row,
    name: pendingNames[row.symbol] ?? row.name,
  }))
  const filtered = q
    ? displayRows.filter((r) =>
        r.symbol.toLowerCase().includes(q) ||
        (r.name ?? '').toLowerCase().includes(q),
      )
    : displayRows
  const sorted = sortRows(filtered, sort, sortDir)

  const pos = rows.filter((r) => r.changePct >= 0).length
  const neg = rows.filter((r) => r.changePct < 0).length

  const timeFmt = lastRefresh
    ? lastRefresh.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null

  const openAlertModal = useCallback(async (symbol: string, name: string | null) => {
    try {
      const res = await fetch(`/api/wallet/alerts/${encodeURIComponent(symbol)}`, { cache: 'no-store' })
      const payload = await res.json().catch(() => null) as PriceAlertModalData | { error?: string } | null

      if (!res.ok) {
        const message = payload && typeof payload === 'object' && 'error' in payload
          ? (payload.error ?? 'Nie udało się pobrać alertu')
          : 'Nie udało się pobrać alertu'
        toast.error(message)
        return
      }

      const alert = payload && typeof payload === 'object' && 'enabled' in payload ? payload : null
      setAlertTarget({ symbol, name: name ?? symbol, alert })
    } catch {
      toast.error('Błąd połączenia')
    }
  }, [])

  return (
    <>
    {showMarketDialog && (
      <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 px-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-market-title"
          className="w-full max-w-lg rounded-xl border border-white/10 bg-slate-950 p-5 shadow-2xl"
        >
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 id="add-market-title" className="text-lg font-semibold text-white">Dodaj market</h2>
            <button
              type="button"
              onClick={() => setShowMarketDialog(false)}
              className="rounded-lg px-2 py-1 text-white/50 hover:bg-white/10 hover:text-white"
              aria-label="Zamknij formularz marketu"
            >
              ×
            </button>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-xs text-white/50">
              MIC
              <input
                value={marketForm.mic}
                onChange={(event) => setMarketForm((current) => ({ ...current, mic: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="XLON"
              />
            </label>
            <label className="space-y-1 text-xs text-white/50">
              Waluta
              <select
                value={marketForm.currency}
                onChange={(event) => setMarketForm((current) => ({ ...current, currency: event.target.value as Currency }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
              >
                <option value="PLN">PLN</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="CHF">CHF</option>
              </select>
            </label>
            <label className="space-y-1 text-xs text-white/50 sm:col-span-2">
              Nazwa
              <input
                value={marketForm.name}
                onChange={(event) => setMarketForm((current) => ({ ...current, name: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="London Stock Exchange"
              />
            </label>
            <label className="space-y-1 text-xs text-white/50">
              Kraj
              <input
                value={marketForm.country}
                onChange={(event) => setMarketForm((current) => ({ ...current, country: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="UK"
              />
            </label>
            <label className="space-y-1 text-xs text-white/50">
              Strefa czasowa
              <input
                value={marketForm.timezone}
                onChange={(event) => setMarketForm((current) => ({ ...current, timezone: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="Europe/London"
              />
            </label>
          </div>
          {stockFormError && <p className="mt-3 text-sm text-red-400">{stockFormError}</p>}
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowMarketDialog(false)}
              className="rounded-lg px-3 py-2 text-sm text-white/60 hover:bg-white/10 hover:text-white"
            >
              Anuluj
            </button>
            <button
              type="button"
              onClick={handleCreateMarket}
              disabled={savingStockForm}
              className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
            >
              Dodaj market
            </button>
          </div>
        </div>
      </div>
    )}
    {showInstrumentDialog && (
      <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 px-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-instrument-title"
          className="w-full max-w-2xl rounded-xl border border-white/10 bg-slate-950 p-5 shadow-2xl"
        >
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 id="add-instrument-title" className="text-lg font-semibold text-white">Dodaj instrument</h2>
            <button
              type="button"
              onClick={() => setShowInstrumentDialog(false)}
              className="rounded-lg px-2 py-1 text-white/50 hover:bg-white/10 hover:text-white"
              aria-label="Zamknij formularz instrumentu"
            >
              ×
            </button>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="space-y-1 text-xs text-white/50">
              Market
              <select
                value={instrumentForm.market_mic}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, market_mic: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
              >
                {allMarketOptions.map((market) => (
                  <option key={market.mic} value={market.mic}>
                    {market.mic}{market.name ? ` · ${market.name}` : ''}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-xs text-white/50">
              Symbol
              <input
                value={instrumentForm.symbol}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, symbol: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="LNGA.UK"
              />
            </label>
            <label className="space-y-1 text-xs text-white/50">
              Skrót
              <input
                value={instrumentForm.shortname}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, shortname: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="WisdomTree Natural Gas"
              />
            </label>
            <label className="space-y-1 text-xs text-white/50 sm:col-span-2">
              Nazwa
              <input
                value={instrumentForm.name}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, name: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="WisdomTree Natural Gas"
              />
            </label>
            <label className="space-y-1 text-xs text-white/50">
              Waluta
              <select
                value={instrumentForm.currency}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, currency: event.target.value as Currency }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
              >
                <option value="PLN">PLN</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="CHF">CHF</option>
              </select>
            </label>
            <label className="space-y-1 text-xs text-white/50">
              Typ
              <select
                value={instrumentForm.type}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, type: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
              >
                <option value="ETF">ETF</option>
                <option value="STOCK">Akcja</option>
                <option value="BOND">Obligacja</option>
                <option value="COMMODITY">Towar</option>
                <option value="INDEX">Indeks</option>
              </select>
            </label>
            <label className="space-y-1 text-xs text-white/50">
              ISIN
              <input
                value={instrumentForm.isin}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, isin: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="IE00..."
              />
            </label>
            <label className="space-y-1 text-xs text-white/50 sm:col-span-3">
              Źródło notowań
              <input
                value={instrumentForm.quote_source}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, quote_source: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="https://quotes.example.com/q/?s=SYMBOL"
              />
            </label>
            <label className="space-y-1 text-xs text-white/50 sm:col-span-3">
              Źródło historii
              <input
                value={instrumentForm.historical_source}
                onChange={(event) => setInstrumentForm((current) => ({ ...current, historical_source: event.target.value }))}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
                placeholder="https://quotes.example.com/q/d/l/?s=SYMBOL&i=d"
              />
            </label>
          </div>
          {stockFormError && <p className="mt-3 text-sm text-red-400">{stockFormError}</p>}
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowInstrumentDialog(false)}
              className="rounded-lg px-3 py-2 text-sm text-white/60 hover:bg-white/10 hover:text-white"
            >
              Anuluj
            </button>
            <button
              type="button"
              onClick={handleCreateInstrument}
              disabled={savingStockForm}
              className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
            >
              Dodaj instrument
            </button>
          </div>
        </div>
      </div>
    )}
    {alertTarget && (
      <PriceAlertModal
        symbol={alertTarget.symbol}
        name={alertTarget.name}
        initial={alertTarget.alert}
        onClose={() => setAlertTarget(null)}
        onSaved={() => setAlertTarget(null)}
        onDeleted={() => setAlertTarget(null)}
      />
    )}
    {favoritesTarget && (
      <FavoritesDialog
        symbol={favoritesTarget.symbol}
        name={favoritesTarget.name}
        mic={mic}
        onClose={() => setFavoritesTarget(null)}
      />
    )}
    <div className="px-4 py-4">
      <div className="max-w-screen-2xl mx-auto">

        {/* ── Header ── */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl px-5 py-4 mb-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h1 className="text-xl font-semibold text-white">Notowania</h1>
            <div className="flex flex-wrap items-center gap-3">
              {/* Summary chips */}
              <span className="inline-flex items-center gap-1 text-sm px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 tabular-nums">
                <TrendingUp className="w-3.5 h-3.5" />
                +{pos}
              </span>
              <span className="inline-flex items-center gap-1 text-sm px-2.5 py-1 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 tabular-nums">
                <TrendingDown className="w-3.5 h-3.5" />
                −{neg}
              </span>
              {/* Last refresh */}
              {timeFmt && (
                <span className="text-xs text-white/30">
                  Odświeżono: {timeFmt}
                </span>
              )}
              <button
                type="button"
                onClick={() => { setStockFormError(null); setShowMarketDialog(true) }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-700/60 border border-white/10 rounded-lg text-white/60 hover:text-white hover:border-white/20 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Market
              </button>
              <button
                type="button"
                onClick={() => {
                  setStockFormError(null)
                  void loadMarkets()
                  setShowInstrumentDialog(true)
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-700/70 border border-emerald-400/20 rounded-lg text-white hover:bg-emerald-600/80 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Instrument
              </button>
              {/* Manual refresh */}
              <button
                onClick={handleManualRefresh}
                disabled={loading || refreshing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-700/60 border border-white/10 rounded-lg text-white/60 hover:text-white hover:border-white/20 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading || refreshing ? 'animate-spin' : ''}`} />
                Odśwież
              </button>
            </div>
          </div>
          {refreshMessage && (
            <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              {refreshMessage}
            </div>
          )}
        </div>

        {/* ── Filters ── */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl px-4 py-3 mb-4 flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-[180px] max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/30" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Szukaj symbol / nazwa…"
              className="w-full pl-7 pr-3 py-1.5 text-sm bg-slate-900/60 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
            />
          </div>

          <div className="flex-1" />

          {/* Market selector */}
          <div className="flex rounded-lg overflow-hidden border border-white/10">
            {quoteMarketOptions.map((market) => (
              <button
                key={market.mic}
                onClick={() => router.push(`/stock/quotes/${market.mic}`)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  mic === market.mic
                    ? 'bg-blue-600 text-white'
                    : 'text-white/50 hover:text-white hover:bg-white/5'
                }`}
              >
                {MIC_LABELS[market.mic] ?? market.name ?? market.mic}
              </button>
            ))}
          </div>
        </div>

        {/* ── Table ── */}
        <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="px-4 py-3 text-left">
                    <ThBtn label="Symbol" field="symbol" sort={sort} dir={sortDir} onSort={handleSort} className="text-left" />
                  </th>
                  <th className="px-4 py-3 text-left">
                    <ThBtn label="Nazwa" field="name" sort={sort} dir={sortDir} onSort={handleSort} className="text-left" />
                  </th>
                  <th className="px-4 py-3 text-left">
                    <ThBtn label="Kurs" field="lastPrice" sort={sort} dir={sortDir} onSort={handleSort} className="text-left" />
                  </th>
                  <th className="px-4 py-3 text-left">
                    <ThBtn label="Zmiana %" field="changePct" sort={sort} dir={sortDir} onSort={handleSort} className="text-left" />
                  </th>
                  <th className="px-4 py-3 text-left">
                    <ThBtn label="Wolumen" field="volume" sort={sort} dir={sortDir} onSort={handleSort} className="text-left" />
                  </th>
                  <th className="px-4 py-3 text-left">
                    <span className="text-xs text-white/40 uppercase tracking-wide">Ostatni handel</span>
                  </th>
                  <th className="px-4 py-3 w-10" />
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-white/30 text-sm">
                      {loading ? 'Ładowanie…' : refreshMessage ?? 'Brak danych'}
                    </td>
                  </tr>
                )}
                {sorted.map((row) => {
                  const flash = flashMap[row.symbol]
                  const positive = row.changePct >= 0

                  return (
                    <tr
                      key={row.symbol}
                      className={`border-b border-white/5 hover:bg-white/[0.02] transition-colors ${
                        flash === 'up'
                          ? 'bg-emerald-500/10'
                          : flash === 'down'
                          ? 'bg-red-500/10'
                          : ''
                      }`}
                      style={{ transition: flash ? 'background-color 0.1s' : 'background-color 0.7s' }}
                    >
                      <td className="px-4 py-2.5 font-semibold text-white whitespace-nowrap">
                        {row.symbol}
                      </td>
                      <td className="px-4 py-2.5 text-white/70 max-w-[260px]">
                        {editingNameSymbol === row.symbol ? (
                          <input
                            ref={editNameInputRef}
                            value={editNameValue}
                            maxLength={40}
                            onChange={(event) => setEditNameValue(event.target.value)}
                            onBlur={() => commitNameEdit(row)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault()
                                event.currentTarget.blur()
                              }
                              if (event.key === 'Escape') {
                                event.preventDefault()
                                setEditingNameSymbol(null)
                              }
                            }}
                            aria-label={`Edytuj nazwę instrumentu ${row.symbol}`}
                            className="w-full min-w-[180px] rounded border border-blue-500/50 bg-slate-900 px-2 py-1 text-sm text-white outline-none focus:border-blue-400"
                          />
                        ) : (
                          <button
                            type="button"
                            onDoubleClick={() => startNameEdit(row)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === 'F2') {
                                event.preventDefault()
                                startNameEdit(row)
                              }
                            }}
                            aria-label={`Nazwa instrumentu ${row.symbol}: ${row.name ?? '—'}. Kliknij dwukrotnie, aby edytować`}
                            className="block max-w-[260px] truncate text-left text-white/70 hover:text-white focus:outline-none focus:ring-1 focus:ring-blue-400/60"
                          >
                            {row.name ?? '—'}
                          </button>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-left tabular-nums text-white whitespace-nowrap">
                        {row.lastPriceFmt}
                        {row.currency && row.lastPrice > 0 ? ` ${row.currency}` : ''}
                      </td>
                      <td className="px-4 py-2.5 text-left whitespace-nowrap">
                        <span className={`inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded tabular-nums ${
                          positive
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : 'bg-red-500/20 text-red-300'
                        }`}>
                          {positive
                            ? <TrendingUp className="w-3 h-3" />
                            : <TrendingDown className="w-3 h-3" />}
                          {row.changePctFmt}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-left tabular-nums text-white/60 whitespace-nowrap">
                        {row.volume > 0
                          ? row.volume.toLocaleString('pl-PL')
                          : '—'}
                      </td>
                      <td className="px-4 py-2.5 whitespace-nowrap">
                        {row.lastTradeDateFmt ? (
                          <span className="text-white/40">{row.lastTradeDateFmt}</span>
                        ) : null}
                        {row.lastTradeTimeFmt ? (
                          <span className="ml-1.5 font-medium text-blue-400">{row.lastTradeTimeFmt}</span>
                        ) : null}
                        {!row.lastTradeDateFmt && !row.lastTradeTimeFmt && (
                          <span className="text-white/20">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <div className="inline-flex items-center gap-1" data-row-menu>
                          {pendingNames[row.symbol] !== undefined && (
                            <button
                              type="button"
                              onClick={() => void saveInstrumentName(row)}
                              disabled={savingNames[row.symbol]}
                              aria-label={`Zapisz nazwę instrumentu ${row.symbol}`}
                              title="Zapisz nazwę"
                              className="rounded p-1 text-emerald-400 transition-colors hover:bg-emerald-500/10 hover:text-emerald-300 disabled:cursor-wait disabled:opacity-60"
                            >
                              {savingNames[row.symbol]
                                ? <LoaderCircle className="w-4 h-4 animate-spin" />
                                : <Save className="w-4 h-4" />}
                            </button>
                          )}
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              if (openMenu?.symbol === row.symbol) {
                                setOpenMenu(null)
                              } else {
                                const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect()
                                setOpenMenu({ symbol: row.symbol, top: rect.bottom + 4, right: window.innerWidth - rect.right })
                              }
                            }}
                            className="p-1 rounded text-white/30 hover:text-white hover:bg-white/5 transition-colors"
                          >
                            <MoreVertical className="w-4 h-4" />
                          </button>
                          {openMenu?.symbol === row.symbol && (
                            <RowMenu
                              symbol={row.symbol}
                              mic={mic}
                              top={openMenu.top}
                              right={openMenu.right}
                              onClose={() => setOpenMenu(null)}
                              onAlert={() => void openAlertModal(row.symbol, row.name)}
                              onFavorites={() => setFavoritesTarget({ symbol: row.symbol, name: row.name })}
                            />
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Footer */}
          {rows.length > 0 && (
            <div className="px-4 py-2.5 border-t border-white/5 flex items-center justify-between">
              <span className="text-xs text-white/30">
                {sorted.length !== rows.length
                  ? `${sorted.length} z ${rows.length} instrumentów`
                  : `${rows.length} instrumentów`}
              </span>
              <span className="text-xs text-white/20">
                {refreshing
                  ? 'Trwa odświeżanie notowań…'
                  : autoRefreshEnabled
                  ? 'Auto-odświeżanie co 10 min'
                  : 'Auto-odświeżanie wstrzymane'}
              </span>
            </div>
          )}
        </div>

      </div>
    </div>
    </>
  )
}
