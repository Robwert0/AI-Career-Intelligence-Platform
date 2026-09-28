import { describe, expect, it } from 'vitest'
import type { ApiFailure } from '../http'
import type { FailureOut, Recovery } from '../match'
import {
  analysisFailureAction,
  jobRecovery,
  requestProblem,
  retryLimitProblem,
  runningJobId,
} from '../matchErrors'

function failure(patch: Partial<ApiFailure> & { status: number }): ApiFailure {
  return { ok: false, detail: 'The server says so.', ...patch }
}

function failed(code: string, recovery: Recovery = 'retry'): FailureOut {
  return { code, message: `message for ${code}`, recovery }
}

describe('requestProblem', () => {
  it('reports an unreachable server', () => {
    expect(requestProblem(failure({ status: 0 })).message).toMatch(/could not reach the server/i)
  })

  it('ends the session on a 401, whatever shape the body is (app-wide 401s are plain strings)', () => {
    expect(requestProblem(failure({ status: 401 })).message).toBe(
      'Your session ended. Sign in again.',
    )
  })

  it('marks a 404 as expired so the inputs can be resubmitted', () => {
    expect(requestProblem(failure({ status: 404 }))).toMatchObject({ expired: true })
  })

  it('keeps the running analysis id from a 409', () => {
    const problem = requestProblem(
      failure({ status: 409, code: 'analysis_in_progress', body: { analysis_id: 'run-1' } }),
    )

    expect(problem.runningAnalysisId).toBe('run-1')
  })

  it('still explains a 409 whose body has no id', () => {
    const problem = requestProblem(failure({ status: 409, code: 'analysis_in_progress', body: {} }))

    expect(problem.runningAnalysisId).toBeUndefined()
    expect(problem.message).toMatch(/already have an analysis running/i)
  })

  it('turns Retry-After into a wait', () => {
    expect(requestProblem(failure({ status: 429, retryAfter: 120 })).message).toBe(
      'Too many requests. Try again in 2 minutes.',
    )
  })

  it('reports a busy service with its wait', () => {
    expect(requestProblem(failure({ status: 503, retryAfter: 30 })).message).toMatch(
      /busy or unavailable\. Try again in 30 seconds\./,
    )
  })

  it.each([
    ['invalid_github_url', 422, 'github'],
    ['consent_required', 422, 'consent'],
    ['cv_and_cv_text', 422, 'cv'],
    ['no_candidate_source', 422, 'sources'],
    ['invalid_job', 422, 'job'],
    ['invalid_url', 422, 'job'],
    ['file_too_large', 413, 'cv'],
    ['unsupported_type', 415, 'cv'],
  ])('shows the server message for %s on the %s field', (code, status, field) => {
    expect(requestProblem(failure({ status, code }))).toEqual({
      message: 'The server says so.',
      field,
    })
  })

  it('shows the server message for an unknown code without guessing a field', () => {
    expect(requestProblem(failure({ status: 422, code: 'brand_new' }))).toEqual({
      message: 'The server says so.',
      field: undefined,
    })
  })

  it('does not echo raw validation errors', () => {
    const problem = requestProblem(failure({ status: 422, detail: 'Field required' }))

    expect(problem.message).toBe("Some of the input wasn't accepted. Check it and try again.")
  })

  it('treats an uncoded 413 as a CV size problem', () => {
    expect(requestProblem(failure({ status: 413 }))).toEqual({
      message: 'That file is larger than 5 MB.',
      field: 'cv',
    })
  })

  it('falls back to a generic message', () => {
    expect(requestProblem(failure({ status: 500 })).message).toBe(
      'Something went wrong. Please try again.',
    )
  })

  it('treats a coded not_found 404 the same as an uncoded one: start again, inputs kept', () => {
    const coded = requestProblem(
      failure({ status: 404, code: 'not_found', body: { detail: { code: 'not_found' } } }),
    )

    expect(coded).toMatchObject({ expired: true })
    expect(coded.message).toMatch(/start it again/i)
  })

  it('treats a coded unavailable 503 the same busy-service way as an uncoded one', () => {
    const coded = requestProblem(
      failure({ status: 503, code: 'unavailable', retryAfter: 30, body: {} }),
    )

    expect(coded.message).toMatch(/busy or unavailable\. Try again in 30 seconds\./)
  })

  it("treats a coded analysis_not_found 404 the same as job intake's not_found (amendment 3)", () => {
    const coded = requestProblem(failure({ status: 404, code: 'analysis_not_found', body: {} }))

    expect(coded).toMatchObject({ expired: true })
    expect(coded.message).toMatch(/start it again/i)
  })

  it('shows the generic message for a FastAPI validation list, not the raw cv_text detail (amendment 3)', () => {
    const problem = requestProblem(
      failure({ status: 422, detail: 'cv_text: String should have at most 40000 characters' }),
    )

    expect(problem).toEqual({
      message: "Some of the input wasn't accepted. Check it and try again.",
    })
  })
})

describe('jobRecovery', () => {
  it('offers paste, not retry, when a site blocks us', () => {
    expect(jobRecovery(failed('blocked_by_robots', 'paste'), 'url')).toEqual({
      offerRetry: false,
      offerPaste: true,
    })
  })

  it('offers both for a timeout', () => {
    expect(jobRecovery(failed('fetch_timeout', 'paste'), 'url')).toEqual({
      offerRetry: true,
      offerPaste: true,
    })
  })

  it('offers retry for a model failure on pasted text, with nothing to switch to', () => {
    expect(jobRecovery(failed('ai_unavailable', 'retry'), 'text')).toEqual({
      offerRetry: true,
      offerPaste: false,
    })
  })

  it('offers retry when the queue says wait', () => {
    expect(jobRecovery(failed('queue_unavailable', 'wait'), 'url').offerRetry).toBe(true)
  })

  it('asks for a fixed URL rather than a retry', () => {
    expect(jobRecovery(failed('invalid_url', 'fix_url'), 'url')).toEqual({
      offerRetry: false,
      offerPaste: true,
    })
  })

  it('offers the paste tab for input_too_long from a fetched url, never a pointless retry (amendment 4)', () => {
    expect(jobRecovery(failed('input_too_long', 'paste'), 'url')).toEqual({
      offerRetry: false,
      offerPaste: true,
    })
  })

  it('offers neither button for input_too_long when already on the paste tab (amendment 4)', () => {
    expect(jobRecovery(failed('input_too_long', 'paste'), 'text')).toEqual({
      offerRetry: false,
      offerPaste: false,
    })
  })
})

describe('analysisFailureAction', () => {
  it.each([
    ['file_too_large', 'edit_candidate'],
    ['unsupported_type', 'edit_candidate'],
    ['encrypted_pdf', 'edit_candidate'],
    ['too_many_pages', 'edit_candidate'],
    ['unsafe_docx', 'edit_candidate'],
    ['github_user_not_found', 'edit_candidate'],
    ['scanned_pdf_suspected', 'paste_cv'],
    ['unreadable_document', 'paste_cv'],
    ['invalid_job', 'edit_job'],
    ['ai_timeout', 'retry'],
    ['something_new', 'retry'],
  ])('%s → %s', (code, action) => {
    expect(analysisFailureAction(failed(code))).toBe(action)
  })

  it('waits when the backend says so', () => {
    expect(analysisFailureAction(failed('queue_unavailable', 'wait'))).toBe('wait')
  })

  it.each([
    ['not_a_cv', 'paste_cv', 'paste_cv'],
    ['invalid_github_url', 'fix_github_url', 'edit_candidate'],
  ] as const)('%s (recovery %s) → %s', (code, recovery, action) => {
    expect(analysisFailureAction(failed(code, recovery))).toBe(action)
  })

  it.each([
    ['choose_file', 'edit_candidate'],
    ['paste_cv', 'paste_cv'],
    ['fix_github_url', 'edit_candidate'],
    ['retry_or_continue', 'retry'],
  ] as const)('an unknown code with recovery %s → %s', (recovery, action) => {
    expect(analysisFailureAction(failed('brand_new_code', recovery))).toBe(action)
  })

  it('degrades an unknown future recovery value to a plain message, never throwing', () => {
    const exotic = failed('brand_new_code', 'something_not_yet_invented' as Recovery)

    expect(() => analysisFailureAction(exotic)).not.toThrow()
    expect(analysisFailureAction(exotic)).toBe('retry')
  })
})

describe('retryLimitProblem (amendment 3: retry spends a 5/hour analysis token)', () => {
  it('gives a specific analysis-limit message for a 429, not the generic rate-limit one', () => {
    const problem = retryLimitProblem(failure({ status: 429, retryAfter: 900 }))

    expect(problem.message).toBe(
      "You've used all your analysis retries for this hour. Try again in 15 minutes.",
    )
    expect(problem.message).not.toMatch(/^Too many requests\./)
  })

  it('falls back to the ordinary mapping for anything that is not a 429', () => {
    expect(retryLimitProblem(failure({ status: 404 }))).toMatchObject({ expired: true })
    expect(retryLimitProblem(failure({ status: 401 })).message).toBe(
      'Your session ended. Sign in again.',
    )
  })
})

describe('runningJobId (amendment 4: one active intake per user)', () => {
  it('reads the running job id from a job_in_progress 409', () => {
    const running = failure({
      status: 409,
      code: 'job_in_progress',
      body: { job_id: 'job-9' },
    })

    expect(runningJobId(running)).toBe('job-9')
  })

  it('is undefined for any other code, even if the body happens to carry a job_id', () => {
    const other = failure({
      status: 409,
      code: 'analysis_in_progress',
      body: { job_id: 'job-9' },
    })

    expect(runningJobId(other)).toBeUndefined()
  })

  it('is undefined when the body has no job_id', () => {
    expect(
      runningJobId(failure({ status: 409, code: 'job_in_progress', body: {} })),
    ).toBeUndefined()
  })

  it('never surfaces as a requestProblem error message (it is not an error state)', () => {
    const running = failure({
      status: 409,
      code: 'job_in_progress',
      detail: 'A job intake is already running.',
      body: { job_id: 'job-9' },
    })

    // requestProblem is the generic error mapper; job_in_progress is deliberately not special-
    // cased there because the caller (useJobIntake) resumes polling instead of showing an error.
    // The natural fallthrough still returns a sane message if something calls it by mistake.
    expect(requestProblem(running).message).toBe('A job intake is already running.')
  })
})
