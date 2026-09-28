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
