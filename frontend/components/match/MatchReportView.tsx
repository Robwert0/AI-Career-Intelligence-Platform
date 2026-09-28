import type { MatchReport } from '@/lib/match'
import { Improvements, SuggestedWording } from './ReportAdvice'
import { ReportOverview } from './ReportOverview'
import { RequirementBreakdown } from './RequirementBreakdown'
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from './styles'

type Props = { report: MatchReport; onStartOver: () => void; onEditJob: () => void }

export function MatchReportView({ report, onStartOver, onEditJob }: Props) {
  return (
    <div className="space-y-12">
      <ReportOverview report={report} />
      <RequirementBreakdown requirements={report.requirements} />
      <Improvements report={report} />
      <SuggestedWording report={report} />
      <p className="font-mono text-xs text-muted">Assessed by {report.model}.</p>
      <div className="flex flex-wrap gap-3 border-t border-line pt-6">
        <button type="button" onClick={onEditJob} className={PRIMARY_BUTTON}>
          Edit job and re-run
        </button>
        <button type="button" onClick={onStartOver} className={SECONDARY_BUTTON}>
          Start over
        </button>
      </div>
    </div>
  )
}
