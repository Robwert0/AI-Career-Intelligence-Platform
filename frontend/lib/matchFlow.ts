import type { JobDraft } from './jobDraft'
import type { MatchReport } from './match'
import { EMPTY_CANDIDATE, EMPTY_JOB_INPUT, type CandidateInput, type JobInput } from './matchInputs'

export type Step = 'job' | 'candidate' | 'analysis' | 'report'

// A union on `step`: candidate needs a confirmed draft; analysis/report have one unless the
// analysis was restored after a reload, where draft is null because the posting is never kept in
// the browser. Only analysis/report have the analysis id that produced them, and only report has
// the report itself.
type FlowCommon = { jobInput: JobInput; candidate: CandidateInput }
export type FlowState =
  | (FlowCommon & {
      step: 'job'
      draft: JobDraft | null
      inputTruncated: boolean
      analysisId: null
      report: null
    })
  | (FlowCommon & {
      step: 'candidate'
      draft: JobDraft
      inputTruncated: boolean
      analysisId: null
      report: null
    })
  | (FlowCommon & {
      step: 'analysis'
      draft: JobDraft | null
      inputTruncated: boolean
      analysisId: string
      report: null
      expiresAt: null
    })
  | (FlowCommon & {
      step: 'report'
      draft: JobDraft | null
      inputTruncated: boolean
      analysisId: string
      report: MatchReport
      expiresAt: number | null
    })

export type FlowAction =
  | { type: 'jobInputChanged'; input: Partial<JobInput> }
  | { type: 'jobExtracted'; draft: JobDraft; inputTruncated: boolean }
  | { type: 'draftChanged'; draft: JobDraft }
  | { type: 'draftDiscarded' }
  | { type: 'jobConfirmed' }
  | { type: 'candidateChanged'; candidate: Partial<CandidateInput> }
  | { type: 'backToJob' }
  | { type: 'analysisStarted'; analysisId: string }
  | { type: 'analysisRestored'; analysisId: string }
  | { type: 'analysisFinished'; report: MatchReport; expiresAt: number | null }
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
      return state.step === 'job' ? { ...state, draft: null, inputTruncated: false } : state
    case 'jobConfirmed':
      return state.draft === null
        ? state
        : {
            step: 'candidate',
            jobInput: state.jobInput,
            candidate: state.candidate,
            draft: state.draft,
            inputTruncated: state.inputTruncated,
            analysisId: null,
            report: null,
          }
    case 'candidateChanged':
      return { ...state, candidate: { ...state.candidate, ...action.candidate } }
    case 'backToJob':
      return {
        step: 'job',
        jobInput: state.jobInput,
        candidate: state.candidate,
        draft: state.draft,
        inputTruncated: state.inputTruncated,
        analysisId: null,
        report: null,
      }
    case 'analysisStarted':
      // A moved or reopened analysis keeps whatever draft this tab still has, including none.
      return state.step === 'job' && state.draft === null
        ? state
        : {
            step: 'analysis',
            jobInput: state.jobInput,
            candidate: state.candidate,
            draft: state.draft,
            inputTruncated: state.inputTruncated,
            analysisId: action.analysisId,
            report: null,
            expiresAt: null,
          }
    case 'analysisRestored':
      return {
        step: 'analysis',
        jobInput: EMPTY_JOB_INPUT,
        candidate: EMPTY_CANDIDATE,
        draft: null,
        inputTruncated: false,
        analysisId: action.analysisId,
        report: null,
        expiresAt: null,
      }
    case 'analysisFinished':
      return state.step === 'analysis'
        ? {
            step: 'report',
            jobInput: state.jobInput,
            candidate: state.candidate,
            draft: state.draft,
            inputTruncated: state.inputTruncated,
            analysisId: state.analysisId,
            report: action.report,
            expiresAt: action.expiresAt,
          }
        : state
    case 'analysisAbandoned':
      if (state.draft === null) {
        // A restored analysis has no posting to go back to: the job must be entered again.
        return state.step === 'job' ? state : { ...INITIAL_FLOW, candidate: state.candidate }
      }
      return {
        step: 'candidate',
        jobInput: state.jobInput,
        candidate: state.candidate,
        draft: state.draft,
        inputTruncated: state.inputTruncated,
        analysisId: null,
        report: null,
      }
    case 'editJob':
      return {
        step: 'job',
        jobInput: state.jobInput,
        candidate: { ...state.candidate, consent: false },
        draft: state.draft,
        inputTruncated: state.inputTruncated,
        analysisId: null,
        report: null,
      }
    case 'startOver':
      return INITIAL_FLOW
  }
}
