import { describe, expect, it } from 'vitest'
import { accountIdFrom } from '../auth'
import { restoredPanelKind } from '../decisionPanel'
import type { ApiResult } from '../http'
import type { AnalysisView, MatchReport } from '../match'
import {
  availabilityText,
  clearRecoveryId,
  expiresAt,
  isCurrentRestore,
  readRecoveryId,
  restoreOutcome,
  saveRecoveryId,
} from '../matchRecovery'
import { claimTabSession, clearTabSession, type KeyValueStore } from '../tabSession'

const ID = 'AbCdEfGhIjKlMnOpQrSt_-'
const OTHER_ID = 'ZZZZZZZZZZZZZZZZZZZZZZ'
const REPORT = { score: 70 } as unknown as MatchReport
const RECEIVED = 1_000_000

function memoryStore(initial: Record<string, string> = {}): KeyValueStore & {
  data: Map<string, string>
} {
  const data = new Map(Object.entries(initial))
  return {
    data,
    get length() {
      return data.size
    },
    key: (index) => [...data.keys()][index] ?? null,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
  }
}

function throwingStore(): KeyValueStore {
  const fail = () => {
    throw new DOMException('blocked', 'SecurityError')
  }
  return { length: 0, key: fail, getItem: fail, setItem: fail, removeItem: fail }
}

function view(patch: Partial<AnalysisView>): ApiResult<AnalysisView> {
  return {
    ok: true,
    data: {
      analysis_id: ID,
      stage: null,
      queue_position: null,
      error: null,
      decision: null,
      report: null,
      expires_in_seconds: 1800,
      status: 'running',
      ...patch,
    } as AnalysisView,
  }
}

function failure(status: number, code?: string): ApiResult<AnalysisView> {
  return { ok: false, status, detail: 'x', code }
}

function token(payload: object): string {
  const body = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_')
  return `header.${body.replace(/=+$/, '')}.signature`
}

describe('the stored recovery reference', () => {
  it('keeps only an analysis id, under the tab prefix', () => {
    const store = memoryStore()
    saveRecoveryId(ID, store)

    expect([...store.data.entries()]).toEqual([['aci:match:analysis', ID]])
    expect(readRecoveryId(store)).toBe(ID)
  })

  it('never stores or returns anything that is not an analysis id', () => {
    const store = memoryStore({ 'aci:match:analysis': '../../users/me' })

    expect(readRecoveryId(store)).toBeNull()
    saveRecoveryId('{"cv":"text"}', store)
    expect(store.data.get('aci:match:analysis')).toBe('../../users/me')
  })

  it('is cleared on demand', () => {
    const store = memoryStore()
    saveRecoveryId(ID, store)
    clearRecoveryId(store)

    expect(readRecoveryId(store)).toBeNull()
  })

  it('degrades to no recovery when storage is blocked or missing', () => {
    expect(() => saveRecoveryId(ID, throwingStore())).not.toThrow()
    expect(readRecoveryId(throwingStore())).toBeNull()
    expect(readRecoveryId(null)).toBeNull()
  })
})

describe('tab session ownership', () => {
  it('wipes every app key when a different account claims the tab', () => {
    const store = memoryStore({ 'aci:owner': 'alice', 'aci:match:analysis': ID, theme: 'dark' })

    claimTabSession('bob', store)

    expect(Object.fromEntries(store.data)).toEqual({ 'aci:owner': 'bob', theme: 'dark' })
  })

  it('keeps the state when the same account signs back in', () => {
    const store = memoryStore({ 'aci:owner': 'alice', 'aci:match:analysis': ID })

    claimTabSession('alice', store)

    expect(readRecoveryId(store)).toBe(ID)
  })

  it('clears every app key on sign-out but leaves unrelated keys', () => {
    const store = memoryStore({ 'aci:owner': 'alice', 'aci:match:analysis': ID, theme: 'dark' })

    clearTabSession(store)

    expect(Object.fromEntries(store.data)).toEqual({ theme: 'dark' })
  })

  it('tolerates blocked storage', () => {
    expect(() => claimTabSession('alice', throwingStore())).not.toThrow()
    expect(() => clearTabSession(throwingStore())).not.toThrow()
  })
})

describe('accountIdFrom', () => {
  it('reads the subject claim, including base64url characters', () => {
    expect(accountIdFrom(token({ sub: 'a1b2-c3', note: '>>>???' }))).toBe('a1b2-c3')
  })

  it.each([null, '', 'not-a-jwt', 'a.%%%.c', token({}), token({ sub: 42 })])(
    'is null for %s',
    (value) => {
      expect(accountIdFrom(value)).toBeNull()
    },
  )
})

describe('restoreOutcome', () => {
  it('restores a finished analysis straight to its report with the server expiry', () => {
    const result = view({ status: 'done', report: REPORT, expires_in_seconds: 900 })

    expect(restoreOutcome(result, RECEIVED)).toEqual({
      type: 'report',
      analysisId: ID,
      report: REPORT,
      expiresAt: RECEIVED + 900_000,
    })
  })

  it.each(['queued', 'running', 'needs_decision', 'failed'] as const)(
    'resumes polling a %s analysis',
    (status) => {
      expect(restoreOutcome(view({ status }), RECEIVED)).toEqual({
        type: 'progress',
        analysisId: ID,
      })
    },
  )

  it('treats a 404 as gone: expired, discarded or never this account’s', () => {
    expect(restoreOutcome(failure(404, 'analysis_not_found'), RECEIVED)).toEqual({ type: 'gone' })
  })

  it('treats a 401 as an ended session, not a missing analysis', () => {
    expect(restoreOutcome(failure(401), RECEIVED)).toEqual({ type: 'session_ended' })
  })

  it.each([0, 429, 500, 502, 503, 504])(
    'keeps the reference after a temporary %s failure',
    (status) => {
      expect(restoreOutcome(failure(status), RECEIVED).type).toBe('unreachable')
    },
  )
})

describe('isCurrentRestore: stale responses never restore another session', () => {
  const request = { accountId: 'alice', analysisId: ID }

  it('applies a response for the same account and the same stored analysis', () => {
    expect(isCurrentRestore(request, { accountId: 'alice', storedId: ID })).toBe(true)
  })

  it('drops a response that arrives after the account changed', () => {
    expect(isCurrentRestore(request, { accountId: 'bob', storedId: ID })).toBe(false)
    expect(isCurrentRestore(request, { accountId: null, storedId: ID })).toBe(false)
  })

  it('drops a response after Start over or a newer analysis replaced the reference', () => {
    expect(isCurrentRestore(request, { accountId: 'alice', storedId: null })).toBe(false)
    expect(isCurrentRestore(request, { accountId: 'alice', storedId: OTHER_ID })).toBe(false)
  })

  it('never applies a restore that started without an account', () => {
    const anonymous = { accountId: null, analysisId: ID }
    expect(isCurrentRestore(anonymous, { accountId: null, storedId: ID })).toBe(false)
  })
})

describe('server expiry', () => {
  it('is derived from the remaining seconds the server reported, not a fresh hour', () => {
    expect(expiresAt(120, RECEIVED)).toBe(RECEIVED + 120_000)
    expect(expiresAt(null, RECEIVED)).toBeNull()
  })

  it('counts down against the same deadline, so a reload cannot reset it', () => {
    const deadline = expiresAt(600, RECEIVED)!

    expect(availabilityText(deadline, RECEIVED)).toMatch(/about 10 minutes left/)
    expect(availabilityText(deadline, RECEIVED + 540_000)).toMatch(/about 1 minute left/)
    expect(availabilityText(deadline, RECEIVED + 600_000)).toMatch(/expired/)
  })
})

describe('restoredPanelKind', () => {
  it('asks for the CV again when a restored CV retry would resend nothing', () => {
    expect(restoredPanelKind('retry_or_continue', 'cv', true)).toBe('choose_file')
    expect(restoredPanelKind('retry_or_continue', 'cv', false)).toBe('retry_or_continue')
  })

  it('leaves a GitHub retry alone: the server still holds the URL', () => {
    expect(restoredPanelKind('retry_or_continue', 'github', true)).toBe('retry_or_continue')
    expect(restoredPanelKind('fix_github_url', 'github', true)).toBe('fix_github_url')
  })
})
