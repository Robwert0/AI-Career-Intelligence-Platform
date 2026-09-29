import type { ApiResult } from './http'
import type { AnalysisSubmitted } from './match'
import { requestProblem, retryLimitProblem, type Problem } from './matchErrors'

export type DecideOutcome =
  | { type: 'moved'; analysisId: string }
  | { type: 'succeeded' }
  | { type: 'stale' }
  | { type: 'session_ended' }
  | { type: 'problem'; problem: Problem }

// The response to POST .../continue or .../retry, pulled out of useAnalysis so every branch is
// unit-testable without mounting the hook: a stale 409 (the analysis already moved past the
// decision the user was acting on -- e.g. a slow double click) just means re-poll it, not an
// error to show; retry spends a scarce 5/hour token so its 429 needs its own wording, while
// continue only spends the ordinary poll limit.
export function decideOutcome(
  action: 'continue' | 'retry',
  analysisId: string,
  result: ApiResult<AnalysisSubmitted>,
): DecideOutcome {
  if (result.ok) {
    return result.data.analysis_id === analysisId
      ? { type: 'succeeded' }
      : { type: 'moved', analysisId: result.data.analysis_id }
  }
  if (result.code === 'not_awaiting_decision') return { type: 'stale' }
  if (result.status === 401) return { type: 'session_ended' }
  return {
    type: 'problem',
    problem: action === 'retry' ? retryLimitProblem(result) : requestProblem(result),
  }
}

export type DiscardOutcome =
  { type: 'reset' } | { type: 'session_ended' } | { type: 'problem'; problem: Problem }

// analysis_running (running, or already done/failed) and analysis_not_found both mean there is
// nothing left to release server-side, so the local reset is safe. Any other failure must not
// reset: the one-active-analysis lock would still be held and the next submit would 409 straight
// back to the analysis the user just tried to leave.
const NOTHING_TO_DISCARD = new Set(['analysis_running', 'analysis_not_found'])

export function discardOutcome(result: ApiResult<AnalysisSubmitted>): DiscardOutcome {
  if (result.ok) return { type: 'reset' }
  if (result.code !== undefined && NOTHING_TO_DISCARD.has(result.code)) return { type: 'reset' }
  if (result.status === 401) return { type: 'session_ended' }
  return { type: 'problem', problem: requestProblem(result) }
}
