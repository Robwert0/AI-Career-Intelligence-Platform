'use client'

import { useEffect, useEffectEvent, useState } from 'react'
import { describedBy } from '@/lib/aria'
import type { MatchField, Problem } from '@/lib/matchErrors'
import {
  candidateErrors,
  DISCLOSURE,
  hasCandidateErrors,
  type CandidateErrors,
  type CandidateInput,
  type CvMode,
} from '@/lib/matchInputs'
import { CvInput } from './CvInput'
import { FieldError } from './Field'
import { ALERT, FIELD, PRIMARY_BUTTON, SECONDARY_BUTTON } from './styles'

type Props = {
  candidate: CandidateInput
  onChange: (patch: Partial<CandidateInput>) => void
  onBack: () => void
  onAnalyze: () => void
  submitting: boolean
  problem: Problem | null
  onOpenRunning: (analysisId: string) => void
  onEditJob: () => void
}

type FieldKey = keyof CandidateErrors

function fieldIdFor(field: MatchField, cvMode: CvMode): string {
  if (field === 'github') return 'github-url'
  if (field === 'consent') return 'consent'
  if (field === 'job') return 'match-step-title'
  return cvMode === 'file' ? 'candidate-cv-file' : 'candidate-cv-text'
}

export function CandidateStep({
  candidate,
  onChange,
  onBack,
  onAnalyze,
  submitting,
  problem,
  onOpenRunning,
  onEditJob,
}: Props) {
  const [attempted, setAttempted] = useState(false)
  const errors = candidateErrors(candidate)
  const general =
    problem !== null &&
    (problem.field === undefined || problem.field === 'job' || problem.field === 'sources')
      ? problem
      : null
  const runningId = general?.runningAnalysisId
  const focusField = useEffectEvent((field: MatchField) => {
    document.getElementById(fieldIdFor(field, candidate.cvMode))?.focus()
  })

  useEffect(() => {
    if (problem?.field === undefined || problem.field === 'job') return
    focusField(problem.field)
  }, [problem])

  function fieldError(field: FieldKey): string | undefined {
    if (attempted && errors[field]) return errors[field]
    return problem?.field === field ? problem.message : undefined
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setAttempted(true)
    if (submitting) return
    if (hasCandidateErrors(errors)) {
      const first: MatchField =
        errors.sources || errors.cv ? 'cv' : errors.github ? 'github' : 'consent'
      document.getElementById(fieldIdFor(first, candidate.cvMode))?.focus()
      return
    }
    onAnalyze()
  }

  const githubError = fieldError('github')
  const consentError = fieldError('consent')

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-8">
      <p className="text-sm text-muted">
        Add a CV, a GitHub profile, or both. Both together give the fullest picture.
      </p>

      <CvInput
        idPrefix="candidate"
        candidate={candidate}
        error={fieldError('cv')}
        onChange={onChange}
      />

      <div className="space-y-2">
        <label htmlFor="github-url" className="font-medium">
          GitHub profile
        </label>
        <input
          id="github-url"
          type="url"
          inputMode="url"
          value={candidate.githubUrl}
          onChange={(event) => onChange({ githubUrl: event.target.value })}
          placeholder="https://github.com/your-username"
          aria-invalid={Boolean(githubError)}
          aria-describedby={describedBy('github-hint', githubError && 'github-error')}
          className={FIELD}
        />
        <p id="github-hint" className="text-xs text-muted">
          Public repositories only. We read repository metadata and READMEs, not code.
        </p>
        <FieldError id="github-error" message={githubError} />
      </div>

      {errors.sources ? (
        <p
          id="sources-status"
          role="status"
          className={`font-mono text-xs ${attempted ? 'text-danger' : 'text-muted'}`}
        >
          {errors.sources}
        </p>
      ) : null}

      <div className="space-y-4 rounded-lg border border-line p-4">
        <p id="match-disclosure" className="text-sm leading-relaxed">
          {DISCLOSURE}
        </p>
        <label className="flex items-start gap-3 text-sm">
          <input
            id="consent"
            type="checkbox"
            checked={candidate.consent}
            onChange={(event) => onChange({ consent: event.target.checked })}
            aria-invalid={Boolean(consentError)}
            aria-describedby={describedBy('match-disclosure', consentError && 'consent-error')}
            className="mt-0.5 size-4 shrink-0 accent-accent"
          />
          <span>I understand and agree to this processing.</span>
        </label>
        <FieldError id="consent-error" message={consentError} />
      </div>

      {general ? (
        <div role="alert" className={ALERT}>
          <p>{general.message}</p>
          <div className="flex flex-wrap gap-2">
            {runningId ? (
              <button
                type="button"
                onClick={() => onOpenRunning(runningId)}
                className={SECONDARY_BUTTON}
              >
                Open the running analysis
              </button>
            ) : null}
            {general.field === 'job' ? (
              <button type="button" onClick={onEditJob} className={SECONDARY_BUTTON}>
                Edit the job
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          aria-describedby={describedBy(errors.sources && 'sources-status')}
          className={PRIMARY_BUTTON}
        >
          {submitting ? 'Uploading…' : 'Analyze'}
        </button>
        <button type="button" onClick={onBack} className={SECONDARY_BUTTON}>
          Back to the job
        </button>
      </div>
    </form>
  )
}
