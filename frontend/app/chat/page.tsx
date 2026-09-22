'use client'

import { useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { Composer } from '@/components/Composer'
import { RequireAuth } from '@/components/RequireAuth'
import { SessionBar } from '@/components/SessionBar'
import { Transcript } from '@/components/Transcript'
import { chat } from '@/lib/api'
import { questionTurn, replyTurn, type Turn } from '@/lib/turns'

function Conversation() {
  const { sessionExpired } = useAuth()
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState(false)

  async function ask(message: string) {
    setTurns((current) => [...current, questionTurn(message)])
    setPending(true)

    const result = await chat(message)

    setPending(false)
    setTurns((current) => [...current, replyTurn(result)])
    if (!result.ok && result.status === 401) sessionExpired()
  }

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
