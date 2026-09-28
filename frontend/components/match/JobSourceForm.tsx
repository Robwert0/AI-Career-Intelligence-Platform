'use client'

import { useState } from 'react'
import { describedBy } from '@/lib/aria'
import type { JobView } from '@/lib/match'
import { jobRecovery } from '@/lib/matchErrors'
import {
  jobInputError,
  jobIntake,
  MAX_JOB_TEXT_CHARS,
  type JobInput,
  type JobTab,
} from '@/lib/matchInputs'
import { jobAnnouncement, jobSourceLabel, jobStages } from '@/lib/matchProgress'
import { charCount } from '@/lib/text'
import { useFocusAfterRender } from '@/lib/useFocusAfterRender'
import { useJobIntake } from '@/lib/useJobIntake'
import { FieldError } from './Field'
import { Announcer, StageList } from './StageList'
import { ALERT, FIELD, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from './styles'

const TABS: { id: JobTab; label: string }[] = [
  { id: 'url', label: 'Job URL' },
  { id: 'text', label: 'Paste description' },
]
const FIELD_ID: Record<JobTab, string> = { url: 'job-url', text: 'job-text' }
const ERROR_ID = 'job-input-error'

type Props = {
  input: JobInput
  onInputChange: (patch: Partial<JobInput>) => void
  onExtracted: (view: JobView) => void
}

export function JobSourceForm({ input, onInputChange, onExtracted }: Props) {
  const intake = useJobIntake(onExtracted)
  const [attempted, setAttempted] = useState(false)
  const focusAfterRender = useFocusAfterRender()
  const error = attempted ? jobInputError(input) : null
  const stages = jobStages(input.tab, intake.view)
  const recovery = intake.failure ? jobRecovery(intake.failure, input.tab) : null
  const message = intake.failure?.message ?? intake.problem?.message ?? null
  const offerRetry = intake.problem !== null || recovery?.offerRetry === true
  const offerPaste =
    input.tab === 'url' && (intake.problem !== null || recovery?.offerPaste === true)

  function selectTab(tab: JobTab, focus: 'tab' | 'field') {
    onInputChange({ tab })
    focusAfterRender(focus === 'tab' ? `job-tab-${tab}` : FIELD_ID[tab])
  }

  function handleTabKey(event: React.KeyboardEvent) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    if (event.key === 'Home') selectTab('url', 'tab')
    else if (event.key === 'End') selectTab('text', 'tab')
    else selectTab(input.tab === 'url' ? 'text' : 'url', 'tab')
  }

  function extract() {
    void intake.extract(jobIntake(input))
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setAttempted(true)
    if (intake.busy) return
    if (jobInputError(input) !== null) {
      document.getElementById(FIELD_ID[input.tab])?.focus()
      return
    }
    extract()
  }

  function invalid(tab: JobTab) {
    return input.tab === tab && error !== null
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      <fieldset disabled={intake.busy} className="space-y-5">
        <legend className="sr-only">The job posting</legend>
        <div
          role="tablist"
          aria-label="How to add the job"
          className="flex gap-1 border-b border-line"
        >
          {TABS.map((tab) => {
            const selected = input.tab === tab.id
            return (
              <button
                key={tab.id}
                id={`job-tab-${tab.id}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={`job-panel-${tab.id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => selectTab(tab.id, 'field')}
                onKeyDown={handleTabKey}
                className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${
                  selected ? 'border-accent text-fg' : 'border-transparent text-muted hover:text-fg'
                }`}
              >
                {tab.label}
              </button>
            )
          })}
        </div>

        <div
          id="job-panel-url"
          role="tabpanel"
          aria-labelledby="job-tab-url"
          hidden={input.tab !== 'url'}
          className="space-y-2"
        >
          <label htmlFor="job-url" className={LABEL}>
            Link to the job posting
          </label>
          <input
            id="job-url"
            type="url"
            inputMode="url"
            autoComplete="url"
            value={input.url}
            onChange={(event) => onInputChange({ url: event.target.value })}
            placeholder="https://"
            aria-invalid={invalid('url')}
            aria-describedby={describedBy('job-url-hint', invalid('url') && ERROR_ID)}
            className={FIELD}
          />
          <p id="job-url-hint" className="text-xs text-muted">
            Our server fetches the page and respects sites that block automated access. If a site
            blocks it, paste the description instead.
          </p>
        </div>

        <div
          id="job-panel-text"
          role="tabpanel"
          aria-labelledby="job-tab-text"
          hidden={input.tab !== 'text'}
          className="space-y-2"
        >
          <label htmlFor="job-text" className={LABEL}>
            Job description
          </label>
          <textarea
            id="job-text"
            rows={10}
            value={input.text}
            onChange={(event) => onInputChange({ text: event.target.value })}
            aria-invalid={invalid('text')}
            aria-describedby={describedBy('job-text-count', invalid('text') && ERROR_ID)}
            className={`${FIELD} min-h-48`}
          />
          <p id="job-text-count" className="text-right font-mono text-xs text-muted">
            {charCount(input.text.trim()).toLocaleString('en-US')} /{' '}
            {MAX_JOB_TEXT_CHARS.toLocaleString('en-US')} characters
          </p>
        </div>

        <FieldError id={ERROR_ID} message={error} />

        <button type="submit" className={PRIMARY_BUTTON}>
          {intake.busy ? 'Reading the job…' : 'Extract requirements'}
        </button>
      </fieldset>

      {intake.resumed ? (
        <p className="text-sm text-muted">
          You already have a job intake in progress
          {intake.view ? <>: {jobSourceLabel(intake.view.source_url)}</> : null}.
        </p>
      ) : null}
      {intake.busy ? <StageList items={stages} /> : null}
      <Announcer text={intake.busy ? jobAnnouncement(intake.view, stages) : ''} />

      {message !== null && !intake.busy ? (
        <div role="alert" className={ALERT}>
          <p>{message}</p>
          <div className="flex flex-wrap gap-2">
            {offerRetry ? (
              <button type="button" onClick={extract} className={SECONDARY_BUTTON}>
                Try again
              </button>
            ) : null}
            {offerPaste ? (
              <button
                type="button"
                onClick={() => selectTab('text', 'field')}
                className={SECONDARY_BUTTON}
              >
                Paste the description instead
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </form>
  )
}
