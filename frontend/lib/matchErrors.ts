import type { ApiFailure } from './http'
import type { FailureOut, Recovery } from './match'
import type { JobTab } from './matchInputs'
import { waitPhrase } from './messages'

export type MatchField = 'job' | 'sources' | 'cv' | 'github' | 'consent'
export type Problem = {
  message: string
  field?: MatchField
  runningAnalysisId?: string
  expired?: boolean
}
export type JobRecovery = { offerRetry: boolean; offerPaste: boolean }
export type FailureAction = 'retry' | 'wait' | 'edit_candidate' | 'paste_cv' | 'edit_job'

const FIELD_BY_CODE: Record<string, MatchField> = {
  invalid_url: 'job',
  invalid_job: 'job',
  no_candidate_source: 'sources',
  cv_and_cv_text: 'cv',
  file_too_large: 'cv',
  unsupported_type: 'cv',
  unsafe_docx: 'cv',
  invalid_github_url: 'github',
  consent_required: 'consent',
}

const RETRYABLE_FETCH_CODES = new Set(['fetch_timeout', 'site_unavailable'])
const CANDIDATE_INPUT_CODES = new Set([
  'file_too_large',
  'unsupported_type',
  'encrypted_pdf',
  'too_many_pages',
  'unsafe_docx',
  'github_user_not_found',
  'github_rate_limited',
  'github_unavailable',
  'invalid_github_url',
])
const PASTE_CV_CODES = new Set(['scanned_pdf_suspected', 'unreadable_document', 'not_a_cv'])
const JOB_CODES = new Set(['invalid_job', 'not_a_job_posting'])

// A code this map doesn't know yet still resolves through recovery; a recovery value neither map
// knows falls back to 'retry' rather than throwing, so a future backend addition degrades instead
// of crashing. Every recovery value maps to *something other than a blind retry* except 'retry'
// itself, so an unmapped code never surfaces as a futile "Try again" when the server told us what
// to do instead (§ analysisFailureAction).
const ACTION_BY_RECOVERY: Partial<Record<Recovery, FailureAction>> = {
  choose_file: 'edit_candidate',
  paste_cv: 'paste_cv',
  fix_github_url: 'edit_candidate',
  retry_or_continue: 'retry',
  wait: 'wait',
  edit_job: 'edit_job',
  paste: 'paste_cv',
  fix_url: 'edit_job',
}

function idFromBody(body: unknown, field: 'analysis_id' | 'job_id'): string | undefined {
  if (typeof body !== 'object' || body === null) return undefined
  const id = (body as Record<string, unknown>)[field]
  return typeof id === 'string' && id !== '' ? id : undefined
}

// One active job intake per user is not an error state, unlike analysis_in_progress -- the caller
// (useJobIntake) resumes polling the running job instead of showing anything, so this stays a
// standalone extractor rather than a requestProblem branch.
export function runningJobId(failure: ApiFailure): string | undefined {
  return failure.code === 'job_in_progress' ? idFromBody(failure.body, 'job_id') : undefined
}

export function requestProblem(failure: ApiFailure): Problem {
  if (failure.code === 'analysis_in_progress') {
    return {
      message: 'You already have an analysis running. Open it, or wait for it to finish.',
      runningAnalysisId: idFromBody(failure.body, 'analysis_id'),
    }
  }
  switch (failure.status) {
    case 0:
      return { message: 'Could not reach the server. Check your connection and try again.' }
    case 401:
      return { message: 'Your session ended. Sign in again.' }
    case 404:
      return {
        message:
          'This request has expired or no longer exists. Start it again; your inputs are kept.',
        expired: true,
      }
    case 429:
      return { message: `Too many requests. ${waitPhrase(failure.retryAfter)}` }
    case 503:
      return { message: `The service is busy or unavailable. ${waitPhrase(failure.retryAfter)}` }
  }
  if (failure.code !== undefined) {
    return { message: failure.detail, field: FIELD_BY_CODE[failure.code] }
  }
  if (failure.status === 413) return { message: 'That file is larger than 5 MB.', field: 'cv' }
  // FastAPI's own 422 list has no {code, message} (the one shape our API doesn't wrap, per the
  // contract), but http.ts already reduces it to the validators' own .msg text, which is safe and
  // meaningful to show as-is rather than discarding it for a one-size-fits-all message.
  if (failure.status === 422) return { message: failure.detail }
  return { message: 'Something went wrong. Please try again.' }
}

// Retry spends a MATCH_ANALYSIS_USER token (5/hour); continue uses the poll limit and keeps the
// ordinary requestProblem mapping. A 429 from retry needs its own wording so it doesn't read like
// a transient "too many requests" — the user actually used up a scarce resource.
export function retryLimitProblem(failure: ApiFailure): Problem {
  if (failure.status !== 429) return requestProblem(failure)
  return {
    message: `You've used all your analysis retries for this hour. ${waitPhrase(failure.retryAfter)}`,
  }
}

export function jobRecovery(error: FailureOut, tab: JobTab): JobRecovery {
  return {
    offerRetry:
      error.recovery === 'retry' ||
      error.recovery === 'wait' ||
      RETRYABLE_FETCH_CODES.has(error.code),
    offerPaste: tab === 'url',
  }
}

export function analysisFailureAction(error: FailureOut): FailureAction {
  if (CANDIDATE_INPUT_CODES.has(error.code)) return 'edit_candidate'
  if (PASTE_CV_CODES.has(error.code)) return 'paste_cv'
  if (JOB_CODES.has(error.code)) return 'edit_job'
  return ACTION_BY_RECOVERY[error.recovery] ?? 'retry'
}
