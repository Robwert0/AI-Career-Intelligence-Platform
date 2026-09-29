import type { AssessedRequirement, Evidence } from '@/lib/match'
import {
  citation,
  evidenceKindLabel,
  IMPORTANCE_LABEL,
  NOT_ASSESSED_NOTE,
  statusLabel,
} from '@/lib/matchReport'
import { StatusIcon } from './StatusIcon'
import { SECTION_TITLE } from './styles'

function marker(requirement: AssessedRequirement): string {
  if (requirement.hard_gap) return 'border-l-4 border-l-danger'
  if (requirement.status === 'not_assessed') return 'border-l-4 border-dashed border-l-line-strong'
  return 'border-l-4 border-l-transparent'
}

export function RequirementBreakdown({ requirements }: { requirements: AssessedRequirement[] }) {
  if (requirements.length === 0) return null
  return (
    <section aria-labelledby="requirements-title" className="space-y-4">
      <h2 id="requirements-title" className={SECTION_TITLE}>
        Requirement breakdown
      </h2>

      <table className="hidden w-full border-collapse text-left text-sm md:table">
        <caption className="sr-only">
          Each requirement from the job, how well your evidence shows it, and the evidence cited
        </caption>
        <thead>
          <tr className="border-b border-line font-mono text-xs text-muted">
            <th scope="col" className="py-2 pr-4 pl-4 font-normal">
              Requirement
            </th>
            <th scope="col" className="py-2 pr-4 font-normal">
              Status
            </th>
            <th scope="col" className="py-2 font-normal">
              Evidence and reasoning
            </th>
          </tr>
        </thead>
        <tbody>
          {requirements.map((requirement) => (
            <tr
              key={requirement.id}
              className={`border-b border-line align-top ${requirement.status === 'not_assessed' ? 'text-muted' : ''}`}
            >
              <th scope="row" className={`w-1/3 py-3 pr-4 pl-3 font-normal ${marker(requirement)}`}>
                <span className="block">{requirement.text}</span>
                <span className="font-mono text-xs text-muted">
                  {IMPORTANCE_LABEL[requirement.importance]}
                </span>
              </th>
              <td className="py-3 pr-4 whitespace-nowrap">
                <StatusTag requirement={requirement} />
              </td>
              <td className="py-3">
                <RequirementDetail requirement={requirement} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="space-y-3 md:hidden">
        {requirements.map((requirement) => (
          <li
            key={requirement.id}
            className={`space-y-2 rounded-md border border-line p-3 ${marker(requirement)} ${requirement.status === 'not_assessed' ? 'text-muted' : ''}`}
          >
            <p>{requirement.text}</p>
            <p className="font-mono text-xs text-muted">
              {IMPORTANCE_LABEL[requirement.importance]}
            </p>
            <StatusTag requirement={requirement} />
            <RequirementDetail requirement={requirement} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function StatusTag({ requirement }: { requirement: AssessedRequirement }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-xs ${requirement.hard_gap ? 'font-semibold text-danger' : ''}`}
    >
      <StatusIcon status={requirement.status} />
      {statusLabel(requirement)}
    </span>
  )
}

function RequirementDetail({ requirement }: { requirement: AssessedRequirement }) {
  if (requirement.status === 'not_assessed') return <p className="text-sm">{NOT_ASSESSED_NOTE}</p>
  return (
    <div className="space-y-2">
      <p className="text-sm leading-relaxed">{requirement.rationale}</p>
      {requirement.hard_gap ? (
        <p className="text-xs text-danger">
          Hard gap: your evidence contradicts this required item. It does not cap the estimate, but
          an employer may treat it as a blocker.
        </p>
      ) : null}
      {requirement.evidence.length > 0 ? (
        <ul className="space-y-2">
          {requirement.evidence.map((item, index) => (
            <EvidenceLine key={`${item.id}-${index}`} evidence={item} />
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted">No evidence cited.</p>
      )}
    </div>
  )
}

function EvidenceLine({ evidence }: { evidence: Evidence }) {
  const { label, href } = citation(evidence)
  return (
    <li className="space-y-0.5">
      <p className="flex flex-wrap items-baseline gap-x-2 font-mono text-xs text-accent">
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-4"
          >
            {label}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        ) : (
          label
        )}
        <span className="text-subtle">{evidenceKindLabel(evidence.kind)}</span>
      </p>
      <p className="line-clamp-3 text-xs break-words text-muted">{evidence.text}</p>
    </li>
  )
}
