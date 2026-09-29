import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setAccessToken } from '../auth'
import {
  continueAnalysis,
  discardAnalysis,
  getAnalysis,
  getJob,
  getMatchConfig,
  retryAnalysis,
  submitAnalysis,
  submitJob,
} from '../match'

function respond(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function call(fetchMock: { mock: { calls: unknown[][] } }, index = 0) {
  const [url, init] = fetchMock.mock.calls[index] as [string, RequestInit]
  return { url, init, headers: init.headers as Record<string, string> }
}

beforeEach(() => setAccessToken('live'))
afterEach(() => vi.unstubAllGlobals())

describe('match client', () => {
  it('submits a job URL as JSON with the bearer token', async () => {
    const fetchMock = vi.fn(async () => respond(202, { job_id: 'j1' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await submitJob({ url: 'https://jobs.example.com/1' })

    const { url, init, headers } = call(fetchMock)
    expect(result).toEqual({ ok: true, data: { job_id: 'j1' } })
    expect(url).toBe('/api/match/jobs')
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"url":"https://jobs.example.com/1"}')
    expect(headers.Authorization).toBe('Bearer live')
  })

  it('encodes the job id into the poll path', async () => {
    const fetchMock = vi.fn(async () => respond(200, {}))
    vi.stubGlobal('fetch', fetchMock)

    await getJob('a/b')

    expect(call(fetchMock).url).toBe('/api/match/jobs/a%2Fb')
  })

  it('uploads an analysis as multipart with a long timeout', async () => {
    const fetchMock = vi.fn(async () => respond(202, { analysis_id: 'a1' }))
    vi.stubGlobal('fetch', fetchMock)
    const form = new FormData()

    await submitAnalysis(form)

    const { url, init, headers } = call(fetchMock)
    expect(url).toBe('/api/match/analyses')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(form)
    expect(headers['Content-Type']).toBeUndefined()
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('polls an analysis', async () => {
    const fetchMock = vi.fn(async () => respond(200, {}))
    vi.stubGlobal('fetch', fetchMock)

    await getAnalysis('a1')

    expect(call(fetchMock).url).toBe('/api/match/analyses/a1')
  })

  it('continues without a body', async () => {
    const fetchMock = vi.fn(async () => respond(202, { analysis_id: 'a1' }))
    vi.stubGlobal('fetch', fetchMock)

    await continueAnalysis('a1')

    const { url, init } = call(fetchMock)
    expect(url).toBe('/api/match/analyses/a1/continue')
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
  })

  it('retries GitHub with no body and the CV with the CV again', async () => {
    const fetchMock = vi.fn(async () => respond(202, { analysis_id: 'a1' }))
    vi.stubGlobal('fetch', fetchMock)
    const form = new FormData()

    await retryAnalysis('a1')
    await retryAnalysis('a1', form)

    expect(call(fetchMock, 0).url).toBe('/api/match/analyses/a1/retry')
    expect(call(fetchMock, 0).init.body).toBeUndefined()
    expect(call(fetchMock, 1).init.body).toBe(form)
  })

  it('keeps the running analysis id from a 409', async () => {
    const body = {
      detail: { code: 'analysis_in_progress', message: 'Already running.' },
      analysis_id: 'running-1',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => respond(409, body)),
    )

    const result = await submitAnalysis(new FormData())

    expect(result).toMatchObject({ ok: false, status: 409, code: 'analysis_in_progress', body })
  })

  it('discards an analysis with a bodyless POST', async () => {
    const fetchMock = vi.fn(async () => respond(200, { analysis_id: 'a1' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await discardAnalysis('a/1')

    const { url, init } = call(fetchMock)
    expect(result).toEqual({ ok: true, data: { analysis_id: 'a1' } })
    expect(url).toBe('/api/match/analyses/a%2F1/discard')
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
  })

  it('reads the upload limits from GET /match/config', async () => {
    const config = { max_upload_bytes: 2_097_152, cv_text_min_chars: 50, cv_text_max_chars: 40_000 }
    const fetchMock = vi.fn(async () => respond(200, config))
    vi.stubGlobal('fetch', fetchMock)

    const result = await getMatchConfig()

    expect(call(fetchMock).url).toBe('/api/match/config')
    expect(result).toEqual({ ok: true, data: config })
  })
})
