'use client'

import { RequireAuth } from '@/components/RequireAuth'
import { SessionBar } from '@/components/SessionBar'

export default function ChatPage() {
  return (
    <RequireAuth>
      <SessionBar />
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-4 px-4 py-16">
        <p className="font-mono text-xs text-accent">&gt; signed in</p>
        <p className="text-muted">
          The chat interface arrives in the next slice. The API it will call is already live.
        </p>
      </main>
    </RequireAuth>
  )
}
