import { describe, expect, it } from 'vitest'
import type { AnalysisView, JobView } from '../match'
import {
  analysisAnnouncement,
  analysisProblem,
  analysisStages,
  jobAnnouncement,
  jobStages,
  queueText,
  type StageItem,
} from '../matchProgress'

function jobView(patch: Partial<JobView>): JobView {
  return {
    job_id: 'j1',
    status: 'running',
    stage: null,
    error: null,
    posting: null,
    source_url: null,
    input_truncated: false,
    ...patch,
  }
}

function analysisView(patch: Partial<AnalysisView>): AnalysisView {
  return {
    analysis_id: 'a1',
    status: 'running',
    stage: null,
    queue_position: null,
    error: null,
    decision: null,
    report: null,
    ...patch,
  }
}

function states(items: StageItem[]): string[] {
  return items.map((item) => `${item.stage}:${item.state}`)
}

const BOTH = { cv: true, github: true }
const CV_ONLY = { cv: true, github: false }

describe('jobStages', () => {
  it('shows every stage pending before the first poll', () => {
    expect(states(jobStages('url', null))).toEqual(['reading:pending', 'extracting:pending'])
  })

  it('marks earlier stages done and the current one current', () => {
    expect(states(jobStages('url', jobView({ stage: 'extracting' })))).toEqual([
      'reading:done',
      'extracting:current',
    ])
  })

  it('skips reading a page for pasted text', () => {
    expect(states(jobStages('text', jobView({ status: 'queued' })))).toEqual(['extracting:pending'])
  })

  it('shows the first stage as current while running with no stage yet, not every stage pending', () => {
    expect(states(jobStages('url', jobView({ status: 'running', stage: null })))).toEqual([
      'reading:current',
      'extracting:pending',
    ])
  })
})

describe('analysisStages', () => {
  it('lists the CV and GitHub stages only for the sources given', () => {
    expect(analysisStages({ cv: false, github: true }, null).map((item) => item.stage)).toEqual([
      'reading_github',
      'matching',
      'assessing',
      'scoring',
      'recommending',
    ])
  })

  it('tracks the current stage', () => {
    expect(states(analysisStages(BOTH, analysisView({ stage: 'assessing' })))).toEqual([
      'reading_cv:done',
      'reading_github:done',
      'matching:done',
      'assessing:current',
      'scoring:pending',
      'recommending:pending',
    ])
  })

  it('marks everything done when the analysis is done', () => {
    const items = analysisStages(CV_ONLY, analysisView({ status: 'done' }))

    expect(items.every((item) => item.state === 'done')).toBe(true)
  })

  it('marks nothing current for a stage outside the list', () => {
    const items = analysisStages(CV_ONLY, analysisView({ stage: 'reading_github' }))

    expect(items.every((item) => item.state === 'pending')).toBe(true)
  })

  it('shows the first stage as current while running with no stage yet (a resumed analysis, or right after dequeue), not every stage pending', () => {
    const items = analysisStages(BOTH, analysisView({ status: 'running', stage: null }))

    expect(states(items)).toEqual([
      'reading_cv:current',
      'reading_github:pending',
      'matching:pending',
      'assessing:pending',
      'scoring:pending',
      'recommending:pending',
    ])
  })

  it('still shows everything pending while queued, even though queued also carries stage: null', () => {
    const items = analysisStages(CV_ONLY, analysisView({ status: 'queued', stage: null }))

    expect(items.every((item) => item.state === 'pending')).toBe(true)
  })
})

describe('queueText', () => {
  it.each([
    [null, null],
    [0, "You're next in the queue."],
    [1, '1 analysis ahead of you in the queue.'],
    [3, '3 analyses ahead of you in the queue.'],
  ])('%s → %s', (position, expected) => {
    expect(queueText(position)).toBe(expected)
  })
})

describe('announcements', () => {
  it('announces the queue', () => {
    const view = analysisView({ status: 'queued', queue_position: 2 })

    expect(analysisAnnouncement(view, analysisStages(CV_ONLY, view))).toBe(
      'Waiting to start. 2 analyses ahead of you in the queue.',
    )
  })

  it('announces the step with its position', () => {
    const view = analysisView({ stage: 'matching' })

    expect(analysisAnnouncement(view, analysisStages(CV_ONLY, view))).toBe(
      'Step 2 of 5: Matching evidence to requirements.',
    )
  })

  it('announces a pause with its reason', () => {
    const view = analysisView({
      status: 'needs_decision',
      decision: {
        failed_source: 'github',
        error: {
          code: 'github_rate_limited',
          message: 'GitHub is rate limited.',
          recovery: 'retry',
        },
      },
    })

    expect(analysisAnnouncement(view, [])).toBe('Paused: GitHub is rate limited.')
  })

  it('shows a github_rate_limited message with its own UTC retry time verbatim, appending nothing (amendment 3)', () => {
    const view = analysisView({
      status: 'needs_decision',
      decision: {
        failed_source: 'github',
        error: {
          code: 'github_rate_limited',
          message: 'GitHub rate limit reached. Try again after 14:32 UTC.',
          recovery: 'retry',
        },
      },
    })

    expect(analysisAnnouncement(view, [])).toBe(
      'Paused: GitHub rate limit reached. Try again after 14:32 UTC.',
    )
  })

  it('announces a failure and completion', () => {
    const failed = analysisView({
      status: 'failed',
      error: { code: 'ai_unavailable', message: 'The model is unavailable.', recovery: 'retry' },
    })

    expect(analysisAnnouncement(failed, [])).toBe('The analysis failed: The model is unavailable.')
    expect(analysisAnnouncement(analysisView({ status: 'done' }), [])).toBe(
      'Analysis complete. Your report is ready.',
    )
    expect(analysisAnnouncement(null, [])).toBe('Starting the analysis.')
  })

  it('announces job progress', () => {
    const view = jobView({ stage: 'reading' })

    expect(jobAnnouncement(view, jobStages('url', view))).toBe('Step 1 of 2: Reading the job page.')
    expect(jobAnnouncement(null, [])).toBe('Sending the job.')
  })
})

describe('analysisProblem (defensive: the backend now enforces these invariants and 500s instead of violating them, but a parsed JSON body is never actually checked against the TS type at runtime)', () => {
  it('is null for an ordinary done report', () => {
    expect(analysisProblem(analysisView({ status: 'done', report: {} as never }))).toBeNull()
  })

  it('is null while queued, running, or failed with an error', () => {
    expect(analysisProblem(analysisView({ status: 'queued' }))).toBeNull()
    expect(analysisProblem(analysisView({ status: 'running' }))).toBeNull()
    expect(
      analysisProblem(
        analysisView({
          status: 'failed',
          error: { code: 'internal_error', message: 'x', recovery: 'retry' },
        }),
      ),
    ).toBeNull()
  })

  it('is null for a well-formed needs_decision', () => {
    const view = analysisView({
      status: 'needs_decision',
      decision: {
        failed_source: 'cv',
        error: { code: 'not_a_cv', message: 'x', recovery: 'paste_cv' },
      },
    })

    expect(analysisProblem(view)).toBeNull()
  })

  it('flags a done status with no report, instead of a caller crashing on report.score', () => {
    const problem = analysisProblem(analysisView({ status: 'done', report: null as never }))

    expect(problem?.message).toMatch(/no report came back/i)
  })

  it('flags a needs_decision with no decision, instead of a dead-end screen with no buttons', () => {
    const problem = analysisProblem(analysisView({ status: 'needs_decision', decision: null }))

    expect(problem?.message).toMatch(/paused/i)
  })
})
