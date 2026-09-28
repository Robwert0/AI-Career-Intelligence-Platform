'use client'

import { useEffect, useState } from 'react'
import type { FailureOut, MatchReport } from '@/lib/match'
import { analysisFailureAction, type Problem } from '@/lib/matchErrors'
import {
  buildCvRetryForm,
  candidateSources,
  cvRetryError,
  type CandidateInput,
} from '@/lib/matchInputs'
import { analysisAnnouncement, analysisStages, queueText } from '@/lib/matchProgress'
import { useAnalysis } from '@/lib/useAnalysis'
import { CvInput } from './CvInput'
import { Announcer, StageList } from './StageList'
import { ALERT, PRIMARY_BUTTON, SECONDARY_BUTTON, TEXT_BUTTON } from './styles'

const UNKNOWN_FAILURE: FailureOut = {
  code: 'unknown',
  message: 'The analysis stopped unexpectedly. Try again.',
  recovery: 'retry',
}

type Props = {
  analysisId: string
  candidate: CandidateInput
  onCandidateChange: (patch: Partial<CandidateInput>) => void
  onReport: (report: MatchReport) => void
  onMoved: (analysisId: string) => void
  onResubmit: () => void
  resubmitting: boolean
  resubmitProblem: Problem | null
  onEditCandidate: (pasteCv: boolean) => void
  onEditJob: () => void
  onStartOver: () => void
}

export function AnalysisProgress(props: Props) {
  const analysis = useAnalysis(props.analysisId, {
    onReport: props.onReport,
    onMoved: props.onMoved,
  })
  const [cvRetryProblem, setCvRetryProblem] = useState<string | null>(null)
  const { view } = analysis
  const given = candidateSources(props.candidate)
  const stages = analysisStages(
    {
      cv: given.cv && !analysis.skipped.includes('cv'),
      github: given.github && !analysis.skipped.includes('github'),
    },
    view,
  )
  const queue = view?.status === 'queued' ? queueText(view.queue_position) : null
  const decision = view?.status === 'needs_decision' ? view.decision : null
  const failure = view?.status === 'failed' ? (view.error ?? UNKNOWN_FAILURE) : null
  const working = view === null || view.status === 'queued' || view.status === 'running'
  const paused = decision !== null

  useEffect(() => {
    if (paused) document.getElementById('decision-title')?.focus()
  }, [paused])

  function retryCv() {
    const problem = cvRetryError(props.candidate)
    setCvRetryProblem(problem)
    if (problem === null) void analysis.retry(buildCvRetryForm(props.candidate))
  }

  return (
    <div className="space-y-6">
      <StageList items={stages} />
      <Announcer text={analysisAnnouncement(view, stages)} />
      {queue ? <p className="text-sm">{queue}</p> : null}
      {working && analysis.problem === null ? (
        <p className="text-sm text-muted">
          This usually takes a few minutes. Keep this tab open until the report is ready.
        </p>
      ) : null}

      {decision ? (
        <section aria-labelledby="decision-title" className={ALERT}>
          <h3 id="decision-title" tabIndex={-1} className="font-medium">
            {decision.failed_source === 'cv'
              ? "We couldn't read your CV"
              : "We couldn't read your GitHub profile"}
          </h3>
          <p>{decision.error.message}</p>
          {decision.failed_source === 'cv' ? (
            <CvInput
              idPrefix="retry"
              candidate={props.candidate}
              error={cvRetryProblem ?? undefined}
              onChange={props.onCandidateChange}
            />
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={analysis.acting}
              onClick={decision.failed_source === 'cv' ? retryCv : () => void analysis.retry()}
              className={PRIMARY_BUTTON}
            >
              {decision.failed_source === 'cv' ? 'Retry with this CV' : 'Retry'}
            </button>
            <button
              type="button"
              disabled={analysis.acting}
              onClick={() => void analysis.continueWithout()}
              className={SECONDARY_BUTTON}
            >
              Continue without {decision.failed_source === 'cv' ? 'your CV' : 'GitHub'}
            </button>
          </div>
        </section>
      ) : null}

      {failure ? (
        <div role="alert" className={ALERT}>
          <p>{failure.message}</p>
          <ResubmitNote problem={props.resubmitProblem} onOpen={props.onMoved} />
          <div className="flex flex-wrap items-center gap-2">
            <FailureAction
              failure={failure}
              onResubmit={props.onResubmit}
              resubmitting={props.resubmitting}
              onEditCandidate={props.onEditCandidate}
              onEditJob={props.onEditJob}
            />
            <button type="button" onClick={props.onStartOver} className={TEXT_BUTTON}>
              Start over
            </button>
          </div>
        </div>
      ) : null}

      {analysis.problem ? (
        <div role="alert" className={ALERT}>
          <p>{analysis.problem.message}</p>
          <ResubmitNote problem={props.resubmitProblem} onOpen={props.onMoved} />
          <div className="flex flex-wrap items-center gap-2">
            {analysis.problem.expired ? (
              <button
                type="button"
                onClick={props.onResubmit}
                disabled={props.resubmitting}
                className={SECONDARY_BUTTON}
              >
                Start the analysis again
              </button>
            ) : (
              <button type="button" onClick={analysis.resume} className={SECONDARY_BUTTON}>
                Check again
              </button>
            )}
            <button type="button" onClick={props.onStartOver} className={TEXT_BUTTON}>
              Start over
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function ResubmitNote({
  problem,
  onOpen,
}: {
  problem: Problem | null
  onOpen: (analysisId: string) => void
}) {
  if (problem === null) return null
  const runningId = problem.runningAnalysisId
  return (
    <div className="space-y-2">
      <p>{problem.message}</p>
      {runningId ? (
        <button type="button" onClick={() => onOpen(runningId)} className={SECONDARY_BUTTON}>
          Open the running analysis
        </button>
      ) : null}
    </div>
  )
}

function FailureAction({
  failure,
  onResubmit,
  resubmitting,
  onEditCandidate,
  onEditJob,
}: {
  failure: FailureOut
  onResubmit: () => void
  resubmitting: boolean
  onEditCandidate: (pasteCv: boolean) => void
  onEditJob: () => void
}) {
  switch (analysisFailureAction(failure)) {
    case 'edit_candidate':
      return (
        <button type="button" onClick={() => onEditCandidate(false)} className={SECONDARY_BUTTON}>
          Change your evidence
        </button>
      )
    case 'paste_cv':
      return (
        <button type="button" onClick={() => onEditCandidate(true)} className={SECONDARY_BUTTON}>
          Paste your CV text instead
        </button>
      )
    case 'edit_job':
      return (
        <button type="button" onClick={onEditJob} className={SECONDARY_BUTTON}>
          Edit the job
        </button>
      )
    case 'retry':
    case 'wait':
      return (
        <button
          type="button"
          onClick={onResubmit}
          disabled={resubmitting}
          className={SECONDARY_BUTTON}
        >
          {resubmitting ? 'Starting…' : 'Try again'}
        </button>
      )
  }
}
