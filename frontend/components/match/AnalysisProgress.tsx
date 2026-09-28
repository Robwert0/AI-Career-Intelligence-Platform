'use client'

import { useEffect, useState } from 'react'
import { describedBy } from '@/lib/aria'
import { decisionPanelKind } from '@/lib/decisionPanel'
import type { Decision, FailureOut, MatchReport } from '@/lib/match'
import { analysisFailureAction, type Problem } from '@/lib/matchErrors'
import {
  buildCvRetryForm,
  buildGithubRetryForm,
  candidateSources,
  cvRetryError,
  githubRetryError,
  type CandidateInput,
} from '@/lib/matchInputs'
import { analysisAnnouncement, analysisStages, queueText } from '@/lib/matchProgress'
import { useAnalysis } from '@/lib/useAnalysis'
import { CvInput } from './CvInput'
import { FieldError } from './Field'
import { Announcer, StageList } from './StageList'
import { ALERT, FIELD, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON, TEXT_BUTTON } from './styles'

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
        <DecisionPanel
          decision={decision}
          candidate={props.candidate}
          onCandidateChange={props.onCandidateChange}
          acting={analysis.acting}
          onRetry={analysis.retry}
          onContinue={() => void analysis.continueWithout()}
        />
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

type DecisionPanelProps = {
  decision: Decision
  candidate: CandidateInput
  onCandidateChange: (patch: Partial<CandidateInput>) => void
  acting: boolean
  onRetry: (form?: FormData) => Promise<void>
  onContinue: () => void
}

// Follows decision.error.recovery, not failed_source alone (Amendment 5): the same CV failure can
// need a brand new file, a pasted excerpt, or nothing at all (the model just needs another try
// with the CV already on hand), and a GitHub failure that names the wrong user must never offer a
// blind retry -- that would just re-fetch the same bad URL and spend another rate-limited token.
function DecisionPanel({
  decision,
  candidate,
  onCandidateChange,
  acting,
  onRetry,
  onContinue,
}: DecisionPanelProps) {
  const kind = decisionPanelKind(decision.error.recovery)
  const isCv = decision.failed_source === 'cv'

  useEffect(() => {
    if (!isCv) return
    if (kind === 'paste_cv' && candidate.cvMode !== 'text') onCandidateChange({ cvMode: 'text' })
    if (kind === 'choose_file' && candidate.cvMode !== 'file') onCandidateChange({ cvMode: 'file' })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run only when the decision itself changes
  }, [decision, isCv, kind])

  return (
    <section aria-labelledby="decision-title" className={ALERT}>
      <h3 id="decision-title" tabIndex={-1} className="font-medium">
        {isCv ? "We couldn't read your CV" : "We couldn't read your GitHub profile"}
      </h3>
      <p>{decision.error.message}</p>

      {isCv && (kind === 'choose_file' || kind === 'paste_cv') ? (
        <CvRetryPanel
          candidate={candidate}
          onCandidateChange={onCandidateChange}
          acting={acting}
          onRetry={onRetry}
        />
      ) : null}

      {!isCv && kind === 'fix_github_url' ? (
        <GithubUrlRetryPanel candidate={candidate} acting={acting} onRetry={onRetry} />
      ) : null}

      <div className="flex flex-wrap gap-2">
        {kind === 'retry_or_continue' ? (
          <button
            type="button"
            disabled={acting}
            onClick={() => void onRetry(isCv ? buildCvRetryForm(candidate) : undefined)}
            className={PRIMARY_BUTTON}
          >
            Retry
          </button>
        ) : null}
        <button type="button" disabled={acting} onClick={onContinue} className={SECONDARY_BUTTON}>
          Continue without {isCv ? 'your CV' : 'GitHub'}
        </button>
      </div>
    </section>
  )
}

function CvRetryPanel({
  candidate,
  onCandidateChange,
  acting,
  onRetry,
}: {
  candidate: CandidateInput
  onCandidateChange: (patch: Partial<CandidateInput>) => void
  acting: boolean
  onRetry: (form?: FormData) => Promise<void>
}) {
  const [problem, setProblem] = useState<string | null>(null)

  function retry() {
    const error = cvRetryError(candidate)
    setProblem(error)
    if (error === null) void onRetry(buildCvRetryForm(candidate))
  }

  return (
    <>
      <CvInput
        idPrefix="retry"
        candidate={candidate}
        error={problem ?? undefined}
        onChange={onCandidateChange}
      />
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={acting} onClick={retry} className={PRIMARY_BUTTON}>
          Retry with this CV
        </button>
      </div>
    </>
  )
}

function GithubUrlRetryPanel({
  candidate,
  acting,
  onRetry,
}: {
  candidate: CandidateInput
  acting: boolean
  onRetry: (form?: FormData) => Promise<void>
}) {
  const [url, setUrl] = useState(candidate.githubUrl)
  const [problem, setProblem] = useState<string | null>(null)

  function retry() {
    const error = githubRetryError(url)
    setProblem(error)
    if (error === null) void onRetry(buildGithubRetryForm(url))
  }

  return (
    <div className="space-y-2">
      <label htmlFor="retry-github-url" className={LABEL}>
        GitHub profile
      </label>
      <input
        id="retry-github-url"
        type="url"
        inputMode="url"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        aria-invalid={Boolean(problem)}
        aria-describedby={describedBy(problem && 'retry-github-url-error')}
        className={FIELD}
      />
      <FieldError id="retry-github-url-error" message={problem} />
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={acting} onClick={retry} className={PRIMARY_BUTTON}>
          Retry with this URL
        </button>
      </div>
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
