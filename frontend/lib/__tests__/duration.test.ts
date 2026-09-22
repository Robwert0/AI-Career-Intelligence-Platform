import { describe, expect, it } from 'vitest'
import { formatWait } from '../duration'

describe('formatWait', () => {
  it.each([
    [1, '1 second'],
    [45, '45 seconds'],
    [90, '2 minutes'],
    [600, '10 minutes'],
    [1200, '20 minutes'],
    [3600, '1 hour'],
    [7200, '2 hours'],
  ])('renders %i seconds as %s', (seconds, expected) => {
    expect(formatWait(seconds)).toBe(expected)
  })

  it('never renders a zero or negative wait as a number', () => {
    expect(formatWait(0)).toBe('a moment')
    expect(formatWait(-5)).toBe('a moment')
  })

  it('rounds up so the caller never retries too early', () => {
    expect(formatWait(61)).toBe('2 minutes')
  })
})
