'use client'

import { useEffect, useState } from 'react'
import { describedBy } from '@/lib/aria'
import {
  CV_ACCEPT,
  cvFileError,
  formatBytes,
  type CandidateInput,
  type CvMode,
} from '@/lib/matchInputs'
import type { UploadLimits } from '@/lib/matchConfig'
import { charCount } from '@/lib/text'
import { FieldError } from './Field'
import { FIELD, LABEL, TEXT_BUTTON } from './styles'

const MODES: { id: CvMode; label: string }[] = [
  { id: 'file', label: 'Upload a file' },
  { id: 'text', label: 'Paste CV text' },
]

type Props = {
  idPrefix: string
  candidate: CandidateInput
  limits: UploadLimits
  error?: string
  onChange: (patch: Partial<CandidateInput>) => void
}

export function CvInput({ idPrefix, candidate, limits, error, onChange }: Props) {
  const [pickError, setPickError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileId = `${idPrefix}-cv-file`
  const errorId = `${idPrefix}-cv-error`
  const shownError = pickError ?? error

  // A file dropped just outside the zone would otherwise navigate away and lose every input.
  useEffect(() => {
    const block = (event: DragEvent) => event.preventDefault()
    window.addEventListener('dragover', block)
    window.addEventListener('drop', block)
    return () => {
      window.removeEventListener('dragover', block)
      window.removeEventListener('drop', block)
    }
  }, [])

  function take(files: FileList | null) {
    const file = files?.[0]
    if (file === undefined) return
    const problem = cvFileError(file, limits)
    setPickError(problem)
    onChange({ cvFile: problem === null ? file : null })
  }

  function removeFile() {
    setPickError(null)
    onChange({ cvFile: null })
    document.getElementById(fileId)?.focus()
  }

  return (
    <fieldset className="space-y-3">
      <legend className="font-medium">CV</legend>
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
        {MODES.map((mode) => (
          <label key={mode.id} className="inline-flex items-center gap-2">
            <input
              type="radio"
              name={`${idPrefix}-cv-mode`}
              value={mode.id}
              checked={candidate.cvMode === mode.id}
              onChange={() => {
                setPickError(null)
                onChange({ cvMode: mode.id })
              }}
              className="size-4 accent-accent"
            />
            {mode.label}
          </label>
        ))}
      </div>

      {candidate.cvMode === 'file' ? (
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            take(event.dataTransfer.files)
          }}
          className={`space-y-2 rounded-lg border-2 border-dashed px-4 py-6 text-center outline-offset-2 has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-accent ${
            dragging ? 'border-accent' : shownError ? 'border-danger' : 'border-line-strong'
          }`}
        >
          <input
            id={fileId}
            type="file"
            accept={CV_ACCEPT}
            onChange={(event) => {
              take(event.target.files)
              event.target.value = ''
            }}
            aria-invalid={Boolean(shownError)}
            aria-describedby={describedBy(`${idPrefix}-cv-hint`, shownError && errorId)}
            className="sr-only"
          />
          <label htmlFor={fileId} className="block cursor-pointer text-sm">
            <span className="font-medium text-accent underline underline-offset-4">
              Choose a file
            </span>{' '}
            or drop it here
          </label>
          <p id={`${idPrefix}-cv-hint`} className="font-mono text-xs text-muted">
            PDF or DOCX, max {formatBytes(limits.maxCvBytes)}, 10 pages
          </p>
          {candidate.cvFile ? (
            <p className="flex flex-wrap items-center justify-center gap-3 text-sm">
              <span className="break-all">
                {candidate.cvFile.name} · {formatBytes(candidate.cvFile.size)}
              </span>
              <button type="button" onClick={removeFile} className={TEXT_BUTTON}>
                Remove file
              </button>
            </p>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2">
          <label htmlFor={`${idPrefix}-cv-text`} className={LABEL}>
            CV text
          </label>
          <textarea
            id={`${idPrefix}-cv-text`}
            rows={10}
            value={candidate.cvText}
            onChange={(event) => onChange({ cvText: event.target.value })}
            aria-invalid={Boolean(shownError)}
            aria-describedby={describedBy(`${idPrefix}-cv-count`, shownError && errorId)}
            className={`${FIELD} min-h-48`}
          />
          <p id={`${idPrefix}-cv-count`} className="text-right font-mono text-xs text-muted">
            {charCount(candidate.cvText.trim()).toLocaleString('en-US')} /{' '}
            {limits.maxCvTextChars.toLocaleString('en-US')} characters
          </p>
        </div>
      )}
      <FieldError id={errorId} message={shownError} />
    </fieldset>
  )
}
