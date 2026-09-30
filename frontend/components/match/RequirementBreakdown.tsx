import type { AssessedRequirement, Evidence } from '@/lib/match'
import {
  citation,
  evidenceKindLabel,
  filterCounts,
  IMPORTANCE_LABEL,
  matchesFilter,
  NOT_ASSESSED_NOTE,
  REQUIREMENT_FILTERS,
  requirementAnchor,
  statusLabel,
  type RequirementFilter,
} from '@/lib/matchReport'
import { Disclosure } from './Disclosure'
import { StatusIcon } from './StatusIcon'
import { REPORT_HEADING } from './styles'

type Props = {
  requirements: AssessedRequirement[]
  filter: RequirementFilter
  onFilterChange: (filter: RequirementFilter) => void
}

export function RequirementBreakdown({ requirements, filter, onFilterChange }: Props) {
  if (requirements.length === 0) return null
  const counts = filterCounts(requirements)
  const shown = requirements.filter((requirement) => matchesFilter(requirement, filter))
  const active = REQUIREMENT_FILTERS.find((option) => option.id === filter)!

  return (
    <section aria-labelledby="requirements-title" className="space-y-5">
      <div className="space-y-2">
        <h2 id="requirements-title" className={REPORT_HEADING}>
          Requirements
        </h2>
        <p className="max-w-2xl text-muted">
          Each requirement from the posting, how well your evidence shows it, and the evidence
          cited.
        </p>
      </div>

      <div role="group" aria-label="Filter requirements" className="flex flex-wrap gap-2">
        {REQUIREMENT_FILTERS.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={filter === option.id}
            onClick={() => onFilterChange(option.id)}
            className={`rounded-full border px-3.5 py-1.5 text-sm transition-colors ${
              filter === option.id
                ? 'border-accent bg-accent text-on-accent'
                : 'border-line-strong hover:border-accent hover:text-accent'
            }`}
          >
            {option.label} <span className="tabular-nums">({counts[option.id]})</span>
          </button>
        ))}
      </div>
      <p role="status" className="sr-only">
        {filter === 'all'
          ? `Showing all ${counts.all} requirements.`
          : `Showing ${shown.length} of ${counts.all} requirements: ${active.label.toLowerCase()}.`}
      </p>

      {shown.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line-strong px-4 py-6 text-center text-muted">
          No requirements in this group.
        </p>
      ) : (
        <ul className="space-y-3">
          {shown.map((requirement) => (
            <RequirementCard key={requirement.id} requirement={requirement} />
          ))}
        </ul>
      )}
    </section>
  )
}

function cardStyle(requirement: AssessedRequirement): string {
  if (requirement.hard_gap) return 'border-danger/60 border-l-4 border-l-danger'
  if (requirement.status === 'not_assessed') return 'border-dashed border-line-strong'
  return 'border-line'
}

function RequirementCard({ requirement }: { requirement: AssessedRequirement }) {
  const notAssessed = requirement.status === 'not_assessed'
  return (
    <li
      id={requirementAnchor(requirement.id)}
      tabIndex={-1}
      className={`scroll-mt-24 rounded-lg border p-4 focus:outline-2 focus:outline-offset-2 focus:outline-accent sm:p-5 ${cardStyle(requirement)}`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <StatusTag requirement={requirement} />
        <span className="rounded-sm border border-line px-1.5 py-0.5 font-mono text-xs text-muted">
          {IMPORTANCE_LABEL[requirement.importance]}
        </span>
      </div>
      <h3 className={`mt-2 font-semibold break-words ${notAssessed ? 'text-muted' : ''}`}>
        {requirement.text}
      </h3>
      {notAssessed ? (
        <p className="mt-1.5 text-sm leading-relaxed text-muted">{NOT_ASSESSED_NOTE}</p>
      ) : (
        <div className="mt-1.5 space-y-2">
          <p className="leading-relaxed text-muted">{requirement.rationale}</p>
          {requirement.hard_gap ? (
            <p className="text-sm text-danger">
              Hard gap: your evidence contradicts this required item. It does not cap the estimate,
              but an employer may treat it as a blocker.
            </p>
          ) : null}
          {requirement.evidence.length > 0 ? (
            <Disclosure
              summary={
                <>
                  Evidence ({requirement.evidence.length})
                  <span className="sr-only">: {requirement.text}</span>
                </>
              }
            >
              <ul className="space-y-3 border-l-2 border-line pl-4">
                {requirement.evidence.map((item, index) => (
                  <EvidenceItem key={`${item.id}-${index}`} evidence={item} />
                ))}
              </ul>
            </Disclosure>
          ) : (
            <p className="text-sm text-subtle">No evidence cited.</p>
          )}
        </div>
      )}
    </li>
  )
}

function StatusTag({ requirement }: { requirement: AssessedRequirement }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-sm font-medium ${requirement.hard_gap ? 'text-danger' : ''}`}
    >
      <StatusIcon status={requirement.status} />
      {statusLabel(requirement)}
    </span>
  )
}

function EvidenceItem({ evidence }: { evidence: Evidence }) {
  const { label, href } = citation(evidence)
  return (
    <li className="space-y-1">
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-mono text-xs">
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent underline underline-offset-4"
          >
            {label}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        ) : (
          <span className="text-accent">{label}</span>
        )}
        <span className="text-subtle">{evidenceKindLabel(evidence.kind)}</span>
      </p>
      <blockquote className="text-sm leading-relaxed break-words whitespace-pre-line">
        {evidence.text}
      </blockquote>
    </li>
  )
}
