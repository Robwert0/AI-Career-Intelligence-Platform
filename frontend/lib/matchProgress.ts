import type { Problem } from './matchErrors'
import type { AnalysisStage, AnalysisView, JobStage, JobView } from './match'
import type { JobTab } from './matchInputs'

const NO_REPORT_PROBLEM: Problem = {
  message: 'The analysis finished, but no report came back. Try again.',
}
const NO_DECISION_PROBLEM: Problem = {
  message: 'The analysis paused, but we could not tell why. Start over and try again.',
}

// The backend now enforces status↔payload invariants server-side (a violation is its own 500,
// never a 200 with a hole in it) -- but the browser only ever casts the parsed JSON to our TS
// type (lib/http.ts), so a stale build or a future backend regression could still hand us one.
// Truthiness, not `=== null`, sidesteps TS flagging the comparison as unreachable now that the
// type says these fields can't be null for these statuses.
export function analysisProblem(view: AnalysisView): Problem | null {
  if (view.status === 'done' && !view.report) return NO_REPORT_PROBLEM
  if (view.status === 'needs_decision' && !view.decision) return NO_DECISION_PROBLEM
  return null
}

export type StageState = 'done' | 'current' | 'pending'
export type StageItem = { stage: string; label: string; state: StageState }

const JOB_STAGE_LABELS: Record<JobStage, string> = {
  reading: 'Reading the job page',
  extracting: 'Extracting the requirements',
}

const ANALYSIS_STAGE_LABELS: Record<AnalysisStage, string> = {
  reading_cv: 'Reading your CV',
  reading_github: 'Reading your GitHub profile',
  matching: 'Matching evidence to requirements',
  assessing: 'Assessing each requirement',
  scoring: 'Calculating the alignment estimate',
  recommending: 'Writing recommendations',
}

function withStates<S extends string>(
  stages: S[],
  labels: Record<S, string>,
  progress: { status: string; stage: S | null } | null,
): StageItem[] {
  const finished = progress?.status === 'done'
  // stage: null means "not started" only before or during the queue; once work has begun
  // (running, or a resumed job/analysis whose stage briefly lags a Redis round-trip) it means
  // "the first stage, not yet reported" rather than "nothing in progress".
  const notStarted = progress === null || progress.status === 'queued'
  const current = notStarted ? -1 : progress.stage === null ? 0 : stages.indexOf(progress.stage)
  return stages.map((stage, index) => ({
    stage,
    label: labels[stage],
    state:
      finished || (current !== -1 && index < current)
        ? 'done'
        : index === current
          ? 'current'
          : 'pending',
  }))
}

export function jobStages(tab: JobTab, view: JobView | null): StageItem[] {
  const stages: JobStage[] = tab === 'url' ? ['reading', 'extracting'] : ['extracting']
  return withStates(stages, JOB_STAGE_LABELS, view)
}

export function analysisStages(
  sources: { cv: boolean; github: boolean },
  view: AnalysisView | null,
): StageItem[] {
  const stages: AnalysisStage[] = []
  if (sources.cv) stages.push('reading_cv')
  if (sources.github) stages.push('reading_github')
  stages.push('matching', 'assessing', 'scoring', 'recommending')
  return withStates(stages, ANALYSIS_STAGE_LABELS, view)
}

export function queueText(position: number | null): string | null {
  if (position === null) return null
  if (position === 0) return "You're next in the queue."
  return `${position} ${position === 1 ? 'analysis' : 'analyses'} ahead of you in the queue.`
}

function currentStep(items: StageItem[]): string | null {
  const index = items.findIndex((item) => item.state === 'current')
  if (index === -1) return null
  return `Step ${index + 1} of ${items.length}: ${items[index].label}.`
}

export function jobAnnouncement(view: JobView | null, items: StageItem[]): string {
  if (view === null) return 'Sending the job.'
  switch (view.status) {
    case 'queued':
      return 'Waiting to start.'
    case 'running':
      return currentStep(items) ?? 'Reading the job.'
    case 'failed':
      return `Could not read the job: ${view.error?.message ?? 'unknown error.'}`
    case 'done':
      return 'Job read. Check the requirements below.'
  }
}

export function analysisAnnouncement(view: AnalysisView | null, items: StageItem[]): string {
  if (view === null) return 'Starting the analysis.'
  switch (view.status) {
    case 'queued':
      return `Waiting to start. ${queueText(view.queue_position) ?? ''}`.trim()
    case 'running':
      return currentStep(items) ?? 'Analysing.'
    case 'needs_decision':
      return `Paused: ${view.decision?.error.message ?? 'a source could not be read.'}`
    case 'failed':
      return `The analysis failed: ${view.error?.message ?? 'unknown error.'}`
    case 'done':
      return 'Analysis complete. Your report is ready.'
  }
}
