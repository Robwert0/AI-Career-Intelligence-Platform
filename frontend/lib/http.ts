export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; detail: string; retryAfter?: number }

type ValidationItem = { msg?: string }

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
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    return { ok: false, status: 0, detail: 'Could not reach the server' }
  }

  const body = response.status === 204 ? null : await response.json().catch(() => null)

  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      detail: detailFrom(body, response.status),
      retryAfter: retryAfterFrom(response),
    }
  }

  return { ok: true, data: body as T }
}
