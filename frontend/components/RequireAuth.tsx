'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useAuth } from '@/components/AuthProvider'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status === 'anonymous') router.replace('/login')
  }, [status, router])

  if (status !== 'authenticated') {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-1 items-center px-4">
        <p className="font-mono text-xs text-muted">checking session…</p>
      </main>
    )
  }

  return <>{children}</>
}
