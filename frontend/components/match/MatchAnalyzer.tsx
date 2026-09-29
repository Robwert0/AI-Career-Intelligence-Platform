'use client'

import { useEffect, useReducer, useRef, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { toDraft, toPosting } from '@/lib/jobDraft'
import { submitAnalysis, type JobView } from '@/lib/match'
import { requestProblem, type Problem } from '@/lib/matchErrors'
import { INITIAL_FLOW, matchFlow, type FlowAction, type Step } from '@/lib/matchFlow'
import { buildAnalysisForm } from '@/lib/matchInputs'
import { useMatchConfig } from '@/lib/useMatchConfig'
import { AnalysisProgress } from './AnalysisProgress'
import { CandidateStep } from './CandidateStep'
import { JobPreview } from './JobPreview'
import { JobSourceForm } from './JobSourceForm'
import { MatchReportView } from './MatchReportView'

const STEPS: { id: Step; label: string }[] = [
  { id: 'job', label: 'The job' },
  { id: 'candidate', label: 'Your evidence' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'report', label: 'Report' },
]

export function MatchAnalyzer() {
  const { sessionExpired } = useAuth()
  const limits = useMatchConfig()
  const [state, dispatch] = useReducer(matchFlow, INITIAL_FLOW)
  const [submitting, setSubmitting] = useState(false)
  const [submitProblem, setSubmitProblem] = useState<Problem | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const shownStep = useRef<Step>(state.step)

  useEffect(() => {
    if (shownStep.current === state.step) return
    shownStep.current = state.step
    headingRef.current?.focus()
  }, [state.step])

  function go(action: FlowAction) {
    setSubmitProblem(null)
    dispatch(action)
  }

  function handleExtracted(view: JobView) {
    if (view.posting === null) return
    dispatch({
      type: 'jobExtracted',
      draft: toDraft(view.posting, () => crypto.randomUUID()),
      inputTruncated: view.input_truncated,
    })
  }

  async function analyze() {
    if (state.draft === null || submitting) return
    setSubmitting(true)
    setSubmitProblem(null)
    const result = await submitAnalysis(buildAnalysisForm(toPosting(state.draft), state.candidate))
    setSubmitting(false)
    if (result.ok) dispatch({ type: 'analysisStarted', analysisId: result.data.analysis_id })
    else if (result.status === 401) sessionExpired()
    else setSubmitProblem(requestProblem(result, limits))
  }

  const index = STEPS.findIndex((step) => step.id === state.step)

  return (
    <section aria-labelledby="match-step-title" className="space-y-8">
      <ol aria-label="Steps" className="flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs">
        {STEPS.map((step, position) => (
          <li
            key={step.id}
            aria-current={step.id === state.step ? 'step' : undefined}
            className={
              step.id === state.step ? 'text-accent' : position < index ? 'text-fg' : 'text-muted'
            }
          >
            {position + 1}. {step.label}
          </li>
        ))}
      </ol>
      <h2 id="match-step-title" ref={headingRef} tabIndex={-1} className="text-xl font-medium">
        Step {index + 1} of {STEPS.length}: {STEPS[index].label}
      </h2>

      {state.step === 'job' && state.draft === null ? (
        <JobSourceForm
          input={state.jobInput}
          onInputChange={(input) => dispatch({ type: 'jobInputChanged', input })}
          onExtracted={handleExtracted}
        />
      ) : null}

      {state.step === 'job' && state.draft !== null ? (
        <JobPreview
          draft={state.draft}
          inputTruncated={state.inputTruncated}
          onChange={(draft) => dispatch({ type: 'draftChanged', draft })}
          onConfirm={() => go({ type: 'jobConfirmed' })}
          onDiscard={() => dispatch({ type: 'draftDiscarded' })}
        />
      ) : null}

      {state.step === 'candidate' ? (
        <CandidateStep
          candidate={state.candidate}
          limits={limits}
          onChange={(candidate) => dispatch({ type: 'candidateChanged', candidate })}
          onBack={() => go({ type: 'backToJob' })}
          onAnalyze={() => void analyze()}
          submitting={submitting}
          problem={submitProblem}
          onOpenRunning={(analysisId) => go({ type: 'analysisStarted', analysisId })}
          onEditJob={() => go({ type: 'backToJob' })}
        />
      ) : null}

      {state.step === 'analysis' && state.analysisId !== null ? (
        <AnalysisProgress
          key={state.analysisId}
          analysisId={state.analysisId}
          candidate={state.candidate}
          limits={limits}
          onCandidateChange={(candidate) => dispatch({ type: 'candidateChanged', candidate })}
          onReport={(report) => dispatch({ type: 'analysisFinished', report })}
          onMoved={(analysisId) => go({ type: 'analysisStarted', analysisId })}
          onResubmit={() => void analyze()}
          resubmitting={submitting}
          resubmitProblem={submitProblem}
          onEditCandidate={(pasteCv) => {
            go({ type: 'analysisAbandoned' })
            if (pasteCv) dispatch({ type: 'candidateChanged', candidate: { cvMode: 'text' } })
          }}
          onEditJob={() => go({ type: 'editJob' })}
          onStartOver={() => go({ type: 'startOver' })}
        />
      ) : null}

      {state.step === 'report' && state.report !== null ? (
        <MatchReportView
          report={state.report}
          onEditJob={() => go({ type: 'editJob' })}
          onStartOver={() => go({ type: 'startOver' })}
        />
      ) : null}
    </section>
  )
}
