'use client'

import Link from 'next/link'
import { useRef } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { SAMPLE_CANDIDATE, SAMPLE_JOB, SAMPLE_REPORT, sampleCtas } from '@/lib/sampleMatch'
import { MatchReportView, type ActionPlacement } from './MatchReportView'
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from './styles'

export function SampleReport() {
  const { status } = useAuth()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const ctas = sampleCtas(status === 'authenticated')

  function actions(placement: ActionPlacement) {
    return ctas.map((cta) => (
      <Link
        key={cta.href}
        href={cta.href}
        className={cta.primary && placement === 'header' ? PRIMARY_BUTTON : SECONDARY_BUTTON}
      >
        {cta.label}
      </Link>
    ))
  }

  return (
    <MatchReportView
      report={SAMPLE_REPORT}
      job={SAMPLE_JOB}
      headingRef={headingRef}
      actions={actions}
      sample
      notice={
        <div role="note" className="space-y-1 rounded-lg border border-accent/60 px-4 py-3 text-sm">
          <p className="font-semibold">Sample analysis: fictional data</p>
          <p className="leading-relaxed text-muted">
            {SAMPLE_CANDIDATE}, {SAMPLE_JOB.company}, and every employer and repository below are
            invented. The requirement statuses and advice were written by hand to stand in for the
            model. The estimate, breakdown and coverage come from the same scoring rules a real
            analysis uses. Viewing this page runs no AI and needs no account.{' '}
            <Link href="/match" className="text-accent underline underline-offset-4">
              Back to the Job Match Analyzer
            </Link>
          </p>
        </div>
      }
    />
  )
}
