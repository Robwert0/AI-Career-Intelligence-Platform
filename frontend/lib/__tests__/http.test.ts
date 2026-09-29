import { afterEach, describe, expect, it, vi } from 'vitest'
import { request } from '../http'

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('request', () => {
  it('returns parsed data on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(200, { access_token: 'abc' })))

    const result = await request<{ access_token: string }>('/auth/login')

    expect(result).toEqual({ ok: true, data: { access_token: 'abc' } })
  })

  it('prefixes every path with /api', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(200, {}))
    vi.stubGlobal('fetch', fetchMock)

    await request('/users/me')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/users/me')
  })

  it('maps a string detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(respond(409, { detail: 'Email already registered' })),
    )

    const result = await request('/auth/register')

    expect(result).toEqual({ ok: false, status: 409, detail: 'Email already registered' })
  })

  it('flattens a 422 detail array into one message', async () => {
    const body = {
      detail: [{ loc: ['body', 'message'], msg: 'String should have at most 2000 characters' }],
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(422, body)))

    const result = await request('/chat')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.detail).toBe('String should have at most 2000 characters')
  })

  it('parses Retry-After into seconds', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(respond(429, { detail: 'Too many requests' }, { 'Retry-After': '17' })),
    )

    const result = await request('/chat')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.retryAfter).toBe(17)
  })

  it('handles a 204 with no body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))

    const result = await request<void>('/auth/logout', { method: 'POST' })

    expect(result.ok).toBe(true)
  })

  it('does not report success when a 200 body is unreadable', async () => {
    const garbled = new Response('not json at all', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(garbled))

    const result = await request('/users/me')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.detail).toBe('The server sent an unreadable response')
  })

  it('sends an abort signal so a stalled request cannot hang forever', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(200, {}))
    vi.stubGlobal('fetch', fetchMock)

    await request('/users/me')

    expect((fetchMock.mock.calls[0][1] as RequestInit).signal).toBeInstanceOf(AbortSignal)
  })

  it('reports a timeout as an unreachable server', async () => {
    const aborted = Object.assign(new Error('The operation was aborted'), { name: 'TimeoutError' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(aborted))

    const result = await request('/users/me')

    expect(result).toMatchObject({ ok: false, status: 0, detail: 'Could not reach the server' })
  })

  it('reports a network failure as status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    const result = await request('/users/me')

    expect(result).toMatchObject({ ok: false, status: 0 })
  })

  it('surfaces a coded detail as its message, code and body', async () => {
    const body = {
      detail: { code: 'analysis_in_progress', message: 'An analysis is already running.' },
      analysis_id: 'a1',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => respond(409, body)),
    )

    const result = await request('/match/analyses')

    expect(result).toEqual({
      ok: false,
      status: 409,
      detail: 'An analysis is already running.',
      code: 'analysis_in_progress',
      body,
    })
  })

  it('adds no code for a plain string detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => respond(404, { detail: 'Not found' })),
    )

    const result = await request('/match/jobs/x')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.code).toBeUndefined()
  })

  it('lets the browser set the multipart content type for FormData', async () => {
    const fetchMock = vi.fn(async () => respond(202, { analysis_id: 'a1' }))
    vi.stubGlobal('fetch', fetchMock)
    const form = new FormData()
    form.append('consent', 'true')

    await request('/match/analyses', { method: 'POST', body: form })

    const init = (fetchMock.mock.calls[0] as unknown[])[1] as RequestInit
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined()
    expect(init.body).toBe(form)
  })

  it('keeps a caller-supplied signal', async () => {
    const fetchMock = vi.fn(async () => respond(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    await request('/users/me', { signal: controller.signal })

    const init = (fetchMock.mock.calls[0] as unknown[])[1] as RequestInit
    expect(init.signal).toBe(controller.signal)
  })
})
