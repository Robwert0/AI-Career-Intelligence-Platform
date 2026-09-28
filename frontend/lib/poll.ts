import type { ApiFailure, ApiResult } from './http'

export const POLL_INTERVAL_MS = 1500
// Ceiling for our own exponential backoff, so a run of transient failures with no server hint
// still polls often enough to feel responsive.
export const MAX_BACKOFF_MS = 15_000
// Ceiling even when a 429's Retry-After asks for longer: the per-user poll bucket refills every
// minute (contract §"Amended 2026-09-28"), so a minute is the longest wait that's ever load-bearing.
export const MAX_POLL_INTERVAL_MS = 60_000
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
  const backoff = Math.min(POLL_INTERVAL_MS * 2 ** failures, MAX_BACKOFF_MS)
  if (retryAfterSeconds === undefined) return backoff
  return Math.min(Math.max(backoff, retryAfterSeconds * 1000), MAX_POLL_INTERVAL_MS)
}

// A thrown error here (a `load` rejection, or `onValue` throwing while rendering the value it was
// just given) must not surface as a silent unhandled rejection: the caller only ever awaits this
// promise via `void poll(...)`, so nothing else would ever report it.
function unreachableFailure(): ApiFailure {
  return { ok: false, status: 0, detail: 'Something went wrong while checking for updates.' }
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
    try {
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
    } catch {
      onFailure(unreachableFailure())
      return
    }
  }
}
