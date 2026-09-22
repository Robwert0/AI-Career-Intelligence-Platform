'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useAuth, type ExitReason } from '@/components/AuthProvider'

const EXIT_DESTINATION: Record<ExitReason, string> = {
  clean: '/login',
  incomplete: '/login?logout=incomplete',
  expired: '/login?session=expired',
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status, exitReason } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status !== 'anonymous') return
    router.replace(EXIT_DESTINATION[exitReason])
  }, [status, exitReason, router])

  if (status !== 'authenticated') {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-1 items-center px-4">
        <p className="font-mono text-xs text-muted">checking session…</p>
      </main>
    )
  }

  return <>{children}</>
}
