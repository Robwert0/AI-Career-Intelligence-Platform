import type { ChatResponse, Source } from './api'
import { formatWait } from './duration'
import type { ApiResult } from './http'

export type Turn =
  | { kind: 'question'; id: string; text: string }
  | { kind: 'answer'; id: string; text: string; sources: Source[] }
  | { kind: 'refusal'; id: string; text: string }
  | { kind: 'error'; id: string; text: string }

function nextId(): string {
  return crypto.randomUUID()
}

function chatErrorText(failure: Extract<ApiResult<ChatResponse>, { ok: false }>): string {
  switch (failure.status) {
    case 0:
      return 'Could not reach the server.'
    case 401:
      return 'Your session ended. Sign in again.'
    case 422:
      return failure.detail
    case 429:
      return failure.retryAfter === undefined
        ? 'Too many questions. Try again shortly.'
        : `Too many questions. Try again in ${formatWait(failure.retryAfter)}.`
    case 503:
      return 'The model is busy or still starting up. Try again in a moment.'
    default:
      return 'Something went wrong. Please try again.'
  }
}

export function questionTurn(text: string): Turn {
  return { kind: 'question', id: nextId(), text }
}

export function replyTurn(result: ApiResult<ChatResponse>): Turn {
  if (!result.ok) return { kind: 'error', id: nextId(), text: chatErrorText(result) }
  if (result.data.refused) return { kind: 'refusal', id: nextId(), text: result.data.answer }
  return { kind: 'answer', id: nextId(), text: result.data.answer, sources: result.data.sources }
}
