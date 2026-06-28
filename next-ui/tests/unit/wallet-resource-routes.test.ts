import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveWalletUserId } from '@/lib/api/session'
import {
  createDebt,
  createMetalHolding,
  createRealEstate,
  createRecurringExpense,
  deleteAlert,
  deleteDebt,
  deleteMetalHolding,
  deleteRealEstate,
  deleteRecurringExpense,
  getAlertBySymbol,
  getMyNote,
  sellMetalHolding,
  sellRealEstate,
  updateDebt,
  updateMetalHolding,
  updateRealEstate,
  updateRecurringExpense,
  upsertAlert,
  upsertMyNote,
} from '@/lib/api/wallet'
import { POST as postDebt } from '@/app/api/wallet/debts/route'
import { DELETE as deleteDebtRoute, PUT as putDebt } from '@/app/api/wallet/debts/[id]/route'
import { GET as getNote, PUT as putNote } from '@/app/api/wallet/notes/route'
import { POST as postMetalHolding } from '@/app/api/wallet/metal-holdings/route'
import {
  DELETE as deleteMetalHoldingRoute,
  PUT as putMetalHolding,
} from '@/app/api/wallet/metal-holdings/[id]/route'
import { POST as sellMetalHoldingRoute } from '@/app/api/wallet/metal-holdings/[id]/sell/route'
import { POST as postRealEstate } from '@/app/api/wallet/real-estates/route'
import {
  DELETE as deleteRealEstateRoute,
  PUT as putRealEstate,
} from '@/app/api/wallet/real-estates/[id]/route'
import { POST as sellRealEstateRoute } from '@/app/api/wallet/real-estates/[id]/sell/route'
import { POST as postRecurringExpense } from '@/app/api/wallet/recurring-expenses/route'
import {
  DELETE as deleteRecurringExpenseRoute,
  PUT as putRecurringExpense,
} from '@/app/api/wallet/recurring-expenses/[id]/route'
import { POST as postAlert } from '@/app/api/wallet/alerts/route'
import { DELETE as deleteAlertRoute, GET as getAlertRoute } from '@/app/api/wallet/alerts/[symbol]/route'
import type { Currency, UserNote } from '@/lib/types/wallet'
import { nextUiUnitStory } from '../allure'

vi.mock('@/lib/api/session', () => ({
  resolveWalletUserId: vi.fn(),
}))

vi.mock('@/lib/api/wallet', () => ({
  createDebt: vi.fn(),
  updateDebt: vi.fn(),
  deleteDebt: vi.fn(),
  getMyNote: vi.fn(),
  upsertMyNote: vi.fn(),
  createMetalHolding: vi.fn(),
  updateMetalHolding: vi.fn(),
  deleteMetalHolding: vi.fn(),
  sellMetalHolding: vi.fn(),
  createRealEstate: vi.fn(),
  updateRealEstate: vi.fn(),
  deleteRealEstate: vi.fn(),
  sellRealEstate: vi.fn(),
  createRecurringExpense: vi.fn(),
  updateRecurringExpense: vi.fn(),
  deleteRecurringExpense: vi.fn(),
  upsertAlert: vi.fn(),
  getAlertBySymbol: vi.fn(),
  deleteAlert: vi.fn(),
}))

function jsonRequest(url: string, body: unknown, method = 'POST') {
  return new NextRequest(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function invalidJsonRequest(url: string, method = 'POST') {
  return new NextRequest(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: '{bad-json',
  })
}

function emptyRequest(url: string, method: string) {
  return new NextRequest(url, { method })
}

function params(id: string) {
  return { params: Promise.resolve({ id }) }
}

function symbolParams(symbol: string) {
  return { params: Promise.resolve({ symbol }) }
}

function userNote(text: string): UserNote {
  return {
    id: 'note-1',
    user_id: 'user-1',
    text,
    created_at: '2026-06-01T10:00:00.000Z',
    updated_at: '2026-06-01T10:00:00.000Z',
  }
}

const debtPayload = {
  wallet_id: '11111111-1111-4111-8111-111111111111',
  name: '  Mortgage  ',
  lander: '  Bank  ',
  amount: '250000.00',
  currency: 'PLN',
  interest_rate_pct: '6.50',
  monthly_payment: '3200.00',
  end_date: '2026-06-30T00:00:00.000Z',
}

const recurringPayload = {
  wallet_id: '11111111-1111-4111-8111-111111111111',
  name: '  Internet  ',
  category: '  Home  ',
  amount: '89.99',
  currency: 'PLN',
  due_day: 10,
  account: '  Main  ',
  note: '  monthly  ',
} satisfies {
  wallet_id: string
  name: string
  category: string
  amount: string
  currency: Currency
  due_day: number
  account: string
  note: string
}

describe('wallet resource route handlers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('validates and trims debt create payloads before forwarding to wallet service', async () => {
    await nextUiUnitStory('Wallet debt route validates and trims create payloads', {
      severity: 'critical',
      tags: ['wallet', 'debts', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createDebt).mockResolvedValue({ ok: true, data: { id: 'debt-1' }, status: 201 })

    const response = await postDebt(jsonRequest('http://localhost/api/wallet/debts', debtPayload))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ success: true })
    expect(createDebt).toHaveBeenCalledWith('user-1', {
      ...debtPayload,
      name: 'Mortgage',
      lander: 'Bank',
    })
  })

  it('rejects invalid debt updates before calling wallet service', async () => {
    await nextUiUnitStory('Wallet debt route rejects invalid update payloads', {
      severity: 'critical',
      tags: ['wallet', 'debts', 'api-route', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const response = await putDebt(
      jsonRequest('http://localhost/api/wallet/debts/debt-1', { ...debtPayload, amount: '' }, 'PUT'),
      params('debt-1'),
    )

    expect(response.status).toBe(422)
    expect(updateDebt).not.toHaveBeenCalled()
  })

  it('maps debt delete failures to the dialog error contract', async () => {
    await nextUiUnitStory('Wallet debt route maps delete failures', {
      severity: 'critical',
      tags: ['wallet', 'debts', 'api-route', 'error-state'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(deleteDebt).mockResolvedValue(false)

    const response = await deleteDebtRoute(
      emptyRequest('http://localhost/api/wallet/debts/debt-1', 'DELETE'),
      params('debt-1'),
    )

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({ error: 'Nie udało się usunąć zobowiązania' })
  })

  it('loads and saves the authenticated user note through wallet service', async () => {
    await nextUiUnitStory('Wallet note route loads and saves the authenticated note', {
      severity: 'normal',
      tags: ['wallet', 'notes', 'api-route'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(getMyNote).mockResolvedValue({
      ok: true,
      data: userNote('plan'),
      status: 200,
    })
    vi.mocked(upsertMyNote).mockResolvedValue({
      ok: true,
      data: userNote('updated plan'),
      status: 200,
    })

    const getResponse = await getNote()
    const putResponse = await putNote(jsonRequest('http://localhost/api/wallet/notes', { text: 'updated plan' }, 'PUT'))

    expect(getResponse.status).toBe(200)
    await expect(getResponse.json()).resolves.toEqual(userNote('plan'))
    expect(putResponse.status).toBe(200)
    await expect(putResponse.json()).resolves.toEqual(userNote('updated plan'))
    expect(upsertMyNote).toHaveBeenCalledWith('user-1', 'updated plan')
  })

  it('rejects malformed note JSON before upserting user note', async () => {
    await nextUiUnitStory('Wallet note route rejects malformed JSON', {
      severity: 'normal',
      tags: ['wallet', 'notes', 'api-route', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')

    const response = await putNote(invalidJsonRequest('http://localhost/api/wallet/notes', 'PUT'))

    expect(response.status).toBe(400)
    expect(upsertMyNote).not.toHaveBeenCalled()
  })

  it('forwards metal holding create, update and sell payloads with authenticated ownership context', async () => {
    await nextUiUnitStory('Wallet metal holding routes forward financial mutation payloads', {
      severity: 'critical',
      tags: ['wallet', 'metal-holdings', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createMetalHolding).mockResolvedValue({ ok: true, data: {}, status: 201 })
    vi.mocked(updateMetalHolding).mockResolvedValue({ ok: true, data: {}, status: 200 })
    vi.mocked(sellMetalHolding).mockResolvedValue({ ok: true, data: { updated: 1 }, status: 200 })

    const createPayload = {
      wallet_id: '11111111-1111-4111-8111-111111111111',
      metal: 'GOLD',
      grams: '10.000000',
      cost_basis: '2500.00',
      cost_currency: 'PLN',
      quote_symbol: 'GC.F',
    }
    const sellPayload = {
      deposit_account_id: '22222222-2222-4222-8222-222222222222',
      grams_sold: '2.000000',
      proceeds_amount: '700.00',
      proceeds_currency: 'PLN',
      create_transaction: true,
    }

    const createResponse = await postMetalHolding(jsonRequest('http://localhost/api/wallet/metal-holdings', createPayload))
    const updateResponse = await putMetalHolding(
      jsonRequest('http://localhost/api/wallet/metal-holdings/metal-1', { grams: '8.000000' }, 'PUT'),
      params('metal-1'),
    )
    const sellResponse = await sellMetalHoldingRoute(
      jsonRequest('http://localhost/api/wallet/metal-holdings/metal-1/sell', sellPayload),
      params('metal-1'),
    )

    expect(createResponse.status).toBe(200)
    expect(updateResponse.status).toBe(200)
    expect(sellResponse.status).toBe(200)
    expect(createMetalHolding).toHaveBeenCalledWith('user-1', createPayload)
    expect(updateMetalHolding).toHaveBeenCalledWith('user-1', 'metal-1', { grams: '8.000000' })
    expect(sellMetalHolding).toHaveBeenCalledWith('user-1', 'metal-1', sellPayload)
  })

  it('maps metal holding delete and update backend failures', async () => {
    await nextUiUnitStory('Wallet metal holding routes map backend failures', {
      severity: 'critical',
      tags: ['wallet', 'metal-holdings', 'api-route', 'error-state'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(updateMetalHolding).mockResolvedValue({ ok: false, error: 'Metal holding not found', status: 404 })
    vi.mocked(deleteMetalHolding).mockResolvedValue(false)

    const updateResponse = await putMetalHolding(
      jsonRequest('http://localhost/api/wallet/metal-holdings/metal-1', { grams: '8.000000' }, 'PUT'),
      params('metal-1'),
    )
    const deleteResponse = await deleteMetalHoldingRoute(
      emptyRequest('http://localhost/api/wallet/metal-holdings/metal-1', 'DELETE'),
      params('metal-1'),
    )

    expect(updateResponse.status).toBe(400)
    await expect(updateResponse.json()).resolves.toEqual({ error: 'Metal holding not found' })
    expect(deleteResponse.status).toBe(400)
    await expect(deleteResponse.json()).resolves.toEqual({ error: 'Nie udało się usunąć pozycji' })
  })

  it('forwards real estate create, update, sell and delete route calls', async () => {
    await nextUiUnitStory('Wallet real estate routes forward asset lifecycle payloads', {
      severity: 'critical',
      tags: ['wallet', 'real-estate', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createRealEstate).mockResolvedValue({ ok: true, data: {}, status: 201 })
    vi.mocked(updateRealEstate).mockResolvedValue({ ok: true, data: {}, status: 200 })
    vi.mocked(sellRealEstate).mockResolvedValue({ ok: true, data: { updated: 1 }, status: 200 })
    vi.mocked(deleteRealEstate).mockResolvedValue(true)

    const createPayload = {
      wallet_id: '11111111-1111-4111-8111-111111111111',
      name: 'Apartment',
      country: 'PL',
      city: 'Warsaw',
      type: 'APARTMENT',
      area_m2: '48.50',
      purchase_price: '650000.00',
      purchase_currency: 'PLN',
    }
    const sellPayload = {
      deposit_account_id: '22222222-2222-4222-8222-222222222222',
      proceeds_amount: '720000.00',
      proceeds_currency: 'PLN',
      create_transaction: true,
    }

    const createResponse = await postRealEstate(jsonRequest('http://localhost/api/wallet/real-estates', createPayload))
    const updateResponse = await putRealEstate(
      jsonRequest('http://localhost/api/wallet/real-estates/real-1', { name: 'New apartment name' }, 'PUT'),
      params('real-1'),
    )
    const sellResponse = await sellRealEstateRoute(
      jsonRequest('http://localhost/api/wallet/real-estates/real-1/sell', sellPayload),
      params('real-1'),
    )
    const deleteResponse = await deleteRealEstateRoute(
      emptyRequest('http://localhost/api/wallet/real-estates/real-1', 'DELETE'),
      params('real-1'),
    )

    expect(createResponse.status).toBe(200)
    expect(updateResponse.status).toBe(200)
    expect(sellResponse.status).toBe(200)
    expect(deleteResponse.status).toBe(200)
    expect(createRealEstate).toHaveBeenCalledWith('user-1', createPayload)
    expect(updateRealEstate).toHaveBeenCalledWith('user-1', 'real-1', { name: 'New apartment name' })
    expect(sellRealEstate).toHaveBeenCalledWith('user-1', 'real-1', sellPayload)
    expect(deleteRealEstate).toHaveBeenCalledWith('user-1', 'real-1')
  })

  it('validates and trims recurring expense create and update payloads', async () => {
    await nextUiUnitStory('Wallet recurring expense routes validate scheduled expense payloads', {
      severity: 'normal',
      tags: ['wallet', 'recurring-expenses', 'api-route', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(createRecurringExpense).mockResolvedValue({
      ok: true,
      data: { id: 'expense-1', ...recurringPayload },
      status: 201,
    })
    vi.mocked(updateRecurringExpense).mockResolvedValue({
      ok: true,
      data: { id: 'expense-1', ...recurringPayload, amount: '99.99' },
      status: 200,
    })

    const createResponse = await postRecurringExpense(jsonRequest('http://localhost/api/wallet/recurring-expenses', recurringPayload))
    const updateResponse = await putRecurringExpense(
      jsonRequest('http://localhost/api/wallet/recurring-expenses/expense-1', { ...recurringPayload, amount: '99.99' }, 'PUT'),
      params('expense-1'),
    )

    expect(createResponse.status).toBe(200)
    expect(updateResponse.status).toBe(200)
    expect(createRecurringExpense).toHaveBeenCalledWith('user-1', {
      ...recurringPayload,
      name: 'Internet',
      category: 'Home',
      account: 'Main',
      note: 'monthly',
    })
    expect(updateRecurringExpense).toHaveBeenCalledWith('user-1', 'expense-1', expect.objectContaining({
      amount: '99.99',
      name: 'Internet',
    }))
  })

  it('rejects invalid recurring expense day and maps delete failure', async () => {
    await nextUiUnitStory('Wallet recurring expense routes reject invalid schedule and failed delete', {
      severity: 'normal',
      tags: ['wallet', 'recurring-expenses', 'api-route', 'error-state'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(deleteRecurringExpense).mockResolvedValue(false)

    const invalidResponse = await postRecurringExpense(jsonRequest('http://localhost/api/wallet/recurring-expenses', {
      ...recurringPayload,
      due_day: 32,
    }))
    const deleteResponse = await deleteRecurringExpenseRoute(
      emptyRequest('http://localhost/api/wallet/recurring-expenses/expense-1', 'DELETE'),
      params('expense-1'),
    )

    expect(invalidResponse.status).toBe(422)
    expect(createRecurringExpense).not.toHaveBeenCalled()
    expect(deleteResponse.status).toBe(400)
    await expect(deleteResponse.json()).resolves.toEqual({ error: 'Nie udało się usunąć wydatku' })
  })

  it('normalizes alert payloads and maps missing-instrument errors for users', async () => {
    await nextUiUnitStory('Wallet alert routes normalize symbols and map missing instrument messages', {
      severity: 'critical',
      tags: ['wallet', 'alerts', 'api-route', 'validation'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(upsertAlert).mockResolvedValue({
      ok: false,
      error: "Instrument not found for symbol='PKO'",
      status: 404,
    })

    const response = await postAlert(jsonRequest('http://localhost/api/wallet/alerts', {
      symbol: ' pko ',
      above_price: '100.00',
    }))

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({
      error: 'Ten instrument nie widnieje na liście ulubionych. Dodaj go najpierw do ulubionych, a dopiero potem ustaw alert.',
    })
    expect(upsertAlert).toHaveBeenCalledWith('user-1', {
      symbol: 'PKO',
      below_price: null,
      above_price: '100.00',
      enabled: true,
      one_shot: false,
      expires_at: null,
    })
  })

  it('gets and deletes alerts by symbol through authenticated route handlers', async () => {
    await nextUiUnitStory('Wallet alert routes get and delete symbol alerts', {
      severity: 'critical',
      tags: ['wallet', 'alerts', 'api-route', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('user-1')
    vi.mocked(getAlertBySymbol).mockResolvedValue({
      ok: true,
      data: { id: 'alert-1', symbol: 'PKO', below_price: null, above_price: '100.00', enabled: true, one_shot: false, expires_at: null },
      status: 200,
    })
    vi.mocked(deleteAlert).mockResolvedValue(true)

    const getResponse = await getAlertRoute(
      emptyRequest('http://localhost/api/wallet/alerts/PKO', 'GET'),
      symbolParams('PKO'),
    )
    const deleteResponse = await deleteAlertRoute(
      emptyRequest('http://localhost/api/wallet/alerts/PKO', 'DELETE'),
      symbolParams('PKO'),
    )

    expect(getResponse.status).toBe(200)
    await expect(getResponse.json()).resolves.toEqual({
      id: 'alert-1',
      symbol: 'PKO',
      below_price: null,
      above_price: '100.00',
      enabled: true,
      one_shot: false,
      expires_at: null,
    })
    expect(deleteResponse.status).toBe(200)
    await expect(deleteResponse.json()).resolves.toEqual({ ok: true })
    expect(getAlertBySymbol).toHaveBeenCalledWith('user-1', 'PKO')
    expect(deleteAlert).toHaveBeenCalledWith('user-1', 'PKO')
  })

  it('blocks unauthenticated resource mutations before wallet client calls', async () => {
    await nextUiUnitStory('Wallet resource routes block anonymous financial mutations', {
      severity: 'blocker',
      tags: ['wallet', 'api-route', 'auth', 'security', 'financial-data'],
    })
    vi.mocked(resolveWalletUserId).mockResolvedValue('')

    const response = await postMetalHolding(jsonRequest('http://localhost/api/wallet/metal-holdings', {
      wallet_id: '11111111-1111-4111-8111-111111111111',
    }))

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ error: 'Not authenticated' })
    expect(createMetalHolding).not.toHaveBeenCalled()
  })
})
