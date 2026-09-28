import type { JobDraft } from './jobDraft'
import type { MatchReport } from './match'
import { EMPTY_CANDIDATE, EMPTY_JOB_INPUT, type CandidateInput, type JobInput } from './matchInputs'

export type Step = 'job' | 'candidate' | 'analysis' | 'report'

export type FlowState = {
  step: Step
  jobInput: JobInput
  draft: JobDraft | null
  inputTruncated: boolean
  candidate: CandidateInput
  analysisId: string | null
  report: MatchReport | null
}

export type FlowAction =
  | { type: 'jobInputChanged'; input: Partial<JobInput> }
  | { type: 'jobExtracted'; draft: JobDraft; inputTruncated: boolean }
  | { type: 'draftChanged'; draft: JobDraft }
  | { type: 'draftDiscarded' }
  | { type: 'jobConfirmed' }
  | { type: 'candidateChanged'; candidate: Partial<CandidateInput> }
  | { type: 'backToJob' }
  | { type: 'analysisStarted'; analysisId: string }
  | { type: 'analysisFinished'; report: MatchReport }
  | { type: 'analysisAbandoned' }
  | { type: 'editJob' }
  | { type: 'startOver' }

export const INITIAL_FLOW: FlowState = {
  step: 'job',
  jobInput: EMPTY_JOB_INPUT,
  draft: null,
  inputTruncated: false,
  candidate: EMPTY_CANDIDATE,
  analysisId: null,
  report: null,
}

export function matchFlow(state: FlowState, action: FlowAction): FlowState {
  switch (action.type) {
    case 'jobInputChanged':
      return { ...state, jobInput: { ...state.jobInput, ...action.input } }
    case 'jobExtracted':
      return { ...state, draft: action.draft, inputTruncated: action.inputTruncated }
    case 'draftChanged':
      return state.draft === null ? state : { ...state, draft: action.draft }
    case 'draftDiscarded':
      return { ...state, draft: null, inputTruncated: false }
    case 'jobConfirmed':
      return state.draft === null ? state : { ...state, step: 'candidate' }
    case 'candidateChanged':
      return { ...state, candidate: { ...state.candidate, ...action.candidate } }
    case 'backToJob':
      return { ...state, step: 'job' }
    case 'analysisStarted':
      return { ...state, step: 'analysis', analysisId: action.analysisId, report: null }
    case 'analysisFinished':
      return state.step === 'analysis' ? { ...state, step: 'report', report: action.report } : state
    case 'analysisAbandoned':
      return { ...state, step: 'candidate', analysisId: null }
    case 'editJob':
      return {
        ...state,
        step: 'job',
        analysisId: null,
        report: null,
        candidate: { ...state.candidate, consent: false },
      }
    case 'startOver':
      return INITIAL_FLOW
  }
}
