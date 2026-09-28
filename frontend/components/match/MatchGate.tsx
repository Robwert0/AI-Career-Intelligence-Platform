'use client'

import Link from 'next/link'
import { useAuth } from '@/components/AuthProvider'
import { MatchAnalyzer } from './MatchAnalyzer'

export function MatchGate() {
  const { status, exitReason } = useAuth()
  if (status === 'loading') return <p className="font-mono text-xs text-muted">checking session…</p>
  if (status === 'anonymous') return <SignInPrompt expired={exitReason === 'expired'} />
  return <MatchAnalyzer />
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
