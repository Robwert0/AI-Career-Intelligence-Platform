import { describe, expect, it } from 'vitest'
import { DEFAULT_AFTER_SIGN_IN, safeNextPath, withNext } from '../redirect'

describe('safeNextPath', () => {
  it.each(['/chat', '/match'])('allows %s', (path) => {
    expect(safeNextPath(path)).toBe(path)
  })

  it.each([
    null,
    '',
    '//evil.example',
    'https://evil.example/match',
    '/match/../admin',
    '/match?x=1',
    '/Match',
    ' /match',
    'javascript:alert(1)',
  ])('falls back to the default for %j', (raw) => {
    expect(safeNextPath(raw)).toBe(DEFAULT_AFTER_SIGN_IN)
  })
})

describe('withNext', () => {
  it('carries a non-default destination', () => {
    expect(withNext('/register', '/match')).toBe('/register?next=%2Fmatch')
    expect(withNext('/login?registered=1', '/match')).toBe('/login?registered=1&next=%2Fmatch')
  })

  it('leaves the default out of the URL', () => {
    expect(withNext('/register', DEFAULT_AFTER_SIGN_IN)).toBe('/register')
  })
})
