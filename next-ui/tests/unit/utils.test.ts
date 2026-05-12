import { describe, expect, it } from 'vitest'

import { cn } from '@/lib/utils'
import { nextUiUnitStory } from '../allure'

describe('cn', () => {
  it('merges class names and resolves tailwind conflicts', async () => {
    await nextUiUnitStory('Class name utility resolves Tailwind conflicts', {
      severity: 'minor',
      tags: ['utils'],
    })

    expect(cn('px-2', 'text-sm', 'px-4')).toBe('text-sm px-4')
  })
})
