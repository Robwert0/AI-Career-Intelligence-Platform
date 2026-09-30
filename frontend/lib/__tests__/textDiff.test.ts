import { describe, expect, it } from 'vitest'
import { wordDiff } from '../textDiff'

const join = (segments: { text: string }[]) => segments.map((s) => s.text).join('')
const changed = (segments: { text: string; changed: boolean }[]) =>
  segments.filter((s) => s.changed).map((s) => s.text.trim())

describe('wordDiff', () => {
  it('marks only the words a rewrite added', () => {
    const diff = wordDiff(
      'Built and maintained Python microservices.',
      'Designed, built and maintained Python microservices.',
    )
    expect(changed(diff.suggested)).toEqual(['Designed,'])
    expect(changed(diff.original)).toEqual([])
    expect(join(diff.suggested)).toBe('Designed, built and maintained Python microservices.')
  })

  it('treats punctuation changes as changes', () => {
    const diff = wordDiff('Redis, Docker, Kubernetes', 'Redis, Docker; Kubernetes')
    expect(changed(diff.original)).toEqual(['Docker,'])
    expect(changed(diff.suggested)).toEqual(['Docker;'])
  })

  it('reproduces both texts exactly from their segments', () => {
    const before = 'Python, PostgreSQL, Redis, Docker, Kubernetes (basic)'
    const after = 'Python, PostgreSQL, Redis, Docker; Kubernetes (deployment basics)'
    const diff = wordDiff(before, after)
    expect(join(diff.original)).toBe(before)
    expect(join(diff.suggested)).toBe(after)
  })

  it('reports no change for identical text', () => {
    const diff = wordDiff('Same words here.', 'Same words here.')
    expect(diff.suggested).toEqual([{ text: 'Same words here.', changed: false }])
  })

  it('handles an empty side', () => {
    expect(wordDiff('', 'New line.').suggested).toEqual([{ text: 'New line.', changed: true }])
    expect(wordDiff('Old line.', '').original).toEqual([{ text: 'Old line.', changed: true }])
  })
})
