import { useEffect, useEffectEvent, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { getJob, submitJob, type FailureOut, type JobIntake, type JobView } from '@/lib/match'
import { requestProblem, type Problem } from '@/lib/matchErrors'
import { poll } from '@/lib/poll'

const NO_POSTING: Problem = { message: 'The job was read, but no details came back. Try again.' }
const UNKNOWN_FAILURE: FailureOut = {
  code: 'unknown',
  message: 'Something went wrong while reading the job. Try again.',
  recovery: 'retry',
}

export function useJobIntake(onPosting: (view: JobView) => void) {
  const { sessionExpired } = useAuth()
  const [jobId, setJobId] = useState<string | null>(null)
  const [view, setView] = useState<JobView | null>(null)
  const [problem, setProblem] = useState<Problem | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const deliver = useEffectEvent(onPosting)

  useEffect(() => {
    if (jobId === null) return
    const controller = new AbortController()
    void poll<JobView>({
      load: () => getJob(jobId),
      isFinal: (next) => next.status === 'done' || next.status === 'failed',
      onValue: (next) => {
        setView(next)
        if (next.status === 'failed') setJobId(null)
        if (next.status !== 'done') return
        setJobId(null)
        if (next.posting === null) setProblem(NO_POSTING)
        else deliver(next)
      },
      onFailure: (failure) => {
        setJobId(null)
        if (failure.status === 401) sessionExpired()
        else setProblem(requestProblem(failure))
      },
      signal: controller.signal,
    })
    return () => controller.abort()
  }, [jobId, sessionExpired])

  async function extract(intake: JobIntake) {
    setSubmitting(true)
    setProblem(null)
    setView(null)
    const result = await submitJob(intake)
    setSubmitting(false)
    if (result.ok) setJobId(result.data.job_id)
    else if (result.status === 401) sessionExpired()
    else setProblem(requestProblem(result))
  }

  return {
    busy: submitting || jobId !== null,
    view,
    failure: view?.status === 'failed' ? (view.error ?? UNKNOWN_FAILURE) : null,
    problem,
    extract,
  }
}
