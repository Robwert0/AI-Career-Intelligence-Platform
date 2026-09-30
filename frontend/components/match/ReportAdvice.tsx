'use client'

import { useState } from 'react'
import type { MatchReport, Recommendation, Rewrite } from '@/lib/match'
import { citation, evidenceById, requirementAnchor, requirementTextById } from '@/lib/matchReport'
import { wordDiff, type DiffSegment } from '@/lib/textDiff'
import { Disclosure } from './Disclosure'
import type { RevealRequirement } from './MatchReportView'
import { REPORT_HEADING, SECONDARY_BUTTON } from './styles'

const SHOWN_FIRST = 3

type AdviceProps = { report: MatchReport; onReveal: RevealRequirement }

export function NextSteps({ report, onReveal }: AdviceProps) {
  const { immediate, longer_term: longerTerm } = report.recommendations
  const names = requirementTextById(report)
  const first = immediate.slice(0, SHOWN_FIRST)
  const rest = immediate.slice(SHOWN_FIRST)

  return (
    <section aria-labelledby="next-steps-title" className="space-y-6">
      <h2 id="next-steps-title" className={REPORT_HEADING}>
        Next steps
      </h2>

      <div className="space-y-3">
        <h3 className="font-semibold">For this application</h3>
        {immediate.length === 0 ? (
          <p className="text-sm text-muted">No changes suggested for this application.</p>
        ) : (
          <>
            <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {first.map((item, index) => (
                <li
                  key={`${item.requirement_id}-${index}`}
                  className="flex gap-3 rounded-lg border border-line bg-surface p-4"
                >
                  <span
                    aria-hidden="true"
                    className="flex size-6 shrink-0 items-center justify-center rounded-full border border-accent/60 font-mono text-xs text-accent"
                  >
                    {index + 1}
                  </span>
                  <RecommendationBody item={item} names={names} onReveal={onReveal} />
                </li>
              ))}
            </ol>
            {rest.length > 0 ? (
              <Disclosure summary={`${rest.length} more for this application`}>
                <ol start={SHOWN_FIRST + 1} className="space-y-3">
                  {rest.map((item, index) => (
                    <li
                      key={`${item.requirement_id}-${index}`}
                      className="border-l-2 border-line pl-4"
                    >
                      <RecommendationBody item={item} names={names} onReveal={onReveal} />
                    </li>
                  ))}
                </ol>
              </Disclosure>
            ) : null}
          </>
        )}
      </div>

      {longerTerm.length > 0 ? (
        <div className="space-y-3 border-t border-line pt-5">
          <h3 className="font-semibold">Longer-term development</h3>
          <p className="text-sm text-muted">
            Things to build or learn, rather than changes to make to this application.
          </p>
          <ul className="grid gap-4 md:grid-cols-2">
            {longerTerm.map((item, index) => (
              <li key={`${item.requirement_id}-${index}`} className="border-l-2 border-line pl-4">
                <RecommendationBody item={item} names={names} onReveal={onReveal} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

function RecommendationBody({
  item,
  names,
  onReveal,
}: {
  item: Recommendation
  names: Map<string, string>
  onReveal: RevealRequirement
}) {
  const requirement = names.get(item.requirement_id)
  return (
    <div className="min-w-0 space-y-1">
      <p className="font-medium">{item.title}</p>
      <p className="text-sm leading-relaxed text-muted">{item.detail}</p>
      {requirement ? (
        <p className="text-sm break-words">
          <span className="text-subtle">For: </span>
          <a
            href={`#${requirementAnchor(item.requirement_id)}`}
            onClick={(event) => {
              event.preventDefault()
              onReveal(item.requirement_id)
            }}
            className="text-accent underline underline-offset-4 hover:decoration-2"
          >
            {requirement}
          </a>
        </p>
      ) : null}
    </div>
  )
}

export function SuggestedWording({ report }: { report: MatchReport }) {
  if (report.rewrites.length === 0) return null
  const sources = evidenceById(report)
  return (
    <section aria-labelledby="wording-title" className="space-y-5">
      <div className="space-y-2">
        <h2 id="wording-title" className={REPORT_HEADING}>
          Suggested CV wording
        </h2>
        <p className="max-w-2xl text-muted">
          Each rewrite uses facts already in your evidence. Where a stronger line needs a fact we
          don&apos;t have, we ask for it instead of inventing it. Changed words are highlighted.
        </p>
      </div>
      <ul className="space-y-5">
        {report.rewrites.map((rewrite, index) => {
          const source = sources.get(rewrite.evidence_id)
          return (
            <RewriteCard
              key={`${rewrite.evidence_id}-${index}`}
              rewrite={rewrite}
              label={source ? citation(source).label : 'CV'}
            />
          )
        })}
      </ul>
    </section>
  )
}

type CopyState = 'idle' | 'copied' | 'failed'

function RewriteCard({ rewrite, label }: { rewrite: Rewrite; label: string }) {
  const [copy, setCopy] = useState<CopyState>('idle')
  const diff = wordDiff(rewrite.before, rewrite.after)

  async function copySuggestion() {
    try {
      await navigator.clipboard.writeText(rewrite.after)
      setCopy('copied')
    } catch {
      setCopy('failed')
    }
  }

  return (
    <li className="space-y-4 rounded-lg border border-line p-4 sm:p-5">
      <p className="font-mono text-xs text-accent">{label}</p>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1.5 rounded-md border border-line p-3">
          <p className="text-xs font-medium tracking-wide text-muted uppercase">Original</p>
          <p className="leading-relaxed text-muted">
            <Segments segments={diff.original} kind="removed" />
          </p>
        </div>
        <div className="space-y-1.5 rounded-md border border-accent/60 bg-surface p-3">
          <p className="text-xs font-medium tracking-wide text-accent uppercase">Suggested</p>
          <p className="leading-relaxed">
            <Segments segments={diff.suggested} kind="added" />
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => void copySuggestion()} className={SECONDARY_BUTTON}>
          Copy suggestion
        </button>
        <p role="status" className={`text-sm ${copy === 'failed' ? 'text-danger' : 'text-muted'}`}>
          {copy === 'copied' ? 'Suggestion copied to the clipboard.' : null}
          {copy === 'failed' ? 'Couldn’t copy. Select the suggested text and copy it.' : null}
        </p>
      </div>
      {rewrite.questions.length > 0 ? (
        <div className="space-y-1 border-t border-line pt-3">
          <p className="text-sm font-medium">To make it stronger, answer:</p>
          <ul className="list-disc space-y-1 pl-5 text-sm marker:text-line-strong">
            {rewrite.questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </li>
  )
}

function Segments({ segments, kind }: { segments: DiffSegment[]; kind: 'added' | 'removed' }) {
  return segments.map((segment, index) =>
    !segment.changed ? (
      <span key={index}>{segment.text}</span>
    ) : kind === 'added' ? (
      <ins
        key={index}
        className="rounded-sm bg-accent/20 text-fg underline decoration-accent/70 decoration-2 underline-offset-2"
      >
        {segment.text}
      </ins>
    ) : (
      <del key={index} className="decoration-danger/70">
        {segment.text}
      </del>
    ),
  )
}
