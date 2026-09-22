'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { me } from '@/lib/api'

export function SessionBar() {
  const { signOut } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    me().then((result) => {
      if (active && result.ok) setEmail(result.data.email)
    })
    return () => {
      active = false
    }
  }, [])

  async function handleSignOut() {
    await signOut()
    router.replace('/login')
  }

  return (
    <header className="mx-auto flex w-full max-w-2xl items-baseline justify-between border-b border-line px-4 py-3">
      <span className="font-mono text-sm">cv.chat</span>
      <span className="flex items-baseline gap-4 font-mono text-xs text-muted">
        {email}
        <button
          type="button"
          onClick={handleSignOut}
          className="underline underline-offset-4 hover:text-fg"
        >
          sign out
        </button>
      </span>
    </header>
  )
}
