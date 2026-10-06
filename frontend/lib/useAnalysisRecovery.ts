import { useEffect, useState, type Dispatch } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { currentAccountId } from './auth'
import { getAnalysis } from './match'
import type { FlowAction } from './matchFlow'
import {
  clearRecoveryId,
  isCurrentRestore,
  readRecoveryId,
  restoreOutcome,
  saveRecoveryId,
} from './matchRecovery'

export type RestorePhase =
  | { type: 'none' }
  | { type: 'checking' }
  | { type: 'gone' }
  | { type: 'unreachable'; message: string }

// Restores the analysis this tab was showing before a reload, then keeps the stored id in step
// with whichever analysis is on screen.
export function useAnalysisRecovery(analysisId: string | null, dispatch: Dispatch<FlowAction>) {
  const { accountId, sessionExpired } = useAuth()
  const [phase, setPhase] = useState<RestorePhase>(() =>
    readRecoveryId() === null ? { type: 'none' } : { type: 'checking' },
  )

  useEffect(() => {
    if (phase.type !== 'checking') return
    const storedId = readRecoveryId()
    if (storedId === null) return
    const request = { accountId, analysisId: storedId }
    let active = true
    void getAnalysis(storedId).then((result) => {
      const now = { accountId: currentAccountId(), storedId: readRecoveryId() }
      if (!active || !isCurrentRestore(request, now)) return
      const outcome = restoreOutcome(result, Date.now())
      switch (outcome.type) {
        case 'report':
          dispatch({ type: 'analysisRestored', analysisId: outcome.analysisId })
          dispatch({
            type: 'analysisFinished',
            report: outcome.report,
            expiresAt: outcome.expiresAt,
          })
          setPhase({ type: 'none' })
          return
        case 'progress':
          dispatch({ type: 'analysisRestored', analysisId: outcome.analysisId })
          setPhase({ type: 'none' })
          return
        case 'gone':
          clearRecoveryId()
          setPhase({ type: 'gone' })
          return
        case 'session_ended':
          sessionExpired()
          return
        case 'unreachable':
          setPhase({ type: 'unreachable', message: outcome.message })
          return
      }
    })
    return () => {
      active = false
    }
  }, [phase.type, accountId, sessionExpired, dispatch])

  // Until a pending restore settles, the stored id is the only copy of it and must not be cleared.
  useEffect(() => {
    if (phase.type === 'checking' || phase.type === 'unreachable') return
    if (analysisId === null) clearRecoveryId()
    else saveRecoveryId(analysisId)
  }, [analysisId, phase.type])

  return {
    phase,
    retry: () => setPhase({ type: 'checking' }),
    abandon: () => {
      clearRecoveryId()
      setPhase({ type: 'none' })
    },
  }
}
