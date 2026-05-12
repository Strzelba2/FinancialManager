import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/features/auth/actions/register', () => ({
  registerAction: vi.fn(async () => undefined),
}))

import RegisterPage from '@/app/(auth)/register/page'
import { nextUiUnitStory } from '../allure'

describe('Register page', () => {
  it('renders registration fields and login link', async () => {
    await nextUiUnitStory('Register page exposes stable registration form', {
      severity: 'critical',
      tags: ['auth', 'next-ui'],
    })

    render(<RegisterPage />)

    expect(screen.getByText('Rejestracja')).toBeInTheDocument()
    expect(screen.getByLabelText('Imię')).toBeInTheDocument()
    expect(screen.getByLabelText('Nazwisko')).toBeInTheDocument()
    expect(screen.getByLabelText('Nazwa użytkownika')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email')
    expect(screen.getByLabelText('Hasło')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button', { name: /zarejestruj się/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /zaloguj się/i })).toHaveAttribute('href', '/login')
  })
})
