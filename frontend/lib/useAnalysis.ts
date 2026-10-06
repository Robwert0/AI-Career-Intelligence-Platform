import { useEffect, useEffectEvent, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { decideOutcome, discardOutcome } from '@/lib/analysisDecide'
import {
  continueAnalysis,
  discardAnalysis,
  getAnalysis,
  retryAnalysis,
  type AnalysisStatus,
  type AnalysisView,
  type CandidateSource,
  type MatchReport,
} from '@/lib/match'
import { requestProblem, type Problem } from '@/lib/matchErrors'
import { analysisProblem } from '@/lib/matchProgress'
import { expiresAt as deadline } from '@/lib/matchRecovery'
import { poll } from '@/lib/poll'

const FINAL = new Set<AnalysisStatus>(['done', 'failed', 'needs_decision'])

type Handlers = {
  onReport: (report: MatchReport, expiresAt: number | null) => void
  onMoved: (analysisId: string) => void
  onDiscarded: () => void
  onGone?: () => void
}

export function useAnalysis(
  analysisId: string,
  { onReport, onMoved, onDiscarded, onGone }: Handlers,
) {
  const { sessionExpired } = useAuth()
  const [view, setView] = useState<AnalysisView | null>(null)
  const [problem, setProblem] = useState<Problem | null>(null)
  const [round, setRound] = useState(0)
  const [acting, setActing] = useState(false)
  const [skipped, setSkipped] = useState<CandidateSource[]>([])
  const [expiresAt, setExpiresAt] = useState<number | null>(null)
  const deliver = useEffectEvent(onReport)
  const forget = useEffectEvent(() => onGone?.())

  useEffect(() => {
    const controller = new AbortController()
    void poll<AnalysisView>({
      load: () => getAnalysis(analysisId),
      isFinal: (next) => FINAL.has(next.status),
      onValue: (next) => {
        const expiry = deadline(next.expires_in_seconds, Date.now())
        setView(next)
        setExpiresAt(expiry)
        const problem = analysisProblem(next)
        if (problem !== null) {
          setProblem(problem)
          return
        }
        if (next.status === 'done') deliver(next.report, expiry)
      },
      onFailure: (failure) => {
        if (failure.status === 401) {
          sessionExpired()
          return
        }
        if (failure.status === 404) forget()
        setProblem(requestProblem(failure))
      },
      signal: controller.signal,
    })
    return () => controller.abort()
  }, [analysisId, round, sessionExpired])

  function resume() {
    setProblem(null)
    setRound((current) => current + 1)
  }

  async function decide(action: 'continue' | 'retry', form?: FormData) {
    const source = view?.decision?.failed_source
    setActing(true)
    setProblem(null)
    const result =
      action === 'continue'
        ? await continueAnalysis(analysisId)
        : await retryAnalysis(analysisId, form)
    setActing(false)

    if (action === 'continue' && result.ok && source !== undefined) {
      setSkipped((current) => [...current, source])
    }

    const outcome = decideOutcome(action, analysisId, result)
    switch (outcome.type) {
      case 'moved':
        onMoved(outcome.analysisId)
        return
      case 'succeeded':
        setView(null)
        setRound((current) => current + 1)
        return
      case 'stale':
        resume()
        return
      case 'session_ended':
        sessionExpired()
        return
      case 'problem':
        setProblem(outcome.problem)
        return
    }
  }

  // Start over must release the server's one-active-analysis lock first; a local reset alone
  // leaves the next submit 409-ing straight back to this analysis.
  async function startOver() {
    setActing(true)
    setProblem(null)
    const outcome = discardOutcome(await discardAnalysis(analysisId))
    setActing(false)
    switch (outcome.type) {
      case 'reset':
        onDiscarded()
        return
      case 'session_ended':
        sessionExpired()
        return
      case 'problem':
        setProblem(outcome.problem)
        return
    }
  }

  return {
    view,
    expiresAt,
    problem,
    acting,
    skipped,
    continueWithout: () => decide('continue'),
    retry: (form?: FormData) => decide('retry', form),
    resume,
    startOver,
  }
}
