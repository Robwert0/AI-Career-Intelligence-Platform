'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { bootstrap, login, logout, register, setAccessToken } from '@/lib/auth'
import type { ApiResult } from '@/lib/http'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

type AuthValue = {
  status: AuthStatus
  signIn: (email: string, password: string) => Promise<ApiResult<unknown>>
  signUp: (email: string, password: string) => Promise<ApiResult<unknown>>
  signOut: () => Promise<ApiResult<void>>
  sessionExpired: () => void
  exitReason: ExitReason
}

export type ExitReason = 'clean' | 'incomplete' | 'expired'

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [exitReason, setExitReason] = useState<ExitReason>('clean')

  useEffect(() => {
    bootstrap()
      .then((authenticated) => setStatus(authenticated ? 'authenticated' : 'anonymous'))
      .catch(() => setStatus('anonymous'))
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await login(email, password)
    if (result.ok) {
      setExitReason('clean')
      setStatus('authenticated')
    }
    return result
  }, [])

  const signUp = useCallback((email: string, password: string) => register(email, password), [])

  const signOut = useCallback(async () => {
    const result = await logout()
    setExitReason(result.ok ? 'clean' : 'incomplete')
    setStatus('anonymous')
    return result
  }, [])

  const sessionExpired = useCallback(() => {
    setAccessToken(null)
    setExitReason('expired')
    setStatus('anonymous')
  }, [])

  return (
    <AuthContext.Provider value={{ status, signIn, signUp, signOut, sessionExpired, exitReason }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (value === null) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
