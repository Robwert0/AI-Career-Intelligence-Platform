export type ApiFailure = {
  ok: false
  status: number
  detail: string
  retryAfter?: number
  code?: string
  body?: unknown
}

export type ApiResult<T> = { ok: true; data: T } | ApiFailure

const UNPARSEABLE = Symbol('unparseable')

// Without a deadline a stalled connection never settles, which would leave the app pinned on its
// loading state forever rather than reporting a reachability failure.
const REQUEST_TIMEOUT_MS = 10_000

type ValidationItem = { msg?: string }
type CodedDetail = { code: string; message: string }

function detailFrom(body: unknown, status: number): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const messages = (detail as ValidationItem[]).map((item) => item.msg).filter(Boolean)
      if (messages.length > 0) return messages.join('; ')
    }
  }
  return `Request failed with status ${status}`
}

function codedDetail(body: unknown): CodedDetail | null {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return null
  const detail = (body as { detail: unknown }).detail
  if (typeof detail !== 'object' || detail === null) return null
  const { code, message } = detail as { code?: unknown; message?: unknown }
  return typeof code === 'string' && typeof message === 'string' ? { code, message } : null
}

function retryAfterFrom(response: Response): number | undefined {
  const header = response.headers.get('Retry-After')
  if (header === null) return undefined
  const seconds = Number.parseInt(header, 10)
  return Number.isNaN(seconds) ? undefined : seconds
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      signal: init.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      credentials: 'same-origin',
      // A multipart Content-Type must come from the browser: it carries the boundary.
      headers:
        init.body instanceof FormData
          ? { ...init.headers }
          : { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    return { ok: false, status: 0, detail: 'Could not reach the server' }
  }

  if (response.status === 204) return { ok: true, data: undefined as T }

  const body = await response.json().catch(() => UNPARSEABLE)

  if (!response.ok) {
    const parsed = body === UNPARSEABLE ? null : body
    const coded = codedDetail(parsed)
    const failure: ApiFailure = {
      ok: false,
      status: response.status,
      detail: coded?.message ?? detailFrom(parsed, response.status),
      retryAfter: retryAfterFrom(response),
    }
    return coded === null ? failure : { ...failure, code: coded.code, body: parsed }
  }

  if (body === UNPARSEABLE) {
    return { ok: false, status: response.status, detail: 'The server sent an unreadable response' }
  }

  return { ok: true, data: body as T }
}
