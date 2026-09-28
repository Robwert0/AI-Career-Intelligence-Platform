import { describe, expect, it } from 'vitest'
import { toDraft, type JobDraft } from '../jobDraft'
import type { MatchReport } from '../match'
import { INITIAL_FLOW, matchFlow, type FlowState, type Step } from '../matchFlow'
import type { CandidateInput, JobInput } from '../matchInputs'

const DRAFT = toDraft(
  {
    title: 'Backend Engineer',
    company: null,
    responsibilities: [],
    required: [{ text: 'Go', sensitive: false }],
    preferred: [],
  },
  () => 'k1',
)
const PDF = new File(['%PDF-1.7'], 'cv.pdf')
const REPORT = { score: 67 } as unknown as MatchReport

// FlowState is a union on `step`, so an arbitrary test patch can't always be typed as one real
// member (e.g. a patch that only sets `draft` while leaving `step: 'job'` implicit). This fixture
// stays a flat, loosely typed shape and casts once at the end, rather than fighting
// Partial<union> distribution.
type FlowStatePatch = Partial<{
  step: Step
  jobInput: JobInput
  draft: JobDraft | null
  inputTruncated: boolean
  candidate: CandidateInput
  analysisId: string | null
  report: MatchReport | null
}>

function at(patch: FlowStatePatch): FlowState {
  return { ...INITIAL_FLOW, ...patch } as FlowState
}

describe('matchFlow', () => {
  it('starts on the job step with nothing entered', () => {
    expect(INITIAL_FLOW).toMatchObject({ step: 'job', draft: null, analysisId: null, report: null })
  })

  it('keeps job input edits', () => {
    const state = matchFlow(INITIAL_FLOW, {
      type: 'jobInputChanged',
      input: { tab: 'text', text: 'x' },
    })

    expect(state.jobInput).toEqual({ tab: 'text', url: '', text: 'x' })
  })

  it('shows the preview after extraction, still on the job step', () => {
    const state = matchFlow(INITIAL_FLOW, {
      type: 'jobExtracted',
      draft: DRAFT,
      inputTruncated: true,
    })

    expect(state).toMatchObject({ step: 'job', draft: DRAFT, inputTruncated: true })
  })

  it('moves on only with a draft', () => {
    expect(matchFlow(INITIAL_FLOW, { type: 'jobConfirmed' })).toBe(INITIAL_FLOW)
    expect(matchFlow(at({ draft: DRAFT }), { type: 'jobConfirmed' }).step).toBe('candidate')
  })

  it('discards a draft but keeps what was typed', () => {
    const typed = at({ draft: DRAFT, jobInput: { tab: 'url', url: 'https://a.example', text: '' } })

    const state = matchFlow(typed, { type: 'draftDiscarded' })

    expect(state.draft).toBeNull()
    expect(state.jobInput.url).toBe('https://a.example')
  })

  it('merges candidate edits', () => {
    const state = matchFlow(INITIAL_FLOW, { type: 'candidateChanged', candidate: { cvFile: PDF } })

    expect(state.candidate.cvFile).toBe(PDF)
    expect(state.candidate.cvMode).toBe('file')
  })

  it('starts and finishes an analysis', () => {
    const started = matchFlow(at({ step: 'candidate', draft: DRAFT }), {
      type: 'analysisStarted',
      analysisId: 'a1',
    })
    const finished = matchFlow(started, { type: 'analysisFinished', report: REPORT })

    expect(started).toMatchObject({ step: 'analysis', analysisId: 'a1' })
    expect(finished).toMatchObject({ step: 'report', report: REPORT })
  })

  it('ignores a late report once the user has moved on', () => {
    const state = at({ step: 'job', draft: DRAFT })

    expect(matchFlow(state, { type: 'analysisFinished', report: REPORT })).toBe(state)
  })

  it('goes back to the evidence step when an analysis is abandoned, keeping consent', () => {
    const running = at({
      step: 'analysis',
      draft: DRAFT,
      analysisId: 'a1',
      candidate: { ...INITIAL_FLOW.candidate, cvFile: PDF, consent: true },
    })

    const state = matchFlow(running, { type: 'analysisAbandoned' })

    expect(state).toMatchObject({ step: 'candidate', analysisId: null })
    expect(state.candidate.consent).toBe(true)
  })

  it('edits the job and re-runs with the candidate inputs kept but consent reset', () => {
    const done = at({
      step: 'report',
      draft: DRAFT,
      analysisId: 'a1',
      report: REPORT,
      candidate: {
        ...INITIAL_FLOW.candidate,
        cvFile: PDF,
        githubUrl: 'https://github.com/x',
        consent: true,
      },
    })

    const state = matchFlow(done, { type: 'editJob' })

    expect(state).toMatchObject({ step: 'job', draft: DRAFT, analysisId: null, report: null })
    expect(state.candidate).toMatchObject({
      cvFile: PDF,
      githubUrl: 'https://github.com/x',
      consent: false,
    })
  })

  it('never enters a step that needs a draft without one (the type now guarantees candidate/analysis/report always have a draft)', () => {
    const noDraft = at({ step: 'job', draft: null })

    expect(matchFlow(noDraft, { type: 'jobConfirmed' })).toBe(noDraft)
    expect(matchFlow(noDraft, { type: 'analysisStarted', analysisId: 'a1' })).toBe(noDraft)
    expect(matchFlow(noDraft, { type: 'analysisAbandoned' })).toBe(noDraft)
  })

  it('starts over from nothing', () => {
    const done = at({ step: 'report', draft: DRAFT, report: REPORT, analysisId: 'a1' })

    expect(matchFlow(done, { type: 'startOver' })).toEqual(INITIAL_FLOW)
  })
})
