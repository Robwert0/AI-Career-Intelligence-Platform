'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import {
  bootstrap,
  currentAccountId,
  login,
  logout,
  register,
  setAccessToken,
  type SignUpProfile,
} from '@/lib/auth'
import type { ApiResult } from '@/lib/http'
import { claimTabSession, clearTabSession } from '@/lib/tabSession'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

type AuthValue = {
  status: AuthStatus
  accountId: string | null
  signIn: (email: string, password: string) => Promise<ApiResult<unknown>>
  signUp: (email: string, password: string, profile?: SignUpProfile) => Promise<ApiResult<unknown>>
  signOut: () => Promise<ApiResult<void>>
  sessionExpired: () => void
  exitReason: ExitReason
}

export type ExitReason = 'clean' | 'incomplete' | 'expired'

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [exitReason, setExitReason] = useState<ExitReason>('clean')
  const [accountId, setAccountId] = useState<string | null>(null)

  // Claimed before status flips, so no page can read tab state another account left behind.
  const enter = useCallback(() => {
    const id = currentAccountId()
    if (id !== null) claimTabSession(id)
    setAccountId(id)
    setStatus('authenticated')
  }, [])

  useEffect(() => {
    bootstrap()
      .then((authenticated) => (authenticated ? enter() : setStatus('anonymous')))
      .catch(() => setStatus('anonymous'))
  }, [enter])

  const signIn = useCallback(
    async (email: string, password: string) => {
      const result = await login(email, password)
      if (result.ok) {
        setExitReason('clean')
        enter()
      }
      return result
    },
    [enter],
  )

  const signUp = useCallback(
    (email: string, password: string, profile?: SignUpProfile) =>
      register(email, password, profile),
    [],
  )

  const signOut = useCallback(async () => {
    const result = await logout()
    clearTabSession()
    setAccountId(null)
    setExitReason(result.ok ? 'clean' : 'incomplete')
    setStatus('anonymous')
    return result
  }, [])

  const sessionExpired = useCallback(() => {
    // Tab state is kept: signing back in as the same account resumes it, and a different
    // account's sign-in clears it through claimTabSession.
    setAccessToken(null)
    setAccountId(null)
    setExitReason('expired')
    setStatus('anonymous')
  }, [])

  return (
    <AuthContext.Provider
      value={{ status, accountId, signIn, signUp, signOut, sessionExpired, exitReason }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (value === null) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
