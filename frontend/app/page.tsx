'use client'

import { useAuth } from '@/components/AuthProvider'

const STATUS_LABEL: Record<string, string> = {
  loading: 'checking session',
  authenticated: 'signed in',
  anonymous: 'not signed in',
}

export default function Home() {
  const { status } = useAuth()

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-10 px-4 py-16">
      <header className="flex items-baseline justify-between border-b border-line pb-3">
        <span className="font-mono text-sm tracking-tight">cv.chat</span>
        <span className="font-mono text-xs text-muted">{STATUS_LABEL[status]}</span>
      </header>

      <div className="space-y-4">
        <h1 className="text-3xl leading-tight font-medium text-balance">
          Ask questions about a CV, answered only from its contents.
        </h1>
        <p className="max-w-prose text-muted">
          Retrieval-grounded answers with the source extracts attached. Questions the CV does not
          cover are declined rather than guessed at.
        </p>
      </div>

      <dl className="grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-3">
        {[
          ['retrieval', 'hybrid vector + full text'],
          ['grounding', 'sources shown per answer'],
          ['refusal', 'no model call when off-topic'],
        ].map(([term, detail]) => (
          <div key={term} className="bg-bg p-4">
            <dt className="font-mono text-xs text-accent">{term}</dt>
            <dd className="mt-1 text-sm text-muted">{detail}</dd>
          </div>
        ))}
      </dl>

      <p className="font-mono text-xs text-muted">
        <span className="text-accent">&gt;</span> session: {status}
      </p>
    </main>
  )
}
