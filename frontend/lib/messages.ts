import { formatWait } from './duration'
import type { ApiResult } from './http'

type Failure = Extract<ApiResult<unknown>, { ok: false }>

function waitPhrase(retryAfter?: number): string {
  if (retryAfter === undefined) return 'Try again shortly.'
  return `Try again in ${formatWait(retryAfter)}.`
}

export function authErrorMessage(failure: Failure): string {
  switch (failure.status) {
    case 0:
      return 'Could not reach the server.'
    case 401:
    case 403:
      return 'Email or password is incorrect.'
    case 409:
      return 'That email is already registered.'
    case 422:
      return failure.detail
    case 429:
      return `Too many attempts. ${waitPhrase(failure.retryAfter)}`
    case 503:
      return 'The service is busy. Please try again shortly.'
    default:
      return 'Something went wrong. Please try again.'
  }
}
