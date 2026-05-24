import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const reactMocks = vi.hoisted(() => ({
  useActionState: vi.fn(),
}))

vi.mock('@/features/auth/actions/login', () => ({
  loginAction: vi.fn(async () => undefined),
}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    useActionState: reactMocks.useActionState,
  }
})

import LoginPage from '@/app/(auth)/login/page'
import { nextUiUnitStory } from '../allure'

describe('Login page', () => {
  beforeEach(() => {
    reactMocks.useActionState.mockReturnValue([undefined, vi.fn(), false])
  })

  afterEach(() => {
    reactMocks.useActionState.mockReset()
    vi.unstubAllGlobals()
  })

  it('renders authentication fields and register link', async () => {
    await nextUiUnitStory('Login page exposes stable authentication form', {
      severity: 'critical',
      tags: ['auth', 'next-ui'],
    })

    render(<LoginPage />)

    expect(screen.getByText('FinancialManager')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email')
    expect(screen.getByLabelText('Hasło')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button', { name: /zaloguj się/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /zarejestruj się/i })).toHaveAttribute('href', '/register')
  })

  it('shows login action error messages to the user', async () => {
    await nextUiUnitStory('Login page renders rejected login errors', {
      severity: 'critical',
      tags: ['auth', 'next-ui', 'error-state'],
    })
    reactMocks.useActionState.mockReturnValue([
      { message: 'Incorrect email or password.' },
      vi.fn(),
      false,
    ])

    render(<LoginPage />)

    expect(screen.getByText('Incorrect email or password.')).toBeInTheDocument()
  })

  it('disables the submit button while login is pending', async () => {
    await nextUiUnitStory('Login page prevents duplicate submits while pending', {
      severity: 'critical',
      tags: ['auth', 'next-ui', 'double-submit'],
    })
    reactMocks.useActionState.mockReturnValue([undefined, vi.fn(), true])

    render(<LoginPage />)

    expect(screen.getByRole('button', { name: /logowanie/i })).toBeDisabled()
  })

  it('redirects to wallet after a successful login action', async () => {
    await nextUiUnitStory('Login page redirects to wallet after login success', {
      severity: 'critical',
      tags: ['auth', 'next-ui', 'routing'],
    })
    const location = { href: 'http://next.localhost/login' }
    vi.stubGlobal('window', { ...window, location })
    reactMocks.useActionState.mockReturnValue([{ success: true }, vi.fn(), false])

    render(<LoginPage />)

    expect(location.href).toBe('/wallet')
  })

  it('redirects to two-factor verification when login requires 2FA', async () => {
    await nextUiUnitStory('Login page redirects to two-factor verification after password success', {
      severity: 'blocker',
      tags: ['auth', 'next-ui', '2fa', 'routing'],
    })
    const location = { href: 'http://next.localhost/login' }
    vi.stubGlobal('window', { ...window, location })
    reactMocks.useActionState.mockReturnValue([{ requiresTwoFactor: true }, vi.fn(), false])

    render(<LoginPage />)

    expect(location.href).toBe('/two-factor')
  })
})
