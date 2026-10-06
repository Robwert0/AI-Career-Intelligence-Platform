'use client'

import { useEffect, useRef, useState } from 'react'
import type { JobPosting, MatchReport } from '@/lib/match'
import { matchesFilter, requirementAnchor, type RequirementFilter } from '@/lib/matchReport'
import { NextSteps, SuggestedWording } from './ReportAdvice'
import { ReportOverview } from './ReportOverview'
import { RequirementBreakdown } from './RequirementBreakdown'

export type ActionPlacement = 'header' | 'footer'

type Props = {
  report: MatchReport
  job: Pick<JobPosting, 'title' | 'company'> | null
  headingRef: React.Ref<HTMLHeadingElement>
  actions: (placement: ActionPlacement) => React.ReactNode
  sample?: boolean
  notice?: React.ReactNode
}

export type RevealRequirement = (requirementId: string) => void

export function MatchReportView({
  report,
  job,
  headingRef,
  actions,
  sample = false,
  notice,
}: Props) {
  const [filter, setFilter] = useState<RequirementFilter>('all')
  const [target, setTarget] = useState<{ id: string } | null>(null)
  const pendingScroll = useRef(false)

  const reveal: RevealRequirement = (requirementId) => {
    const requirement = report.requirements.find((r) => r.id === requirementId)
    if (!requirement) return
    if (!matchesFilter(requirement, filter)) setFilter('all')
    pendingScroll.current = true
    setTarget({ id: requirementId })
  }

  // After the filter change has rendered, so a requirement that was filtered out exists again.
  useEffect(() => {
    if (!target || !pendingScroll.current) return
    pendingScroll.current = false
    const element = document.getElementById(requirementAnchor(target.id))
    if (!element) return
    element.scrollIntoView({ block: 'start' })
    element.focus({ preventScroll: true })
  }, [target, filter])

  const hasAdvice =
    report.recommendations.immediate.length > 0 || report.recommendations.longer_term.length > 0
  const sections = [
    { id: 'overview-title', label: 'Overview' },
    ...(hasAdvice ? [{ id: 'next-steps-title', label: 'Next steps' }] : []),
    ...(report.requirements.length > 0
      ? [{ id: 'requirements-title', label: 'Requirements' }]
      : []),
    ...(report.rewrites.length > 0 ? [{ id: 'wording-title', label: 'Suggested CV wording' }] : []),
  ]

  return (
    <div className="space-y-10 sm:space-y-12">
      <header className="space-y-5 border-b border-line pb-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <p className="font-mono text-xs text-accent">
              Job Match Analyzer · {sample ? 'sample report' : 'report'}
            </p>
            <h1
              id="match-step-title"
              ref={headingRef}
              tabIndex={-1}
              className="text-3xl font-semibold tracking-tight text-balance focus:outline-none sm:text-4xl"
            >
              {job?.title || 'Match report'}
            </h1>
            {job?.company ? <p className="text-lg text-muted">{job.company}</p> : null}
          </div>
          <div className="flex flex-wrap gap-3">{actions('header')}</div>
        </div>
        {notice}
        {sections.length > 1 ? (
          <nav aria-label="Report sections">
            <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
              {sections.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    className="text-muted underline decoration-line-strong underline-offset-4 hover:text-fg"
                  >
                    {section.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}
      </header>

      <ReportOverview report={report} onReveal={reveal} />
      {hasAdvice ? <NextSteps report={report} onReveal={reveal} /> : null}
      <RequirementBreakdown
        requirements={report.requirements}
        filter={filter}
        onFilterChange={setFilter}
      />
      <SuggestedWording report={report} />

      <footer className="flex flex-col gap-4 border-t border-line pt-6 sm:flex-row sm:items-center sm:justify-between">
        <p className="font-mono text-xs text-muted">
          {sample
            ? 'Sample data: no model was run to produce this page.'
            : `Assessed by ${report.model}.`}
        </p>
        <div className="flex flex-wrap gap-3">{actions('footer')}</div>
      </footer>
    </div>
  )
}
