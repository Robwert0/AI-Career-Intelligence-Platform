'use client'

import { useEffect, useState } from 'react'
import { availabilityText } from '@/lib/matchRecovery'

const TICK_MS = 30_000

export function Availability({ expiresAt }: { expiresAt: number | null }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), TICK_MS)
    return () => clearInterval(timer)
  }, [])

  if (expiresAt === null) return null
  return <p className="text-sm text-muted">{availabilityText(expiresAt, now)}</p>
}
