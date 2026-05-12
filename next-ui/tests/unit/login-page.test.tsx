import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/features/auth/actions/login', () => ({
  loginAction: vi.fn(async () => undefined),
}))

import LoginPage from '@/app/(auth)/login/page'
import { nextUiUnitStory } from '../allure'

describe('Login page', () => {
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
})
