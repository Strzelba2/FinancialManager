import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import { createBrokerageEvent, importBrokerageEvents, importBrokerageHistory } from '@/lib/api/wallet'
import { POST as postBrokerageEvent } from '@/app/api/wallet/brokerage/event/route'
import { POST as postBrokerageImport } from '@/app/api/wallet/brokerage/events/import/route'
import { POST as postBrokerageHistoryImport } from '@/app/api/wallet/brokerage/history/import/route'
import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  createBrokerageEvent: vi.fn(),
  importBrokerageEvents: vi.fn(),
  importBrokerageHistory: vi.fn(),
}))

function jsonRequest(url: string, body: unknown) {
  return new NextRequest(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

const BASE_EVENT = {
  brokerage_account_id: '11111111-1111-4111-8111-111111111111',
  instrument_symbol: 'PKOBP',
  instrument_mic: 'XWAR',
  instrument_name: 'PKO BP SA',
  quantity: '0',
  price: '0',
  currency: 'PLN',
  split_ratio: '2.0000000000',
  trade_at: '2026-06-04T09:00:00.000Z',
}

describe('wallet brokerage route handlers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('accepts manual SPLIT brokerage event payloads', async () => {
    await nextUiUnitStory('Wallet brokerage route accepts manual split events', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-route', 'split', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createBrokerageEvent).mockResolvedValue({ ok: true, data: { id: 'event-1' }, status: 200 })

    const payload = { ...BASE_EVENT, kind: 'SPLIT', note: null }
    const response = await postBrokerageEvent(jsonRequest('http://localhost/api/wallet/brokerage/event', payload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ success: true, data: { id: 'event-1' } })
    expect(createBrokerageEvent).toHaveBeenCalledWith('user-1', payload)
  })

  it('accepts manual CONVERSION brokerage event payloads with a target instrument', async () => {
    await nextUiUnitStory('Wallet brokerage route accepts manual instrument conversion events', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-route', 'conversion', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createBrokerageEvent).mockResolvedValue({ ok: true, data: { id: 'event-2' }, status: 200 })

    const payload = {
      ...BASE_EVENT,
      instrument_symbol: 'WORK',
      instrument_name: 'WORKSERV SA',
      kind: 'CONVERSION',
      quantity: '1000',
      split_ratio: '0.2',
      note: 'WORKSERV -> GIGROUP, scalenie 1:5',
      target_instrument_symbol: 'GIG',
      target_instrument_mic: 'XWAR',
      target_instrument_name: 'GIGROUP SA',
    }
    const response = await postBrokerageEvent(jsonRequest('http://localhost/api/wallet/brokerage/event', payload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ success: true, data: { id: 'event-2' } })
    expect(createBrokerageEvent).toHaveBeenCalledWith('user-1', payload)
  })

  it('rejects manual ADJUSTMENT events without an audit note', async () => {
    await nextUiUnitStory('Wallet brokerage route requires notes for adjustment events', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-route', 'adjustment', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const response = await postBrokerageEvent(jsonRequest('http://localhost/api/wallet/brokerage/event', {
      ...BASE_EVENT,
      kind: 'ADJUSTMENT',
      note: '',
    }))

    expect(response.status).toBe(422)
    await expect(response.json()).resolves.toEqual({ error: 'Podaj notatkę korekty' })
    expect(createBrokerageEvent).not.toHaveBeenCalled()
  })

  it('rejects manual CONVERSION events without a target instrument', async () => {
    await nextUiUnitStory('Wallet brokerage route requires target instrument for conversion events', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-route', 'conversion', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const response = await postBrokerageEvent(jsonRequest('http://localhost/api/wallet/brokerage/event', {
      ...BASE_EVENT,
      kind: 'CONVERSION',
      note: 'WORKSERV -> GIGROUP',
      target_instrument_symbol: '',
      target_instrument_mic: '',
    }))

    expect(response.status).toBe(422)
    await expect(response.json()).resolves.toEqual({ error: 'Podaj symbol instrumentu docelowego' })
    expect(createBrokerageEvent).not.toHaveBeenCalled()
  })

  it('accepts ADJUSTMENT brokerage import rows with audit notes', async () => {
    await nextUiUnitStory('Wallet brokerage import route accepts adjustment rows with notes', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-route', 'adjustment', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(importBrokerageEvents).mockResolvedValue({
      ok: true,
      data: { total: 1, created: 1, cash_transactions_created: 0, skipped_duplicates: 0, needs_review: 0, failed: 0, errors: [], rows: [] },
      status: 200,
    })

    const payload = {
      brokerage_account_id: BASE_EVENT.brokerage_account_id,
      events: [
        {
          ...BASE_EVENT,
          kind: 'ADJUSTMENT',
          quantity: '25.00',
          price: '8.00',
          split_ratio: '0',
          note: 'Korekta po scaleniu, stara nazwa: ELZAB',
        },
      ],
    }
    const expectedPayload = {
      brokerage_account_id: BASE_EVENT.brokerage_account_id,
      events: [
        {
          trade_at: BASE_EVENT.trade_at,
          instrument_symbol: BASE_EVENT.instrument_symbol,
          instrument_mic: BASE_EVENT.instrument_mic,
          instrument_name: BASE_EVENT.instrument_name,
          kind: 'ADJUSTMENT',
          quantity: '25.00',
          price: '8.00',
          currency: BASE_EVENT.currency,
          split_ratio: '0',
          note: 'Korekta po scaleniu, stara nazwa: ELZAB',
        },
      ],
    }
    const response = await postBrokerageImport(jsonRequest('http://localhost/api/wallet/brokerage/events/import', payload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      total: 1,
      created: 1,
      cash_transactions_created: 0,
      skipped_duplicates: 0,
      needs_review: 0,
      failed: 0,
      errors: [],
      rows: [],
    })
    expect(importBrokerageEvents).toHaveBeenCalledWith('user-1', expectedPayload)
  })

  it('returns detailed validation errors for invalid brokerage import rows', async () => {
    await nextUiUnitStory('Wallet brokerage import route returns field-level validation detail', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-route', 'validation', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const response = await postBrokerageImport(jsonRequest('http://localhost/api/wallet/brokerage/events/import', {
      brokerage_account_id: BASE_EVENT.brokerage_account_id,
      events: [
        {
          ...BASE_EVENT,
          kind: 'ADJUSTMENT',
          note: '',
        },
      ],
    }))

    expect(response.status).toBe(422)
    const body = await response.json()
    expect(body.error).toContain('events.0.note: Podaj notatkę korekty')
    expect(importBrokerageEvents).not.toHaveBeenCalled()
  })

  it('returns backend errors from brokerage event import without hiding the cause', async () => {
    await nextUiUnitStory('Wallet brokerage import route forwards backend import errors', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-route', 'error-state', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(importBrokerageEvents).mockResolvedValue({
      ok: false,
      error: 'Cannot sell more than holding quantity.',
      status: 400,
    })

    const response = await postBrokerageImport(jsonRequest('http://localhost/api/wallet/brokerage/events/import', {
      brokerage_account_id: BASE_EVENT.brokerage_account_id,
      events: [{ ...BASE_EVENT, kind: 'BUY' }],
    }))

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({ error: 'Cannot sell more than holding quantity.' })
  })

  it('accepts a CHF brokerage event with base settlement currency and FX rate', async () => {
    await nextUiUnitStory('Wallet brokerage import route accepts non-base instrument currency with settlement + fx rate', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'api-route', 'saxo', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(importBrokerageEvents).mockResolvedValue({
      ok: true,
      data: { total: 1, created: 1, cash_transactions_created: 0, skipped_duplicates: 0, needs_review: 0, failed: 0, errors: [], rows: [] },
      status: 200,
    })

    const event = {
      ...BASE_EVENT,
      instrument_symbol: 'UHRN',
      instrument_mic: 'XSWX',
      instrument_name: 'Swatch Group AG',
      kind: 'BUY',
      quantity: '14',
      price: '30.80',
      currency: 'CHF',
      split_ratio: '0',
      settlement_currency: 'PLN',
      fx_rate: '4.598222',
    }
    const payload = { brokerage_account_id: BASE_EVENT.brokerage_account_id, events: [event] }
    const response = await postBrokerageImport(jsonRequest('http://localhost/api/wallet/brokerage/events/import', payload))

    expect(response.status).toBe(200)
    // CHF currency + settlement_currency + fx_rate must pass validation and be forwarded intact.
    expect(importBrokerageEvents).toHaveBeenCalledWith('user-1', {
      brokerage_account_id: BASE_EVENT.brokerage_account_id,
      events: [
        {
          trade_at: BASE_EVENT.trade_at,
          instrument_symbol: 'UHRN',
          instrument_mic: 'XSWX',
          instrument_name: 'Swatch Group AG',
          kind: 'BUY',
          quantity: '14',
          price: '30.80',
          currency: 'CHF',
          split_ratio: '0',
          settlement_currency: 'PLN',
          fx_rate: '4.598222',
        },
      ],
    })
  })

  it('accepts BoSSA full brokerage history rows with amount_after balance checks', async () => {
    await nextUiUnitStory('Wallet brokerage history route accepts BoSSA cash rows with balance after', {
      severity: 'critical',
      tags: ['wallet', 'brokerage', 'bossa', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(importBrokerageHistory).mockResolvedValue({
      ok: true,
      data: { total: 1, created: 1, cash_transactions_created: 1, skipped_duplicates: 0, needs_review: 0, failed: 0, errors: [], rows: [] },
      status: 200,
    })

    const payload = {
      brokerage_account_id: BASE_EVENT.brokerage_account_id,
      rows: [
        {
          row_number: 2,
          operation_type: 'TRANSFER',
          trade_at: '2026-06-04T10:00:00.000Z',
          currency: 'PLN',
          amount: '1000.00',
          amount_after: '1000.00',
          description: 'Przelew do DM BOŚ PLN',
        },
      ],
    }
    const response = await postBrokerageHistoryImport(jsonRequest('http://localhost/api/wallet/brokerage/history/import', payload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      total: 1,
      created: 1,
      cash_transactions_created: 1,
      skipped_duplicates: 0,
      needs_review: 0,
      failed: 0,
      errors: [],
      rows: [],
    })
    expect(importBrokerageHistory).toHaveBeenCalledWith('user-1', payload)
  })
})
