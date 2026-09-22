import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  bootstrap,
  getAccessToken,
  login,
  logout,
  refreshAccessToken,
  setAccessToken,
} from '../auth'

function respond(status: number, body: unknown) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => setAccessToken(null))
afterEach(() => vi.unstubAllGlobals())

describe('refreshAccessToken', () => {
  it('issues exactly one request for concurrent callers', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(200, { access_token: 'fresh' }))
    vi.stubGlobal('fetch', fetchMock)

    const results = await Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
      refreshAccessToken(),
      refreshAccessToken(),
    ])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(results).toEqual(['fresh', 'fresh', 'fresh', 'fresh'])
  })

  it('stores the token it fetched', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(200, { access_token: 'fresh' })))

    await refreshAccessToken()

    expect(getAccessToken()).toBe('fresh')
  })

  it('allows a later refresh once the first settled', async () => {
    const fetchMock = vi.fn(async () => respond(200, { access_token: 'fresh' }))
    vi.stubGlobal('fetch', fetchMock)

    await refreshAccessToken()
    await refreshAccessToken()

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('clears the token and returns null when refresh fails', async () => {
    setAccessToken('stale')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(401, { detail: 'Not authenticated' })))

    const token = await refreshAccessToken()

    expect(token).toBeNull()
    expect(getAccessToken()).toBeNull()
  })

  it('does not cache a failed refresh', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(401, { detail: 'Not authenticated' }))
      .mockResolvedValueOnce(respond(200, { access_token: 'fresh' }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await refreshAccessToken()).toBeNull()
    expect(await refreshAccessToken()).toBe('fresh')
  })
})

describe('bootstrap', () => {
  it('reports authenticated when the cookie is still good', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(200, { access_token: 'fresh' })))

    expect(await bootstrap()).toBe(true)
  })

  it('reports anonymous on 401 without throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(401, { detail: 'Not authenticated' })))

    expect(await bootstrap()).toBe(false)
  })
})

describe('login and logout', () => {
  it('stores the access token on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(200, { access_token: 'issued' })))

    const result = await login('a@b.dev', 'supersecret1')

    expect(result.ok).toBe(true)
    expect(getAccessToken()).toBe('issued')
  })

  it('leaves the token unset on bad credentials', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(respond(401, { detail: 'Invalid email or password' })),
    )

    const result = await login('a@b.dev', 'wrongpassword')

    expect(result.ok).toBe(false)
    expect(getAccessToken()).toBeNull()
  })

  it('clears the token even if the logout call fails', async () => {
    setAccessToken('live')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    await logout()

    expect(getAccessToken()).toBeNull()
  })
})
