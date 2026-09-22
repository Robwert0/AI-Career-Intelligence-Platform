'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { me } from '@/lib/api'
import { authErrorMessage } from '@/lib/messages'

export function SessionBar() {
  const { signOut, sessionExpired } = useAuth()
  const [email, setEmail] = useState<string | null>(null)
  const [signingOut, setSigningOut] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    me().then((result) => {
      if (!active) return
      if (result.ok) setEmail(result.data.email)
      else if (result.status === 401) sessionExpired()
      else setError(authErrorMessage(result))
    })
    return () => {
      active = false
    }
  }, [sessionExpired])

  async function handleSignOut() {
    if (signingOut) return
    setSigningOut(true)
    setError(null)

    await signOut()
  }

  return (
    <header className="mx-auto w-full max-w-2xl border-b border-line px-4 py-3">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-sm">cv.chat</span>
        <span className="flex items-baseline gap-4 font-mono text-xs text-muted">
          {email}
          <button
            type="button"
            onClick={handleSignOut}
            disabled={signingOut}
            className="underline underline-offset-4 hover:text-fg disabled:opacity-40"
          >
            {signingOut ? 'signing out…' : 'sign out'}
          </button>
        </span>
      </div>
      {error ? (
        <p role="alert" aria-live="polite" className="pt-2 font-mono text-xs text-danger">
          {error}
        </p>
      ) : null}
    </header>
  )
}
