import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const reactMocks = vi.hoisted(() => ({
  useActionState: vi.fn(),
}))

vi.mock('@/features/auth/actions/two-factor', () => ({
  verifyTwoFactorAction: vi.fn(async () => undefined),
}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    useActionState: reactMocks.useActionState,
  }
})

import TwoFactorPage from '@/app/(auth)/two-factor/page'
import { nextUiUnitStory } from '../allure'

describe('Two-factor page', () => {
  beforeEach(() => {
    reactMocks.useActionState.mockReturnValue([undefined, vi.fn(), false])
  })

  afterEach(() => {
    reactMocks.useActionState.mockReset()
    vi.unstubAllGlobals()
  })

  it('renders the 2FA token form', async () => {
    await nextUiUnitStory('Two-factor page exposes stable token form', {
      severity: 'blocker',
      tags: ['auth', 'next-ui', '2fa'],
    })

    render(<TwoFactorPage />)

    expect(screen.getByText('Weryfikacja 2FA')).toBeInTheDocument()
    expect(screen.getByLabelText('Kod 2FA')).toHaveAttribute('name', 'token')
    expect(screen.getByRole('button', { name: /potwierdź kod/i })).toBeInTheDocument()
  })

  it('shows rejected 2FA messages to the user', async () => {
    await nextUiUnitStory('Two-factor page renders rejected verification errors', {
      severity: 'blocker',
      tags: ['auth', 'next-ui', '2fa', 'error-state'],
    })
    reactMocks.useActionState.mockReturnValue([
      { message: 'Invalid 2FA code.' },
      vi.fn(),
      false,
    ])

    render(<TwoFactorPage />)

    expect(screen.getByText('Invalid 2FA code.')).toBeInTheDocument()
  })

  it('redirects to wallet after successful 2FA verification', async () => {
    await nextUiUnitStory('Two-factor page redirects to wallet after token success', {
      severity: 'blocker',
      tags: ['auth', 'next-ui', '2fa', 'routing'],
    })
    const location = { href: 'http://next.localhost/two-factor' }
    vi.stubGlobal('window', { ...window, location })
    reactMocks.useActionState.mockReturnValue([{ success: true }, vi.fn(), false])

    render(<TwoFactorPage />)

    expect(location.href).toBe('/wallet')
  })
})
