import type { BreakdownRow, Coverage, MatchReport, Refusal } from '@/lib/match'
import {
  CATEGORY_LABEL,
  COVERAGE_LABEL,
  evidenceShare,
  formatPercent,
  formatPoints,
  formatWeight,
  NOT_A_HIRING_PROBABILITY,
  sourceSummary,
  weightsRedistributed,
} from '@/lib/matchReport'
import { PANEL, SECTION_TITLE } from './styles'

export function ReportOverview({ report }: { report: MatchReport }) {
  return (
    <section aria-labelledby="overall-title" className={PANEL}>
      <h2 id="overall-title" className={SECTION_TITLE}>
        Overall match
      </h2>
      {report.score === null ? (
        <RefusalBlock refusal={report.refusal} />
      ) : (
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
          <div className="shrink-0">
            <p id="score-label" className="font-mono text-xs text-muted">
              Alignment estimate
            </p>
            <p aria-describedby="score-label" className="text-6xl font-medium tabular-nums">
              {report.score}
              <span className="text-2xl text-muted"> / 100</span>
            </p>
          </div>
          <Summary summary={report.summary} />
        </div>
      )}
      <CoverageBlock coverage={report.coverage} />
      <p className="text-sm text-muted">{NOT_A_HIRING_PROBABILITY}</p>
      {report.score === null ? null : (
        <BreakdownTable rows={report.breakdown} total={report.score} />
      )}
    </section>
  )
}

function Summary({ summary }: { summary: MatchReport['summary'] }) {
  return (
    <div className="grid flex-1 gap-4 sm:grid-cols-2">
      <SummaryList title="Strongest matches" items={summary.strongest} />
      <SummaryList title="Biggest gaps" items={summary.gaps} />
    </div>
  )
}

function SummaryList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div className="space-y-2">
      <h3 className="font-mono text-xs text-muted">{title}</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function RefusalBlock({ refusal }: { refusal: Refusal }) {
  return (
    <div className="space-y-4">
      <p className="text-2xl font-medium">No alignment estimate</p>
      <p className="text-sm text-muted">
        There wasn&apos;t enough relevant evidence to score this match fairly, so we didn&apos;t
        guess.
      </p>
      {refusal.reasons.length > 0 ? <SummaryList title="Why" items={refusal.reasons} /> : null}
      {refusal.needed.length > 0 ? (
        <SummaryList title="What to add" items={refusal.needed} />
      ) : null}
    </div>
  )
}

function CoverageBlock({ coverage }: { coverage: Coverage }) {
  return (
    <div className="space-y-3">
      <p className="inline-block rounded-sm border border-line-strong px-2 py-1 font-mono text-xs">
        Evidence coverage: {COVERAGE_LABEL[coverage.level]}
      </p>
      <ul className="space-y-1 text-sm text-muted">
        {sourceSummary(coverage).map((line) => (
          <li key={line}>{line}</li>
        ))}
        <li>{evidenceShare(coverage)}</li>
      </ul>
      {coverage.limitations.length > 0 ? (
        <div className="space-y-1">
          <h3 className="font-mono text-xs text-muted">Limitations</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
            {coverage.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function BreakdownTable({ rows, total }: { rows: BreakdownRow[]; total: number }) {
  return (
    <details>
      <summary className="cursor-pointer text-sm font-medium">
        How the estimate is calculated
      </summary>
      <div className="mt-3 space-y-2">
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
        {weightsRedistributed(rows) ? (
          <p className="text-xs text-muted">
            A category had no assessed requirements, so its weight was shared across the others.
          </p>
        ) : null}
        <p className="text-xs text-muted">
          Code computes the estimate from the requirement statuses below. The model never picks the
          number. Demonstrated earns full credit and partially demonstrated earns half, and
          not-assessed items are left out.
        </p>
      </div>
    </details>
  )
}
