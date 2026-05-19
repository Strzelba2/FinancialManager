import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const logoutMocks = vi.hoisted(() => ({
  logoutAction: vi.fn(),
}))

vi.mock('@/features/auth/actions/logout', () => ({
  logoutAction: logoutMocks.logoutAction,
}))

import LogoutPage from '@/app/(dashboard)/logout/page'
import { nextUiUnitStory } from '../allure'

describe('Logout page', () => {
  afterEach(() => {
    logoutMocks.logoutAction.mockReset()
  })

  it('renders a confirmation form without logging out on GET render', async () => {
    await nextUiUnitStory('Logout page requires explicit POST confirmation', {
      severity: 'blocker',
      tags: ['auth', 'next-ui', 'logout', 'csrf'],
    })

    render(<LogoutPage />)

    expect(screen.getByText('Wylogować z konta?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /wyloguj się/i })).toHaveAttribute('type', 'submit')
    expect(screen.getByRole('link', { name: /wróć do portfela/i })).toHaveAttribute('href', '/wallet')
    expect(logoutMocks.logoutAction).not.toHaveBeenCalled()
  })

  it('calls the logout action when the confirmation form is submitted', async () => {
    await nextUiUnitStory('Logout page submits the server logout action', {
      severity: 'blocker',
      tags: ['auth', 'next-ui', 'logout'],
    })

    render(<LogoutPage />)

    const form = screen.getByRole('button', { name: /wyloguj się/i }).closest('form')
    expect(form).not.toBeNull()
    fireEvent.submit(form as HTMLFormElement)

    expect(logoutMocks.logoutAction).toHaveBeenCalledOnce()
  })
})
