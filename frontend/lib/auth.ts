import { ApiResult, request } from './http'

type TokenResponse = { access_token: string }

let accessToken: string | null = null
let inFlight: Promise<string | null> | null = null
let logoutEpoch = 0

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

function tokenFrom(data: unknown): string | null {
  if (typeof data !== 'object' || data === null) return null
  const candidate = (data as { access_token?: unknown }).access_token
  return typeof candidate === 'string' && candidate.length > 0 ? candidate : null
}

async function performRefresh(): Promise<string | null> {
  const epoch = logoutEpoch
  const result = await request<TokenResponse>('/auth/refresh', { method: 'POST' })

  if (!result.ok) {
    if (result.status === 401 || result.status === 403) accessToken = null
    return null
  }

  const token = tokenFrom(result.data)
  if (token === null) {
    accessToken = null
    return null
  }

  if (epoch !== logoutEpoch) return null

  accessToken = token
  return token
}

export function refreshAccessToken(): Promise<string | null> {
  inFlight ??= performRefresh().finally(() => {
    inFlight = null
  })
  return inFlight
}

export async function login(email: string, password: string): Promise<ApiResult<TokenResponse>> {
  const result = await request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  if (result.ok) accessToken = tokenFrom(result.data)
  return result
}

export function register(email: string, password: string): Promise<ApiResult<unknown>> {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export async function logout(): Promise<void> {
  logoutEpoch += 1
  await request<void>('/auth/logout', { method: 'POST' })
  accessToken = null
}

export async function bootstrap(): Promise<boolean> {
  return (await refreshAccessToken()) !== null
}
