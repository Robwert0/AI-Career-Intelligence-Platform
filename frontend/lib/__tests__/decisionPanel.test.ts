import { describe, expect, it } from 'vitest'
import { decisionPanelKind } from '../decisionPanel'
import type { Recovery } from '../match'

describe('decisionPanelKind (Amendment 5: the decision panel follows decision.error.recovery)', () => {
  it.each([
    ['fix_github_url', 'fix_github_url'],
    ['paste_cv', 'paste_cv'],
    ['choose_file', 'choose_file'],
    ['retry_or_continue', 'retry_or_continue'],
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
