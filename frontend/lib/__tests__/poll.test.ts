import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ApiResult } from '../http'
import {
  MAX_POLL_INTERVAL_MS,
  MAX_TRANSIENT_FAILURES,
  POLL_INTERVAL_MS,
  nextDelay,
  poll,
  wait,
} from '../poll'

type View = { status: 'running' | 'done' }

const running: ApiResult<View> = { ok: true, data: { status: 'running' } }
const done: ApiResult<View> = { ok: true, data: { status: 'done' } }

function failed(status: number, retryAfter?: number): ApiResult<View> {
  return { ok: false, status, detail: 'x', retryAfter }
}

function harness(results: ApiResult<View>[]) {
  const queue = [...results]
  const load = vi.fn(async () => {
    const next = queue.shift()
    if (next === undefined) throw new Error('polled after it should have stopped')
    return next
  })
  const delays: number[] = []
  const onValue = vi.fn()
  const onFailure = vi.fn()
  const run = () =>
    poll<View>({
      load,
      isFinal: (value) => value.status === 'done',
      onValue,
      onFailure,
      signal: new AbortController().signal,
      wait: async (ms) => {
        delays.push(ms)
      },
    })
  return { load, delays, onValue, onFailure, run }
}

describe('poll', () => {
  it('polls at the base interval until a final value', async () => {
    const h = harness([running, running, done])

    await h.run()

    expect(h.onValue).toHaveBeenCalledTimes(3)
    expect(h.delays).toEqual([POLL_INTERVAL_MS, POLL_INTERVAL_MS])
    expect(h.onFailure).not.toHaveBeenCalled()
  })

  it('stops and reports a non-transient failure', async () => {
    const h = harness([running, failed(404)])

    await h.run()

    expect(h.onFailure).toHaveBeenCalledWith(expect.objectContaining({ status: 404 }))
    expect(h.load).toHaveBeenCalledTimes(2)
  })

  it('treats a 401 as final so the caller can end the session', async () => {
    const h = harness([failed(401)])

    await h.run()

    expect(h.onFailure).toHaveBeenCalledWith(expect.objectContaining({ status: 401 }))
    expect(h.load).toHaveBeenCalledTimes(1)
  })

  it('backs off on transient failures and recovers', async () => {
    const h = harness([failed(503), failed(0), done])

    await h.run()

    expect(h.delays).toEqual([3000, 6000])
    expect(h.onFailure).not.toHaveBeenCalled()
    expect(h.onValue).toHaveBeenCalledTimes(1)
  })

  it('backs off using Retry-After on a 429 during polling, without failing the job', async () => {
    const h = harness([failed(429, 10), done])

    await h.run()

    expect(h.delays).toEqual([10_000])
    expect(h.onFailure).not.toHaveBeenCalled()
    expect(h.onValue).toHaveBeenCalledTimes(1)
  })

  it('resets the backoff after a success', async () => {
    const h = harness([failed(503), running, failed(503), done])

    await h.run()

    expect(h.delays).toEqual([3000, POLL_INTERVAL_MS, 3000])
  })

  it('gives up after too many consecutive transient failures', async () => {
    const h = harness(Array.from({ length: MAX_TRANSIENT_FAILURES + 1 }, () => failed(503)))

    await h.run()

    expect(h.load).toHaveBeenCalledTimes(MAX_TRANSIENT_FAILURES + 1)
    expect(h.onFailure).toHaveBeenCalledTimes(1)
  })

  it('ignores a response that arrives after abort', async () => {
    const controller = new AbortController()
    const onValue = vi.fn()

    await poll<View>({
      load: async () => {
        controller.abort()
        return done
      },
      isFinal: () => true,
      onValue,
      onFailure: vi.fn(),
      signal: controller.signal,
      wait: async () => {},
    })

    expect(onValue).not.toHaveBeenCalled()
  })

  it('does not load again once aborted during the wait', async () => {
    const controller = new AbortController()
    const load = vi.fn(async () => running)

    await poll<View>({
      load,
      isFinal: () => false,
      onValue: vi.fn(),
      onFailure: vi.fn(),
      signal: controller.signal,
      wait: async () => controller.abort(),
    })

    expect(load).toHaveBeenCalledTimes(1)
  })
})

describe('nextDelay', () => {
  it.each([
    [0, undefined, POLL_INTERVAL_MS],
    [1, undefined, 3000],
    [2, undefined, 6000],
    [4, undefined, MAX_POLL_INTERVAL_MS],
    [1, 5, 5000],
    [1, 1, 3000],
    [1, 30, MAX_POLL_INTERVAL_MS],
  ])('failures=%s retryAfter=%s → %sms', (failures, retryAfter, expected) => {
    expect(nextDelay(failures, retryAfter)).toBe(expected)
  })
})

describe('wait', () => {
  afterEach(() => vi.useRealTimers())

  it('resolves after the delay', async () => {
    vi.useFakeTimers()
    const pending = wait(1000, new AbortController().signal)

    await vi.advanceTimersByTimeAsync(1000)

    await expect(pending).resolves.toBeUndefined()
  })

  it('resolves at once when aborted and clears its timer', async () => {
    vi.useFakeTimers()
    const controller = new AbortController()
    const pending = wait(10_000, controller.signal)

    controller.abort()
    await pending

    expect(vi.getTimerCount()).toBe(0)
  })
})
