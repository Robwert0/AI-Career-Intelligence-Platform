import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { chat, me } from '../api'
import { getAccessToken, setAccessToken } from '../auth'

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function headersOf(call: unknown[]): Record<string, string> {
  return (call[1] as RequestInit).headers as Record<string, string>
}

beforeEach(() => setAccessToken(null))
afterEach(() => vi.unstubAllGlobals())

describe('authedRequest', () => {
  it('attaches the bearer token', async () => {
    setAccessToken('live')
    const fetchMock = vi.fn(async () => respond(200, { answer: 'x', refused: false, sources: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await chat('hello')

    expect(headersOf(fetchMock.mock.calls[0]).Authorization).toBe('Bearer live')
  })

  it('sends no authorization header when anonymous', async () => {
    const fetchMock = vi.fn(async () => respond(200, { id: '1', email: 'a@b.dev', created_at: 'now' }))
    vi.stubGlobal('fetch', fetchMock)

    await me()

    expect(headersOf(fetchMock.mock.calls[0]).Authorization).toBeUndefined()
  })

  it('refreshes once and retries a 401', async () => {
    setAccessToken('stale')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(401, { detail: 'Not authenticated' }))
      .mockResolvedValueOnce(respond(200, { access_token: 'fresh' }))
      .mockResolvedValueOnce(respond(200, { id: '1', email: 'a@b.dev', created_at: 'now' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await me()

    expect(result.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(headersOf(fetchMock.mock.calls[2]).Authorization).toBe('Bearer fresh')
  })

  it('retries at most once', async () => {
    setAccessToken('stale')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(401, { detail: 'Not authenticated' }))
      .mockResolvedValueOnce(respond(200, { access_token: 'fresh' }))
      .mockResolvedValueOnce(respond(401, { detail: 'Not authenticated' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await me()

    expect(result.ok).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('does not retry when the refresh itself fails', async () => {
    setAccessToken('stale')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(401, { detail: 'Not authenticated' }))
      .mockResolvedValueOnce(respond(401, { detail: 'Not authenticated' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await me()

    expect(result.ok).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(getAccessToken()).toBeNull()
  })

  it('does not refresh on a non-401 failure', async () => {
    setAccessToken('live')
    const fetchMock = vi.fn(async () => respond(503, { detail: 'Service unavailable' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await chat('hello')

    expect(result.ok).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('passes a 429 through with its retry hint', async () => {
    setAccessToken('live')
    const fetchMock = vi.fn(async () =>
      respond(429, { detail: 'Too many requests' }, { 'Retry-After': '12' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await chat('hello')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.retryAfter).toBe(12)
  })
})
