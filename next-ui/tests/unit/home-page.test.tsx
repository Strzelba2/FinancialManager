import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import HomePage from '@/app/(public)/home/page'
import { nextUiUnitStory } from '../allure'

describe('Public home page', () => {
  it('renders the main marketing heading and cta links', async () => {
    await nextUiUnitStory('Public home exposes authentication entry points', {
      severity: 'normal',
      tags: ['next-ui'],
    })

    render(<HomePage />)

    expect(
      screen.getByRole('heading', { name: /zyskaj kontrolę nad swoimi finansami/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /zarejestruj się/i })).toHaveAttribute('href', '/register')
    expect(screen.getByRole('link', { name: /zaloguj się/i })).toHaveAttribute('href', '/login')
  })
})
