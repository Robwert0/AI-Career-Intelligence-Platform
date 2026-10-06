'use client'

import Link from 'next/link'
import { useAuth } from '@/components/AuthProvider'
import { MATCH_SAMPLE_PATH } from '@/lib/nav'
import { MatchAnalyzer } from './MatchAnalyzer'
import { SECONDARY_BUTTON } from './styles'
import { ToolIntro } from './ToolIntro'

export function MatchGate() {
  const { status, exitReason, accountId } = useAuth()
  // Keyed by account: a different account never inherits this one's flow, polls or responses.
  if (status === 'authenticated') return <MatchAnalyzer key={accountId ?? 'unknown'} />
  return (
    <div className="max-w-3xl space-y-8">
      <ToolIntro />
      {status === 'loading' ? (
        <p className="font-mono text-xs text-muted">checking session…</p>
      ) : (
        <SignInPrompt expired={exitReason === 'expired'} />
      )}
      <SamplePrompt />
    </div>
  )
}

function SamplePrompt() {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
      <p className="text-sm text-muted">
        Not ready to sign up? See a full report for a fictional candidate and job first. No account
        needed.
      </p>
      <Link href={MATCH_SAMPLE_PATH} className={`${SECONDARY_BUTTON} shrink-0 text-center`}>
        View sample analysis
      </Link>
    </div>
  )
}

function SignInPrompt({ expired }: { expired: boolean }) {
  return (
    <div className="space-y-4 rounded-lg border border-line p-5 sm:p-6">
      {expired ? (
        <p role="alert" className="text-sm">
          Your session ended, so the analysis on this page was closed. Sign in to start again.
        </p>
      ) : null}
      <p className="text-sm text-muted">
        Sign in to analyse a job. Accounts let us rate-limit fairly per person. Nothing you upload
        is kept for more than an hour.
      </p>
      <div className="flex flex-wrap items-center gap-4 font-mono text-sm">
        <Link href="/login?next=%2Fmatch" className="border border-fg px-3 py-2">
          sign in
        </Link>
        <Link href="/register?next=%2Fmatch" className="text-muted underline underline-offset-4">
          create an account
        </Link>
      </div>
    </div>
  )
}
