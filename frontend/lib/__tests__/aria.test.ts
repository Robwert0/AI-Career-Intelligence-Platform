import { describe, expect, it } from 'vitest'
import { describedBy } from '../aria'

describe('describedBy', () => {
  it('joins the ids that are present', () => {
    expect(describedBy('hint', false, undefined, 'error')).toBe('hint error')
  })

  it('returns undefined when nothing describes the field', () => {
    expect(describedBy(false, null, undefined, '')).toBeUndefined()
  })
})
