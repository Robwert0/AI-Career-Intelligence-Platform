import { describe, expect, it } from 'vitest'
import { showsChatBubble } from '../bubble'

describe('showsChatBubble', () => {
  it.each(['/', '/login', '/register'])('shows the bubble on %s', (pathname) => {
    expect(showsChatBubble(pathname)).toBe(true)
  })

  it.each(['/chat', '/chat/', '/match', '/match/'])('hides it on %s', (pathname) => {
    expect(showsChatBubble(pathname)).toBe(false)
  })

  it('does not hide it on a page that merely starts with the same letters', () => {
    expect(showsChatBubble('/chatter')).toBe(true)
  })
})
