import { describe, expect, it } from 'vitest'
import { decisionPanelKind, restoredPanelKind } from '../decisionPanel'
import type { Recovery } from '../match'

describe('decisionPanelKind: the decision panel follows decision.error.recovery', () => {
  it.each([
    ['fix_github_url', 'fix_github_url'],
    ['paste_cv', 'paste_cv'],
    ['choose_file', 'choose_file'],
    ['retry_or_continue', 'retry_or_continue'],
    ['wait_for_reset', 'wait_for_reset'],
  ] as const)('%s -> %s', (recovery, kind) => {
    expect(decisionPanelKind(recovery)).toBe(kind)
  })

  it.each(['retry', 'wait', 'paste', 'fix_url', 'edit_job'] as Recovery[])(
    'degrades an unexpected recovery (%s) to retry_or_continue, never a blind fix_github_url-style retry',
    (recovery) => {
      expect(decisionPanelKind(recovery)).toBe('retry_or_continue')
    },
  )
})

describe('restoredPanelKind', () => {
  it('keeps a spent daily budget retry-free even when the reload dropped the CV', () => {
    expect(restoredPanelKind('wait_for_reset', 'cv', true)).toBe('wait_for_reset')
  })

  it('still asks for the file again for an ordinary CV retry after a reload', () => {
    expect(restoredPanelKind('retry_or_continue', 'cv', true)).toBe('choose_file')
  })
})
