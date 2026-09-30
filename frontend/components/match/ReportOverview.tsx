import type { AssessedRequirement, BreakdownRow, Coverage, MatchReport, Refusal } from '@/lib/match'
import {
  CATEGORY_LABEL,
  COVERAGE_LABEL,
  evidenceShare,
  formatPercent,
  formatPoints,
  formatWeight,
  NOT_A_HIRING_PROBABILITY,
  requirementAnchor,
  sourceStatusLines,
  sourceSummary,
  weightsRedistributed,
} from '@/lib/matchReport'
import { Disclosure } from './Disclosure'
import type { RevealRequirement } from './MatchReportView'
import { REPORT_HEADING } from './styles'

type Props = { report: MatchReport; onReveal: RevealRequirement }

export function ReportOverview({ report, onReveal }: Props) {
  const hardGaps = report.requirements.filter((requirement) => requirement.hard_gap)
  const notAssessed = report.requirements.filter((r) => r.status === 'not_assessed').length
  return (
    <section aria-labelledby="overview-title" className="space-y-6">
      <h2 id="overview-title" className={REPORT_HEADING}>
        Overview
      </h2>

      <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <div className="space-y-4 rounded-xl border border-line bg-surface p-5 sm:p-6">
          <div className="space-y-2">
            <p id="score-label" className="text-sm font-medium text-muted">
              Alignment estimate
            </p>
            {report.score === null ? (
              <p className="text-2xl font-semibold">No estimate</p>
            ) : (
              <p aria-describedby="score-label score-disclaimer" className="tabular-nums">
                <span className="text-6xl font-semibold tracking-tight">{report.score}</span>
                <span className="text-2xl text-muted"> / 100</span>
              </p>
            )}
            <p id="score-disclaimer" className="text-sm leading-relaxed text-muted">
              {NOT_A_HIRING_PROBABILITY}
            </p>
          </div>
          {report.score === null ? <RefusalBlock refusal={report.refusal} /> : null}
          <CoverageSummary coverage={report.coverage} notAssessed={notAssessed} />
          {report.score !== null && weightsRedistributed(report.breakdown) ? (
            <p className="text-sm text-muted">
              A category had no assessed requirements, so its weight was shared across the others.
            </p>
          ) : null}
        </div>

        <div className="space-y-6">
          {report.score === null ? null : (
            <div className="grid gap-6 sm:grid-cols-2">
              <SummaryList
                title="Strongest matches"
                items={report.summary.strongest}
                empty="None listed."
              />
              <SummaryList title="Biggest gaps" items={report.summary.gaps} empty="None listed." />
            </div>
          )}
          {hardGaps.length > 0 ? <HardGaps gaps={hardGaps} onReveal={onReveal} /> : null}
          <div className="space-y-2 border-t border-line pt-4">
            <SourceDetails coverage={report.coverage} />
            {report.score === null ? null : (
              <BreakdownTable rows={report.breakdown} total={report.score} />
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

function SummaryList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="space-y-2">
      <h3 className="font-semibold">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <ul className="list-disc space-y-1.5 pl-5 leading-relaxed marker:text-line-strong">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function HardGaps({
  gaps,
  onReveal,
}: {
  gaps: AssessedRequirement[]
  onReveal: RevealRequirement
}) {
  return (
    <div className="space-y-2 rounded-lg border border-danger/60 px-4 py-3">
      <h3 className="flex items-center gap-2 font-semibold text-danger">
        <svg
          aria-hidden="true"
          viewBox="0 0 16 16"
          className="size-4 shrink-0"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        >
          <path d="M8 2 14.5 13.5h-13z" strokeLinejoin="round" />
          <path d="M8 6.5v3M8 11.5v.01" />
        </svg>
        {gaps.length === 1 ? 'Hard gap' : `Hard gaps (${gaps.length})`}
      </h3>
      <p className="text-sm text-muted">
        Your evidence contradicts{' '}
        {gaps.length === 1 ? 'this required item' : 'these required items'}. It does not cap the
        estimate, but an employer may treat it as a blocker.
      </p>
      <ul className="space-y-1">
        {gaps.map((gap) => (
          <li key={gap.id}>
            <a
              href={`#${requirementAnchor(gap.id)}`}
              onClick={(event) => {
                event.preventDefault()
                onReveal(gap.id)
              }}
              className="underline decoration-danger/60 underline-offset-4 hover:decoration-2"
            >
              {gap.text}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RefusalBlock({ refusal }: { refusal: Refusal }) {
  return (
    <div className="space-y-4 border-t border-line pt-4">
      <p className="text-sm leading-relaxed">
        There wasn&apos;t enough relevant evidence to score this match fairly, so we didn&apos;t
        guess.
      </p>
      {refusal.reasons.length > 0 ? (
        <SummaryList title="Why" items={refusal.reasons} empty="" />
      ) : null}
      {refusal.needed.length > 0 ? (
        <SummaryList title="What to add" items={refusal.needed} empty="" />
      ) : null}
    </div>
  )
}

function CoverageSummary({ coverage, notAssessed }: { coverage: Coverage; notAssessed: number }) {
  return (
    <div className="space-y-2 border-t border-line pt-4">
      <p className="text-sm">
        <span className="text-muted">Evidence coverage: </span>
        <span className="font-semibold">{COVERAGE_LABEL[coverage.level]}</span>
      </p>
      <ul className="space-y-1 text-sm">
        {sourceStatusLines(coverage).map((line) => (
          <li key={line.source} className="flex items-baseline gap-2">
            <SourceMark status={line.status} />
            <span>
              <span className="text-muted">{line.source}: </span>
              {line.status}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-sm text-muted">{evidenceShare(coverage)}</p>
      {notAssessed > 0 ? (
        <p className="text-sm text-muted">
          {notAssessed === 1
            ? '1 requirement was not assessed; confirm it yourself.'
            : `${notAssessed} requirements were not assessed; confirm them yourself.`}
        </p>
      ) : null}
    </div>
  )
}

function SourceMark({ status }: { status: string }) {
  const read = status === 'read'
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className={`size-3.5 shrink-0 translate-y-0.5 ${read ? 'text-accent' : 'text-subtle'}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
    >
      {read ? <path d="M3.5 8.5l3 3 6-7" /> : <path d="M4 8h8" />}
    </svg>
  )
}

function SourceDetails({ coverage }: { coverage: Coverage }) {
  return (
    <Disclosure
      summary={`Sources and limitations${coverage.limitations.length > 0 ? ` (${coverage.limitations.length})` : ''}`}
    >
      <div className="space-y-3 text-sm">
        <ul className="space-y-1 text-muted">
          {sourceSummary(coverage).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        {coverage.limitations.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5 text-muted marker:text-line-strong">
            {coverage.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </Disclosure>
  )
}

function BreakdownTable({ rows, total }: { rows: BreakdownRow[]; total: number }) {
  return (
    <Disclosure summary="How the estimate is calculated">
      <div className="space-y-2">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">Score breakdown by category</caption>
          <thead>
            <tr className="border-b border-line font-mono text-xs text-muted">
              <th scope="col" className="py-2 pr-3 font-normal">
                Category
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                Weight
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                Score
              </th>
              <th scope="col" className="py-2 text-right font-normal">
                Points
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.category} className="border-b border-line">
                <th scope="row" className="py-2 pr-3 font-normal">
                  {CATEGORY_LABEL[row.category]}
                </th>
                <td className="py-2 pr-3 text-right tabular-nums">{formatWeight(row)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{formatPercent(row.score)}</td>
                <td className="py-2 text-right tabular-nums">{formatPoints(row.points)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={3} className="py-2 pr-3 text-right font-medium">
                Alignment estimate
              </th>
              <td className="py-2 text-right font-medium tabular-nums">{total}</td>
            </tr>
          </tfoot>
        </table>
        <p className="text-sm text-muted">
          Code computes the estimate from the requirement statuses below. The model never picks the
          number. Demonstrated earns full credit and partially demonstrated earns half, and
          not-assessed items are left out.
        </p>
      </div>
    </Disclosure>
  )
}
