import type { ChatResponse, HistoryMessage, Source } from './api'
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

// Mirrors backend/app/schemas/chat.py; a history over these limits is a 422.
export const MAX_HISTORY_MESSAGES = 6
export const MAX_HISTORY_MESSAGE_CHARS = 2000
export const MAX_HISTORY_CHARS = 6000

function clip(text: string): string {
  return text.length <= MAX_HISTORY_MESSAGE_CHARS
    ? text
    : `${text.slice(0, MAX_HISTORY_MESSAGE_CHARS - 1)}…`
}

// Only completed exchanges become context: a question whose reply was an error (or is still
// pending) is dropped, and UI-only text never reaches the model. The newest exchanges that fit
// the limits are kept, oldest first.
export function historyFrom(turns: Turn[]): HistoryMessage[] {
  const exchanges: [HistoryMessage, HistoryMessage][] = []
  for (let index = 0; index + 1 < turns.length; index += 1) {
    const question = turns[index]
    const reply = turns[index + 1]
    if (question.kind !== 'question') continue
    if (reply.kind !== 'answer' && reply.kind !== 'refusal') continue
    exchanges.push([
      { role: 'user', content: clip(question.text) },
      { role: 'assistant', content: clip(reply.text) },
    ])
  }

  const kept: [HistoryMessage, HistoryMessage][] = []
  let total = 0
  for (const exchange of exchanges.reverse()) {
    const size = exchange[0].content.length + exchange[1].content.length
    if ((kept.length + 1) * 2 > MAX_HISTORY_MESSAGES || total + size > MAX_HISTORY_CHARS) break
    kept.unshift(exchange)
    total += size
  }
  return kept.flat()
}
