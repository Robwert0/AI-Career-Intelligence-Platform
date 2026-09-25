import { describe, expect, it } from 'vitest'
import { THEME_STORAGE_KEY, resolveTheme, themeInitScript } from '../theme'

function runInitScript(stored: string | null | 'throws', prefersLight: boolean) {
  const root = { dataset: {} as Record<string, string> }
  const localStorage = {
    getItem: (key: string) => {
      if (stored === 'throws') throw new Error('blocked')
      return key === THEME_STORAGE_KEY ? stored : null
    },
  }
  const matchMedia = () => ({ matches: prefersLight })
  new Function('localStorage', 'matchMedia', 'document', themeInitScript)(
    localStorage,
    matchMedia,
    {
      documentElement: root,
    },
  )
  return root.dataset.theme
}

describe('theme', () => {
  it('prefers a saved choice, then the OS preference', () => {
    expect(resolveTheme('light', false)).toBe('light')
    expect(resolveTheme('dark', true)).toBe('dark')
    expect(resolveTheme(null, true)).toBe('light')
    expect(resolveTheme(null, false)).toBe('dark')
  })

  it('ignores a tampered stored value instead of writing it into the page', () => {
    expect(resolveTheme('"><script>', true)).toBe('light')
    expect(runInitScript('"><script>', false)).toBe('dark')
  })

  it('pre-paint script agrees with resolveTheme in every case', () => {
    for (const stored of ['dark', 'light', null, 'bogus']) {
      for (const prefersLight of [true, false]) {
        expect(runInitScript(stored, prefersLight)).toBe(resolveTheme(stored, prefersLight))
      }
    }
  })

  it('falls back to the OS preference when storage is blocked', () => {
    expect(runInitScript('throws', true)).toBe('light')
  })
})
