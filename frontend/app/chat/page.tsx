'use client'

import { Composer } from '@/components/Composer'
import { RequireAuth } from '@/components/RequireAuth'
import { SessionBar } from '@/components/SessionBar'
import { Transcript } from '@/components/Transcript'
import { useConversation } from '@/lib/useConversation'

function Conversation() {
  const { turns, pending, ask } = useConversation()

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-4 py-8">
      <div className="flex-1">
        <Transcript turns={turns} pending={pending} />
      </div>
      <div>
        <Composer onAsk={ask} pending={pending} />
        <p className="pt-2 font-mono text-xs text-muted">
          each question is answered independently from the CV
        </p>
      </div>
    </main>
  )
}

export default function ChatPage() {
  return (
    <RequireAuth>
      <SessionBar />
      <Conversation />
    </RequireAuth>
  )
}
