import { useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { chat } from '@/lib/api'
import { historyFrom, questionTurn, replyTurn, type Turn } from '@/lib/turns'

// Context lives only in this component's state: nothing is stored, and the callers key it by
// account so signing out or switching accounts starts an empty conversation.
export function useConversation() {
  const { sessionExpired } = useAuth()
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState(false)

  async function ask(message: string) {
    if (pending) return
    // Built before the new question is added, so the question is sent exactly once.
    const history = historyFrom(turns)
    setTurns((current) => [...current, questionTurn(message)])
    setPending(true)

    const result = await chat(message, history)

    setPending(false)
    setTurns((current) => [...current, replyTurn(result)])
    if (!result.ok && result.status === 401) sessionExpired()
  }

  return { turns, pending, ask }
}
