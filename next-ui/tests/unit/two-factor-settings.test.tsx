import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const reactMocks = vi.hoisted(() => ({
  useActionState: vi.fn(),
}))

vi.mock('@/features/auth/actions/two-factor', () => ({
  disableTwoFactorAction: vi.fn(async () => undefined),
  enableTwoFactorAction: vi.fn(async () => undefined),
  setupTwoFactorAction: vi.fn(async () => undefined),
}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    useActionState: reactMocks.useActionState,
  }
})

import { TwoFactorSettings } from '@/features/auth/components/TwoFactorSettings'
import { nextUiUnitStory } from '../allure'

function mockActionStates(
  setupState: unknown = undefined,
  enableState: unknown = undefined,
  disableState: unknown = undefined,
) {
  reactMocks.useActionState
    .mockReturnValueOnce([setupState, vi.fn(), false])
    .mockReturnValueOnce([enableState, vi.fn(), false])
    .mockReturnValueOnce([disableState, vi.fn(), false])
}

describe('TwoFactorSettings', () => {
  beforeEach(() => {
    mockActionStates()
  })

  afterEach(() => {
    reactMocks.useActionState.mockReset()
  })

  it('renders inactive 2FA status and setup trigger', async () => {
    await nextUiUnitStory('Profile 2FA settings render inactive status and setup trigger', {
      severity: 'critical',
      tags: ['auth', 'next-ui', '2fa'],
    })

    render(<TwoFactorSettings initialEnabled={false} />)

    expect(screen.getByText('Uwierzytelnianie dwuskładnikowe')).toBeInTheDocument()
    expect(screen.getByText('Status: nieaktywne')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /wygeneruj kod qr/i })).toBeInTheDocument()
  })

  it('renders setup QR and enable form after setup action succeeds', async () => {
    await nextUiUnitStory('Profile 2FA settings render QR setup state', {
      severity: 'critical',
      tags: ['auth', 'next-ui', '2fa', 'qrcode'],
    })
    reactMocks.useActionState.mockReset()
    mockActionStates({ image: 'svg-base64', success: true })

    render(<TwoFactorSettings initialEnabled={false} />)

    expect(await screen.findByAltText('Kod QR 2FA')).toHaveAttribute(
      'src',
      'data:image/svg+xml;base64,svg-base64',
    )
    expect(screen.getByRole('button', { name: /włącz 2fa/i })).toBeInTheDocument()
  })

  it('renders setup errors from the 2FA action', async () => {
    await nextUiUnitStory('Profile 2FA settings render setup error state', {
      severity: 'critical',
      tags: ['auth', 'next-ui', '2fa', 'error-state'],
    })
    reactMocks.useActionState.mockReset()
    mockActionStates({ message: 'Nie udało się wygenerować kodu QR' })

    render(<TwoFactorSettings initialEnabled={false} />)

    expect(screen.getByText('Nie udało się wygenerować kodu QR')).toBeInTheDocument()
  })

  it('renders enabled 2FA status and disable form', async () => {
    await nextUiUnitStory('Profile 2FA settings render enabled status and disable control', {
      severity: 'critical',
      tags: ['auth', 'next-ui', '2fa'],
    })

    render(<TwoFactorSettings initialEnabled />)

    expect(screen.getByText('Status: aktywne')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /wyłącz 2fa/i })).toBeInTheDocument()
  })
})
