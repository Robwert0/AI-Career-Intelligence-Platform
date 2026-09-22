import { getAccessToken, refreshAccessToken } from './auth'
import { ApiResult, request } from './http'

export type UserRead = { id: string; email: string; created_at: string }
export type Source = { section: string; content: string }
export type ChatResponse = { answer: string; refused: boolean; sources: Source[] }

function withToken(init: RequestInit, token: string | null): RequestInit {
  if (token === null) return init
  return { ...init, headers: { ...init.headers, Authorization: `Bearer ${token}` } }
}

export async function authedRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<ApiResult<T>> {
  const result = await request<T>(path, withToken(init, getAccessToken()))
  if (result.ok || result.status !== 401) return result

  const refreshed = await refreshAccessToken()
  if (refreshed === null) return result

  return request<T>(path, withToken(init, refreshed))
}

export function me(): Promise<ApiResult<UserRead>> {
  return authedRequest<UserRead>('/users/me')
}

export function chat(message: string): Promise<ApiResult<ChatResponse>> {
  return authedRequest<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
}
