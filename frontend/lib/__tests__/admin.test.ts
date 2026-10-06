import { afterEach, describe, expect, it, vi } from 'vitest'
import { type AdminUserRow, appendUnique, formatWhen, isPurgeStale, listUsers } from '../admin'

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

describe('appendUnique', () => {
  const row = (id: string): AdminUserRow => ({
    id,
    email: `${id}@test.dev`,
    company: null,
    role: null,
    created_at: '2026-10-05T09:07:00Z',
    last_active_at: null,
  })

  it('drops rows already loaded and keeps the order of the rest', () => {
    const merged = appendUnique([row('a'), row('b')], [row('b'), row('c'), row('d')])

    expect(merged.map((r) => r.id)).toEqual(['a', 'b', 'c', 'd'])
  })
})

describe('isPurgeStale', () => {
  const now = new Date('2026-10-05T12:00:00Z')
  const hoursAgo = (hours: number) => new Date(now.getTime() - hours * 3_600_000).toISOString()

  it('treats a purge that never ran as stale', () => {
    expect(isPurgeStale(null, now)).toBe(true)
  })

  it('treats a purge 47 hours ago as fresh', () => {
    expect(isPurgeStale(hoursAgo(47), now)).toBe(false)
  })

  it('treats a purge 49 hours ago as stale', () => {
    expect(isPurgeStale(hoursAgo(49), now)).toBe(true)
  })

  it('treats an unparseable time as stale', () => {
    expect(isPurgeStale('not a date', now)).toBe(true)
  })
})
