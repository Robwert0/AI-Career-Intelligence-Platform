import { useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { chat } from '@/lib/api'
import { questionTurn, replyTurn, type Turn } from '@/lib/turns'

export function useConversation() {
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

  return { turns, pending, ask }
}
