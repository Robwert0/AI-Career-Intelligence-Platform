import type { ApiFailure, ApiResult } from './http'

export const POLL_INTERVAL_MS = 1500
export const MAX_POLL_INTERVAL_MS = 15_000
export const MAX_TRANSIENT_FAILURES = 5

const TRANSIENT_STATUSES = new Set([0, 429, 502, 503, 504])

export type PollOptions<T> = {
  load: () => Promise<ApiResult<T>>
  isFinal: (value: T) => boolean
  onValue: (value: T) => void
  onFailure: (failure: ApiFailure) => void
  signal: AbortSignal
  wait?: (ms: number, signal: AbortSignal) => Promise<void>
}

export function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }
    const finish = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = setTimeout(finish, ms)
    signal.addEventListener('abort', finish, { once: true })
  })
}

export function nextDelay(failures: number, retryAfterSeconds?: number): number {
  if (failures === 0) return POLL_INTERVAL_MS
  const backoff = Math.min(POLL_INTERVAL_MS * 2 ** failures, MAX_POLL_INTERVAL_MS)
  if (retryAfterSeconds === undefined) return backoff
  return Math.min(Math.max(backoff, retryAfterSeconds * 1000), MAX_POLL_INTERVAL_MS)
}

export async function poll<T>({
  load,
  isFinal,
  onValue,
  onFailure,
  signal,
  wait: pause = wait,
}: PollOptions<T>): Promise<void> {
  let failures = 0
  while (!signal.aborted) {
    const result = await load()
    if (signal.aborted) return

    if (result.ok) {
      failures = 0
      onValue(result.data)
      if (isFinal(result.data)) return
    } else if (TRANSIENT_STATUSES.has(result.status) && failures < MAX_TRANSIENT_FAILURES) {
      failures += 1
    } else {
      onFailure(result)
      return
    }

    await pause(nextDelay(failures, result.ok ? undefined : result.retryAfter), signal)
  }
}
