import type { JobPosting, MatchReport } from './match'
import { withNext } from './redirect'
import sample from './sample/match-report.sample.json'

export const SAMPLE_CANDIDATE = 'Rowan Ellery'
export const SAMPLE_JOB: Pick<JobPosting, 'title' | 'company'> = {
  title: 'Senior Backend Engineer',
  company: 'Quillfeather Freight',
}

// A static fixture: the statuses and advice stand in for model output, and the backend's
// test_sample_report.py proves every derived number is what build_report() computes from them.
export const SAMPLE_REPORT = sample as MatchReport

export type SampleCta = { href: string; label: string; primary: boolean }

export function sampleCtas(authenticated: boolean): SampleCta[] {
  if (authenticated) return [{ href: '/match', label: 'Analyse your own job', primary: true }]
  return [
    { href: withNext('/login', '/match'), label: 'Sign in to analyse your own job', primary: true },
    { href: withNext('/register', '/match'), label: 'Create an account', primary: false },
  ]
}
