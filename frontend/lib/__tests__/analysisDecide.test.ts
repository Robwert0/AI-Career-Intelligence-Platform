import { describe, expect, it } from 'vitest'
import { decideOutcome } from '../analysisDecide'
import type { ApiResult } from '../http'
import type { AnalysisSubmitted } from '../match'

function ok(analysisId: string): ApiResult<AnalysisSubmitted> {
  return { ok: true, data: { analysis_id: analysisId } }
}

function fail(
  patch: Partial<Extract<ApiResult<AnalysisSubmitted>, { ok: false }>> & { status: number },
) {
  return { ok: false as const, detail: 'x', ...patch }
}

describe('decideOutcome (useAnalysis.decide, pulled out for unit testing)', () => {
  it('reports moved when the response names a different analysis', () => {
    expect(decideOutcome('continue', 'a1', ok('a2'))).toEqual({ type: 'moved', analysisId: 'a2' })
  })

  it('reports succeeded when the same analysis continues', () => {
    expect(decideOutcome('retry', 'a1', ok('a1'))).toEqual({ type: 'succeeded' })
  })

  it('reports stale for a 409 not_awaiting_decision, so the caller just resumes polling', () => {
    expect(
      decideOutcome('continue', 'a1', fail({ status: 409, code: 'not_awaiting_decision' })),
    ).toEqual({ type: 'stale' })
  })

  it('reports session_ended on a 401, whichever action it was', () => {
    expect(decideOutcome('continue', 'a1', fail({ status: 401 }))).toEqual({
      type: 'session_ended',
    })
    expect(decideOutcome('retry', 'a1', fail({ status: 401 }))).toEqual({ type: 'session_ended' })
  })

  it('gives retry its own 429 wording: it spent a scarce 5/hour token, unlike continue', () => {
    const outcome = decideOutcome('retry', 'a1', fail({ status: 429, retryAfter: 900 }))

    expect(outcome.type).toBe('problem')
    expect(outcome.type === 'problem' && outcome.problem.message).toBe(
      "You've used all your analysis retries for this hour. Try again in 15 minutes.",
    )
  })

  it('gives continue the ordinary rate-limit wording for a 429: it only spends the poll limit', () => {
    const outcome = decideOutcome('continue', 'a1', fail({ status: 429, retryAfter: 30 }))

    expect(outcome.type).toBe('problem')
    expect(outcome.type === 'problem' && outcome.problem.message).toBe(
      'Too many requests. Try again in 30 seconds.',
    )
  })

  it('falls back to the ordinary problem mapping for anything else', () => {
    const outcome = decideOutcome('continue', 'a1', fail({ status: 503, retryAfter: 5 }))

    expect(outcome.type).toBe('problem')
    expect(outcome.type === 'problem' && outcome.problem.message).toMatch(/busy or unavailable/i)
  })
})
