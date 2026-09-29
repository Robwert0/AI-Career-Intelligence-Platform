import type { JobDraft } from './jobDraft'
import type { MatchReport } from './match'
import { EMPTY_CANDIDATE, EMPTY_JOB_INPUT, type CandidateInput, type JobInput } from './matchInputs'

export type Step = 'job' | 'candidate' | 'analysis' | 'report'

// A union on `step`: only the job step can be draft-less, and only candidate/analysis/report
// have a confirmed draft to show or re-run; only analysis/report have the analysis id that
// produced them, and only report has the report itself.
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
      draft: JobDraft
      inputTruncated: boolean
      analysisId: string
      report: null
    })
  | (FlowCommon & {
      step: 'report'
      draft: JobDraft
      inputTruncated: boolean
      analysisId: string
      report: MatchReport
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
      return state.draft === null
        ? state
        : {
            step: 'analysis',
            jobInput: state.jobInput,
            candidate: state.candidate,
            draft: state.draft,
            inputTruncated: state.inputTruncated,
            analysisId: action.analysisId,
            report: null,
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
          }
        : state
    case 'analysisAbandoned':
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
