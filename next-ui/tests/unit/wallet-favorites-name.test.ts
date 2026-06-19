import { describe, expect, it } from 'vitest'

import { resolveFavoriteName } from '@/app/api/wallet/favorites/[id]/route'

import { nextUiUnitStory } from '../allure'

describe('resolveFavoriteName', () => {
  it('prefers the live quote name over a stored name equal to the symbol', async () => {
    await nextUiUnitStory('Favorite name resolves from the live quote feed', {
      severity: 'normal',
      tags: ['wallet', 'favorites', 'formatting'],
    })
    expect(resolveFavoriteName('PKO', 'PKO', 'PKO Bank Polski')).toBe('PKO Bank Polski')
  })

  it('falls back to the stored name when the quote has no name', () => {
    expect(resolveFavoriteName('PKO', 'PKO Bank Polski', null)).toBe('PKO Bank Polski')
  })

  it('ignores a quote name equal to the symbol and uses the stored name', () => {
    expect(resolveFavoriteName('PKO', 'PKO Bank Polski', 'pko')).toBe('PKO Bank Polski')
  })

  it('returns a dash when neither name carries real information', () => {
    expect(resolveFavoriteName('PKO', 'PKO', '')).toBe('—')
    expect(resolveFavoriteName('PKO', null, null)).toBe('—')
  })

  it('trims whitespace from the resolved name', () => {
    expect(resolveFavoriteName('PKO', null, '  PKO Bank Polski  ')).toBe('PKO Bank Polski')
  })
})
