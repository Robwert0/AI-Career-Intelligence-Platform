import { describe, expect, it } from 'vitest'
import type { ChatResponse } from '../api'
import type { ApiResult } from '../http'
import { questionTurn, replyTurn } from '../turns'

function answered(overrides: Partial<ChatResponse> = {}): ApiResult<ChatResponse> {
  return {
    ok: true,
    data: {
      answer: 'He used FastAPI.',
      refused: false,
      sources: [{ section: 'skills', content: 'FastAPI, PostgreSQL' }],
      ...overrides,
    },
  }
}

function failed(status: number, detail = 'boom', retryAfter?: number): ApiResult<ChatResponse> {
  return { ok: false, status, detail, retryAfter }
}

describe('questionTurn', () => {
  it('keeps the text verbatim', () => {
    expect(questionTurn('what did he build?')).toMatchObject({
      kind: 'question',
      text: 'what did he build?',
    })
  })

  it('gives every turn a distinct id', () => {
    expect(questionTurn('a').id).not.toBe(questionTurn('a').id)
  })
})

describe('replyTurn', () => {
  it('renders an answer with its sources', () => {
    const turn = replyTurn(answered())

    expect(turn).toMatchObject({ kind: 'answer', text: 'He used FastAPI.' })
    if (turn.kind === 'answer') expect(turn.sources).toHaveLength(1)
  })

  it('renders a refusal as its own kind, not an error', () => {
    expect(replyTurn(answered({ refused: true, sources: [] })).kind).toBe('refusal')
  })

  it('never attaches sources to a refusal', () => {
    const turn = replyTurn(
      answered({ refused: true, sources: [{ section: 'skills', content: 'x' }] }),
    )

    expect(turn).not.toHaveProperty('sources')
  })

  it('explains a rate limit with a readable wait', () => {
    expect(replyTurn(failed(429, 'Too many requests', 90))).toMatchObject({
      kind: 'error',
      text: 'Too many questions. Try again in 2 minutes.',
    })
  })

  it('explains a rate limit with no retry hint', () => {
    expect(replyTurn(failed(429, 'Too many requests'))).toMatchObject({
      text: 'Too many questions. Try again shortly.',
    })
  })

  it('explains a busy or cold model', () => {
    expect(replyTurn(failed(503, 'Service unavailable'))).toMatchObject({
      kind: 'error',
      text: 'The model is busy or still starting up. Try again in a moment.',
    })
  })

  it('tells the user to sign in again when the session ended', () => {
    expect(replyTurn(failed(401, 'Not authenticated'))).toMatchObject({
      text: 'Your session ended. Sign in again.',
    })
  })

  it('surfaces a validation message from the server', () => {
    expect(replyTurn(failed(422, 'Question is too long'))).toMatchObject({
      kind: 'error',
      text: 'Question is too long',
    })
  })

  it('reports an unreachable server', () => {
    expect(replyTurn(failed(0, 'Could not reach the server'))).toMatchObject({
      text: 'Could not reach the server.',
    })
  })

  it('does not leak a server detail on a 500', () => {
    const turn = replyTurn(failed(500, 'Traceback: internal detail'))

    expect(turn.text).toBe('Something went wrong. Please try again.')
    expect(turn.text).not.toContain('Traceback')
  })
})
