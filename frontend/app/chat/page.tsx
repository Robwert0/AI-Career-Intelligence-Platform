'use client'

import { useAuth } from '@/components/AuthProvider'
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
        <Transcript turns={turns} pending={pending} onAsk={ask} />
      </div>
      <div>
        <Composer onAsk={ask} pending={pending} />
        <p className="pt-2 font-mono text-xs text-muted">
          answers come only from the CV; follow-ups use this conversation, which is not saved
        </p>
      </div>
    </main>
  )
}

function AccountConversation() {
  const { accountId } = useAuth()
  return <Conversation key={accountId ?? 'unknown'} />
}

export default function ChatPage() {
  return (
    <RequireAuth>
      <SessionBar />
      <AccountConversation />
    </RequireAuth>
  )
}
