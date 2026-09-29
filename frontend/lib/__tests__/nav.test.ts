import { describe, expect, it } from 'vitest'
import { NAV_LINKS } from '../nav'

describe('NAV_LINKS', () => {
  it('links the Job Match Analyzer', () => {
    expect(NAV_LINKS).toContainEqual({ href: '/match', label: 'Job Match Analyzer' })
  })

  it('has no duplicate destinations', () => {
    const hrefs = NAV_LINKS.map((link) => link.href)

    expect(new Set(hrefs).size).toBe(hrefs.length)
  })
})
