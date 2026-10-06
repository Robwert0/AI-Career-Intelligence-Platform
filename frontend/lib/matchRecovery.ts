import type { ApiResult } from './http'
import type { AnalysisView, MatchReport } from './match'
import { readTabItem, writeTabItem, type KeyValueStore } from './tabSession'

// Only the id: the CV, the posting and the report stay on the server, behind the owner check.
const KEY = 'match:analysis'
// Mirrors the server's token_urlsafe(16) ids, so nothing else stored under the key is ever sent.
const ANALYSIS_ID = /^[A-Za-z0-9_-]{22}$/

export function readRecoveryId(store?: KeyValueStore | null): string | null {
  const stored = readTabItem(KEY, store)
  return stored !== null && ANALYSIS_ID.test(stored) ? stored : null
}

export function saveRecoveryId(analysisId: string, store?: KeyValueStore | null): void {
  if (ANALYSIS_ID.test(analysisId)) writeTabItem(KEY, analysisId, store)
}

export function clearRecoveryId(store?: KeyValueStore | null): void {
  writeTabItem(KEY, null, store)
}

export type Restore =
  | { type: 'report'; analysisId: string; report: MatchReport; expiresAt: number | null }
  | { type: 'progress'; analysisId: string }
  | { type: 'gone' }
  | { type: 'session_ended' }
  | { type: 'unreachable'; message: string }

export function expiresAt(expiresInSeconds: number | null, receivedAt: number): number | null {
  return expiresInSeconds === null ? null : receivedAt + expiresInSeconds * 1000
}

// Only a 404 means the record is gone; a network error, 429 or 5xx says nothing about it, so the
// reference must survive those for the next attempt.
export function restoreOutcome(result: ApiResult<AnalysisView>, receivedAt: number): Restore {
  if (result.ok) {
    const view = result.data
    return view.status === 'done'
      ? {
          type: 'report',
          analysisId: view.analysis_id,
          report: view.report,
          expiresAt: expiresAt(view.expires_in_seconds, receivedAt),
        }
      : { type: 'progress', analysisId: view.analysis_id }
  }
  if (result.status === 404) return { type: 'gone' }
  if (result.status === 401) return { type: 'session_ended' }
  return {
    type: 'unreachable',
    message:
      result.status === 0
        ? 'Could not reach the server to restore your analysis. Check your connection.'
        : 'The server could not restore your analysis just now.',
  }
}

export type RestoreRequest = { accountId: string | null; analysisId: string }

// A restore that resolves after the account changed, after Start over, or after another analysis
// took the slot belongs to a session that no longer exists and must not be applied.
export function isCurrentRestore(
  request: RestoreRequest,
  now: { accountId: string | null; storedId: string | null },
): boolean {
  return (
    request.accountId !== null &&
    request.accountId === now.accountId &&
    request.analysisId === now.storedId
  )
}

export const INPUTS_NOT_KEPT =
  'Your job posting and CV are not kept in this browser, so they were not restored after the reload. To change them and run again, start a new analysis and enter them again.'

export function availabilityText(expiresAtMs: number, nowMs: number): string {
  const minutes = Math.ceil((expiresAtMs - nowMs) / 60_000)
  if (minutes <= 0) return 'This analysis has expired and will no longer load after a reload.'
  const clock = new Date(expiresAtMs).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const left = minutes === 1 ? 'about 1 minute' : `about ${minutes} minutes`
  return `Kept on the server until ${clock} (${left} left), then deleted.`
}
