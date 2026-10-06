import { afterEach, describe, expect, it, vi } from 'vitest'
import { chat, type ChatResponse } from '../api'
import { setAccessToken } from '../auth'
import { CHAT_STARTERS } from '../chatStarters'
import type { ApiResult } from '../http'
import {
  MAX_HISTORY_CHARS,
  MAX_HISTORY_MESSAGE_CHARS,
  MAX_HISTORY_MESSAGES,
  historyFrom,
  questionTurn,
  replyTurn,
  type Turn,
} from '../turns'

function answer(text: string, refused = false): ApiResult<ChatResponse> {
  return { ok: true, data: { answer: text, refused, sources: [] } }
}

function exchange(question: string, reply: string): Turn[] {
  return [questionTurn(question), replyTurn(answer(reply))]
}

afterEach(() => vi.unstubAllGlobals())

describe('historyFrom', () => {
  it('sends nothing before the first answer', () => {
    expect(historyFrom([])).toEqual([])
    expect(historyFrom([questionTurn('pending question')])).toEqual([])
  })

  it('turns completed exchanges into alternating user/assistant messages', () => {
    const turns = exchange('What backend experience does he have?', 'He builds FastAPI services.')

    expect(historyFrom(turns)).toEqual([
      { role: 'user', content: 'What backend experience does he have?' },
      { role: 'assistant', content: 'He builds FastAPI services.' },
    ])
  })

  it('keeps refusals, which are real replies, as context', () => {
    const turns = [questionTurn('Does he know Rust?'), replyTurn(answer('Not in the CV.', true))]

    expect(historyFrom(turns).map((m) => m.role)).toEqual(['user', 'assistant'])
  })

  it('drops a question whose reply was an error, and never sends the error text', () => {
    const turns = [
      ...exchange('first?', 'first answer'),
      questionTurn('failed?'),
      replyTurn({ ok: false, status: 0, detail: 'down' }),
      ...exchange('third?', 'third answer'),
    ]

    const history = historyFrom(turns)

    expect(history.map((m) => m.content)).toEqual([
      'first?',
      'first answer',
      'third?',
      'third answer',
    ])
    expect(JSON.stringify(history)).not.toContain('Could not reach the server')
  })

  it('keeps only the newest exchanges that fit the message limit', () => {
    const turns = [1, 2, 3, 4, 5].flatMap((n) => exchange(`q${n}`, `a${n}`))

    const history = historyFrom(turns)

    expect(history).toHaveLength(MAX_HISTORY_MESSAGES)
    expect(history[0].content).toBe('q3')
    expect(history.at(-1)?.content).toBe('a5')
  })

  it('clips one long message and keeps the total under the character limit', () => {
    const long = 'x'.repeat(MAX_HISTORY_MESSAGE_CHARS + 500)
    const turns = [1, 2, 3].flatMap(() => exchange(long, long))

    const history = historyFrom(turns)
    const total = history.reduce((sum, m) => sum + m.content.length, 0)

    expect(history.every((m) => m.content.length <= MAX_HISTORY_MESSAGE_CHARS)).toBe(true)
    expect(total).toBeLessThanOrEqual(MAX_HISTORY_CHARS)
    expect(history.length % 2).toBe(0)
    expect(history[0].role).toBe('user')
  })
})

describe('chat request', () => {
  function capture() {
    setAccessToken('live')
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ answer: 'x', refused: false, sources: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    return () =>
      JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string)
  }

  it('sends a single question exactly as before, with no history field', async () => {
    const body = capture()

    await chat('What backend experience does he have?')

    expect(body()).toEqual({ message: 'What backend experience does he have?' })
  })

  it('sends the current question once, as the message, after its history', async () => {
    const body = capture()
    const history = historyFrom(exchange('What backend experience?', 'FastAPI services.'))

    await chat('Which project demonstrates that?', history)

    const sent = body()
    expect(sent.message).toBe('Which project demonstrates that?')
    expect(sent.history.map((m: { content: string }) => m.content)).not.toContain(sent.message)
    expect(sent.history).toHaveLength(2)
  })
})

describe('starter questions', () => {
  it('offers a few short questions within the message limit', () => {
    expect(CHAT_STARTERS.length).toBeGreaterThanOrEqual(3)
    expect(CHAT_STARTERS.length).toBeLessThanOrEqual(5)
    expect(new Set(CHAT_STARTERS).size).toBe(CHAT_STARTERS.length)
    expect(CHAT_STARTERS.every((q) => q.length > 0 && q.length <= 200)).toBe(true)
  })
})
