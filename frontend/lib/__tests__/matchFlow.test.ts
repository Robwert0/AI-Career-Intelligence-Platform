import { describe, expect, it } from 'vitest'
import { toDraft } from '../jobDraft'
import type { MatchReport } from '../match'
import { INITIAL_FLOW, matchFlow, type FlowState } from '../matchFlow'

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

function at(patch: Partial<FlowState>): FlowState {
  return { ...INITIAL_FLOW, ...patch }
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

  it('starts over from nothing', () => {
    const done = at({ step: 'report', draft: DRAFT, report: REPORT, analysisId: 'a1' })

    expect(matchFlow(done, { type: 'startOver' })).toEqual(INITIAL_FLOW)
  })
})
