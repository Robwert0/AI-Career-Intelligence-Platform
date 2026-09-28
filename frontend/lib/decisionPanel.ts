import type { Recovery } from './match'

export type DecisionPanelKind = 'fix_github_url' | 'paste_cv' | 'choose_file' | 'retry_or_continue'

// A needs_decision pause always resolves through recovery, not the failure code: a code we don't
// otherwise special-case (a future backend addition) still gets a safe panel instead of a blind
// retry. fix_github_url is the only kind that must never fall back to it -- a retry there would
// just re-fetch the same bad URL and spend another GitHub token.
export function decisionPanelKind(recovery: Recovery): DecisionPanelKind {
  switch (recovery) {
    case 'fix_github_url':
    case 'paste_cv':
    case 'choose_file':
      return recovery
    default:
      return 'retry_or_continue'
  }
}
