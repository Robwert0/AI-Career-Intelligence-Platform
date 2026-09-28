import { useEffect, useEffectEvent, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { decideOutcome } from '@/lib/analysisDecide'
import {
  continueAnalysis,
  getAnalysis,
  retryAnalysis,
  type AnalysisStatus,
  type AnalysisView,
  type CandidateSource,
  type MatchReport,
} from '@/lib/match'
import { requestProblem, type Problem } from '@/lib/matchErrors'
import { analysisProblem } from '@/lib/matchProgress'
import { poll } from '@/lib/poll'

const FINAL = new Set<AnalysisStatus>(['done', 'failed', 'needs_decision'])

type Handlers = {
  onReport: (report: MatchReport) => void
  onMoved: (analysisId: string) => void
}

export function useAnalysis(analysisId: string, { onReport, onMoved }: Handlers) {
  const { sessionExpired } = useAuth()
  const [view, setView] = useState<AnalysisView | null>(null)
  const [problem, setProblem] = useState<Problem | null>(null)
  const [round, setRound] = useState(0)
  const [acting, setActing] = useState(false)
  const [skipped, setSkipped] = useState<CandidateSource[]>([])
  const deliver = useEffectEvent(onReport)

  useEffect(() => {
    const controller = new AbortController()
    void poll<AnalysisView>({
      load: () => getAnalysis(analysisId),
      isFinal: (next) => FINAL.has(next.status),
      onValue: (next) => {
        setView(next)
        const problem = analysisProblem(next)
        if (problem !== null) {
          setProblem(problem)
          return
        }
        if (next.status === 'done') deliver(next.report)
      },
      onFailure: (failure) => {
        if (failure.status === 401) sessionExpired()
        else setProblem(requestProblem(failure))
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

  return {
    view,
    problem,
    acting,
    skipped,
    continueWithout: () => decide('continue'),
    retry: (form?: FormData) => decide('retry', form),
    resume,
  }
}
