import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatWhen, listUsers } from '../admin'

afterEach(() => vi.unstubAllGlobals())

describe('listUsers', () => {
  it('requests one page at the given offset', async () => {
    const fetchMock = vi.fn<(url: string) => Promise<Response>>(
      async () =>
        new Response(JSON.stringify({ items: [], total: 0, by_role: {}, limit: 50, offset: 50 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listUsers(50)

    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/users?limit=50&offset=50')
  })
})

describe('formatWhen', () => {
  it('says never for a missing time', () => {
    expect(formatWhen(null)).toBe('never')
  })

  it('formats an ISO time as a short date and time', () => {
    expect(formatWhen('2026-10-05T09:07:00Z')).toMatch(/2026/)
  })
})
