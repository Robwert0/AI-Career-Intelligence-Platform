import { ApiResult, request } from './http'

type TokenResponse = { access_token: string }

let accessToken: string | null = null
let inFlight: Promise<string | null> | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

async function performRefresh(): Promise<string | null> {
  const result = await request<TokenResponse>('/auth/refresh', { method: 'POST' })
  if (!result.ok) {
    accessToken = null
    return null
  }
  accessToken = result.data.access_token
  return accessToken
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
  if (result.ok) accessToken = result.data.access_token
  return result
}

export function register(email: string, password: string): Promise<ApiResult<unknown>> {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export async function logout(): Promise<void> {
  await request<void>('/auth/logout', { method: 'POST' })
  accessToken = null
}

export async function bootstrap(): Promise<boolean> {
  return (await refreshAccessToken()) !== null
}
