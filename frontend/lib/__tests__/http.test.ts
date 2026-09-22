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

  it('reports a network failure as status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    const result = await request('/users/me')

    expect(result).toMatchObject({ ok: false, status: 0 })
  })
})
