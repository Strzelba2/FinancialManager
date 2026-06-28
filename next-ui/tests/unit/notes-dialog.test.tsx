import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../msw-server'
import { toast } from 'sonner'

import { NotesDialog } from '@/features/wallet/components/NotesDialog'
import { nextUiUnitStory } from '../allure'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

describe('NotesDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })

  it('loads the current user note and saves edited text through the wallet API route', async () => {
    await nextUiUnitStory('Wallet notes dialog loads and saves the user note', {
      severity: 'normal',
      tags: ['wallet', 'notes', 'api-contract', 'next-ui'],
    })
    const saves: unknown[] = []
    server.use(
      http.get('*/api/wallet/notes', () =>
        HttpResponse.json({
          id: 'note-1',
          text: 'Kupic obligacje w lipcu',
          updated_at: '2026-06-26T10:15:00.000Z',
        }),
      ),
      http.put('*/api/wallet/notes', async ({ request }) => {
        saves.push(await request.json())
        return HttpResponse.json({
          id: 'note-1',
          text: 'Kupic obligacje w lipcu i sprawdzic IKE',
          updated_at: '2026-06-27T10:15:00.000Z',
        })
      }),
    )

    render(<NotesDialog open onOpenChange={vi.fn()} />)

    const textarea = await screen.findByLabelText('Treść notatki')
    expect(textarea).toHaveValue('Kupic obligacje w lipcu')
    expect(screen.getByText('Treść zgodna z ostatnim zapisem')).toBeInTheDocument()

    fireEvent.change(textarea, {
      target: { value: 'Kupic obligacje w lipcu i sprawdzic IKE' },
    })
    expect(screen.getByText('Masz niezapisane zmiany')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Zapisz/i }))

    await waitFor(() => {
      expect(saves).toEqual([{ text: 'Kupic obligacje w lipcu i sprawdzic IKE' }])
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Zapisano notatkę'))
    expect(screen.getByText('Treść zgodna z ostatnim zapisem')).toBeInTheDocument()
  })

  it('shows a retryable load error when the note endpoint is unavailable', async () => {
    await nextUiUnitStory('Wallet notes dialog exposes a retryable load error state', {
      severity: 'normal',
      tags: ['wallet', 'notes', 'error-state', 'next-ui'],
    })
    let attempts = 0
    server.use(
      http.get('*/api/wallet/notes', () => {
        attempts += 1
        if (attempts === 1) {
          return HttpResponse.json({ error: 'Nie można wczytać notatki' }, { status: 503 })
        }
        return HttpResponse.json(null)
      }),
    )

    render(<NotesDialog open onOpenChange={vi.fn()} />)

    expect(await screen.findByText('Nie można wczytać notatki')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Spróbuj ponownie/i }))

    await waitFor(() => expect(attempts).toBe(2))
    expect(screen.getByLabelText('Treść notatki')).toHaveValue('')
  })
})
