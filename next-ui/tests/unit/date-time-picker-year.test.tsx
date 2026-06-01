import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DateTimePicker } from '@/components/ui/date-time-picker'
import { nextUiUnitStory } from '../allure'

// value centered in June 2024; yearPageStart(2024) = Math.floor(2024/12)*12 = 2016
const VALUE_2024 = '2024-06-15T10:00'

async function openPicker(value = VALUE_2024) {
  const onChange = vi.fn()
  render(<DateTimePicker value={value} onChange={onChange} />)

  // Trigger opens popover
  fireEvent.click(screen.getByRole('button', { name: /15\.06\.2024|Wybierz datę/i }))

  // Wait for the month/year button to appear (popover content rendered in portal)
  await screen.findByRole('button', { name: /Wybierz rok/i })

  return { onChange }
}

describe('DateTimePicker – year navigation', () => {
  it('clicking the month label opens the year grid', async () => {
    await nextUiUnitStory('DateTimePicker clicking the calendar header switches to the year selection view', {
      severity: 'critical',
      tags: ['ui', 'date-time-picker', 'calendar', 'year-view', 'next-ui'],
    })

    await openPicker()

    fireEvent.click(screen.getByRole('button', { name: /Wybierz rok/i }))

    // Year grid must be visible: check for several years in the 2016–2027 grid
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '2024' })).toBeDefined()
      expect(screen.getByRole('button', { name: '2016' })).toBeDefined()
      expect(screen.getByRole('button', { name: '2027' })).toBeDefined()
    })
  })

  it('year grid contains 12 consecutive years starting from the page base', async () => {
    await nextUiUnitStory('DateTimePicker year grid shows 12 years for the current decade page', {
      severity: 'normal',
      tags: ['ui', 'date-time-picker', 'calendar', 'year-view', 'next-ui'],
    })

    await openPicker()
    fireEvent.click(screen.getByRole('button', { name: /Wybierz rok/i }))

    await screen.findByRole('button', { name: '2016' })

    // All 12 years 2016..2027 must be present
    for (let y = 2016; y <= 2027; y++) {
      expect(screen.getByRole('button', { name: String(y) })).toBeDefined()
    }
    // Year outside the page must not be present
    expect(screen.queryByRole('button', { name: '2015' })).toBeNull()
    expect(screen.queryByRole('button', { name: '2028' })).toBeNull()
  })

  it('day view does not show the year grid', async () => {
    await nextUiUnitStory('DateTimePicker day view does not contain year buttons', {
      severity: 'normal',
      tags: ['ui', 'date-time-picker', 'calendar', 'year-view', 'next-ui'],
    })

    await openPicker()

    // Should NOT see year buttons in day view
    expect(screen.queryByRole('button', { name: '2024' })).toBeNull()
    // Should see week day labels instead
    expect(screen.getByText('Pn')).toBeDefined()
    expect(screen.getByText('Nd')).toBeDefined()
  })

  it('clicking a year navigates to that year and returns to the day view', async () => {
    await nextUiUnitStory('DateTimePicker clicking a year in the grid sets that year and returns to the monthly view', {
      severity: 'critical',
      tags: ['ui', 'date-time-picker', 'calendar', 'year-view', 'next-ui'],
    })

    await openPicker()
    fireEvent.click(screen.getByRole('button', { name: /Wybierz rok/i }))

    await screen.findByRole('button', { name: '2020' })
    fireEvent.click(screen.getByRole('button', { name: '2020' }))

    // Should return to day view – week days visible again
    await waitFor(() => {
      expect(screen.getByText('Pn')).toBeDefined()
    })

    // Header should now show 2020
    expect(screen.getByRole('button', { name: /Wybierz rok/i }).textContent).toMatch(/2020/)
  })

  it('previous-years button shifts the grid back by 12 years', async () => {
    await nextUiUnitStory('DateTimePicker previous-years button displays an earlier year grid', {
      severity: 'normal',
      tags: ['ui', 'date-time-picker', 'calendar', 'year-view', 'next-ui'],
    })

    await openPicker()
    fireEvent.click(screen.getByRole('button', { name: /Wybierz rok/i }))

    await screen.findByRole('button', { name: /Poprzednie lata/i })
    fireEvent.click(screen.getByRole('button', { name: /Poprzednie lata/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '2004' })).toBeDefined()
      expect(screen.getByRole('button', { name: '2015' })).toBeDefined()
    })
    expect(screen.queryByRole('button', { name: '2016' })).toBeNull()
  })

  it('next-years button shifts the grid forward by 12 years', async () => {
    await nextUiUnitStory('DateTimePicker next-years button displays a later year grid', {
      severity: 'normal',
      tags: ['ui', 'date-time-picker', 'calendar', 'year-view', 'next-ui'],
    })

    await openPicker()
    fireEvent.click(screen.getByRole('button', { name: /Wybierz rok/i }))

    await screen.findByRole('button', { name: /Następne lata/i })
    fireEvent.click(screen.getByRole('button', { name: /Następne lata/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '2028' })).toBeDefined()
      expect(screen.getByRole('button', { name: '2039' })).toBeDefined()
    })
    expect(screen.queryByRole('button', { name: '2027' })).toBeNull()
  })

  it('clicking the year-range header returns to the day view', async () => {
    await nextUiUnitStory('DateTimePicker clicking the year-range header returns to the day view', {
      severity: 'normal',
      tags: ['ui', 'date-time-picker', 'calendar', 'year-view', 'next-ui'],
    })

    await openPicker()
    fireEvent.click(screen.getByRole('button', { name: /Wybierz rok/i }))

    await screen.findByRole('button', { name: /Wróć do widoku miesięcznego/i })
    fireEvent.click(screen.getByRole('button', { name: /Wróć do widoku miesięcznego/i }))

    await waitFor(() => {
      expect(screen.getByText('Pn')).toBeDefined()
    })
    expect(screen.queryByRole('button', { name: '2024' })).toBeNull()
  })

  it('reopening the popover resets to the day view', async () => {
    await nextUiUnitStory('DateTimePicker reopening the calendar always starts from the day view', {
      severity: 'normal',
      tags: ['ui', 'date-time-picker', 'calendar', 'year-view', 'next-ui'],
    })

    await openPicker()

    // Enter year view
    fireEvent.click(screen.getByRole('button', { name: /Wybierz rok/i }))
    await screen.findByRole('button', { name: '2024' })

    // Close popover by clicking the trigger again
    fireEvent.click(screen.getByRole('button', { name: /15\.06\.2024/i }))

    // Reopen
    fireEvent.click(screen.getByRole('button', { name: /15\.06\.2024/i }))

    // Should be in day view again
    await waitFor(() => {
      expect(screen.getByText('Pn')).toBeDefined()
    })
    expect(screen.queryByRole('button', { name: '2024' })).toBeNull()
  })
})
