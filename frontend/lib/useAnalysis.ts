import { useEffect, useEffectEvent, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import {
  continueAnalysis,
  getAnalysis,
  retryAnalysis,
  type AnalysisStatus,
  type AnalysisView,
  type CandidateSource,
  type MatchReport,
} from '@/lib/match'
import { requestProblem, retryLimitProblem, type Problem } from '@/lib/matchErrors'
import { poll } from '@/lib/poll'

const FINAL = new Set<AnalysisStatus>(['done', 'failed', 'needs_decision'])
const NO_REPORT: Problem = { message: 'The analysis finished, but no report came back. Try again.' }

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
        if (next.status !== 'done') return
        if (next.report === null) setProblem(NO_REPORT)
        else deliver(next.report)
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

    if (result.ok) {
      if (action === 'continue' && source !== undefined) {
        setSkipped((current) => [...current, source])
      }
      if (result.data.analysis_id !== analysisId) {
        onMoved(result.data.analysis_id)
        return
      }
      setView(null)
      setRound((current) => current + 1)
      return
    }
    if (result.code === 'not_awaiting_decision') {
      resume()
      return
    }
    if (result.status === 401) sessionExpired()
    // retry spends a 5/hour analysis token; continue only spends the poll limit.
    else setProblem(action === 'retry' ? retryLimitProblem(result) : requestProblem(result))
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
