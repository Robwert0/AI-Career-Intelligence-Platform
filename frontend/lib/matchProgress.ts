import type { AnalysisStage, AnalysisView, JobStage, JobView } from './match'
import type { JobTab } from './matchInputs'

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
  const current =
    progress === null || progress.status === 'queued' || progress.stage === null
      ? -1
      : stages.indexOf(progress.stage)
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
