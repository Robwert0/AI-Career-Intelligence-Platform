'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useAuth } from '@/components/AuthProvider'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status, logoutIncomplete } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status !== 'anonymous') return
    router.replace(logoutIncomplete ? '/login?logout=incomplete' : '/login')
  }, [status, logoutIncomplete, router])

  if (status !== 'authenticated') {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-1 items-center px-4">
        <p className="font-mono text-xs text-muted">checking session…</p>
      </main>
    )
  }

  return <>{children}</>
}
