import type {
  AssessedRequirement,
  BreakdownCategory,
  BreakdownRow,
  Coverage,
  Evidence,
  EvidenceKind,
  Importance,
  MatchReport,
  RequirementStatus,
  SourceStatus,
} from './match'

export const NOT_A_HIRING_PROBABILITY =
  "This is not a hiring probability or an employer's ATS score."
export const NOT_ASSESSED_NOTE =
  'Not assessed: this is a personal characteristic or work authorization. Confirm it yourself.'

export const STATUS_LABEL: Record<RequirementStatus, string> = {
  demonstrated: 'Demonstrated',
  partial: 'Partially demonstrated',
  not_demonstrated: 'Not demonstrated',
  unmet: 'Unmet',
  not_assessed: 'Not assessed',
}
export const IMPORTANCE_LABEL: Record<Importance, string> = {
  required: 'Required',
  preferred: 'Preferred',
}
export const CATEGORY_LABEL: Record<BreakdownCategory, string> = {
  required: 'Required requirements',
  preferred: 'Preferred requirements',
  applied_evidence: 'Applied evidence',
}
export const COVERAGE_LABEL: Record<Coverage['level'], string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

const SOURCE_STATUS_TEXT: Record<SourceStatus, string> = {
  read: 'read',
  not_provided: 'not provided',
  failed: 'could not be read',
  // A done report never actually carries "failed" here: a source that errored mid-analysis and
  // was skipped by the user's "continue without it" choice shows as "skipped".
  skipped: 'not used: you continued without it',
}

// "profile" (a GitHub bio/profile item) must read as distinct from applied work
// (work/project/repo), never as though the candidate did that work.
export const EVIDENCE_KIND_LABEL: Record<EvidenceKind, string> = {
  work: 'Work experience',
  project: 'Project',
  repo: 'Repository',
  skill_list: 'Skills list',
  education: 'Education',
  accomplishment: 'Accomplishment',
  profile: 'Profile',
}

export type Citation = { label: string; href: string | null }

export function statusLabel(requirement: Pick<AssessedRequirement, 'status' | 'hard_gap'>): string {
  return requirement.hard_gap ? 'Unmet · hard gap' : STATUS_LABEL[requirement.status]
}

export function safeRepoUrl(url: string | null): string | null {
  if (url === null) return null
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return null
  }
  const safe =
    parsed.protocol === 'https:' &&
    parsed.hostname === 'github.com' &&
    parsed.port === '' &&
    parsed.username === '' &&
    parsed.password === ''
  return safe ? parsed.href : null
}

export function citation(evidence: Pick<Evidence, 'source' | 'section_label' | 'url'>): Citation {
  const origin = evidence.source === 'cv' ? 'CV' : 'GitHub'
  return { label: `${origin} · ${evidence.section_label}`, href: safeRepoUrl(evidence.url) }
}

export function evidenceKindLabel(kind: EvidenceKind): string {
  return EVIDENCE_KIND_LABEL[kind]
}

export function evidenceById(report: Pick<MatchReport, 'requirements'>): Map<string, Evidence> {
  const index = new Map<string, Evidence>()
  for (const requirement of report.requirements) {
    for (const item of requirement.evidence) {
      if (!index.has(item.id)) index.set(item.id, item)
    }
  }
  return index
}

export function requirementTextById(
  report: Pick<MatchReport, 'requirements'>,
): Map<string, string> {
  return new Map(report.requirements.map((requirement) => [requirement.id, requirement.text]))
}

export function formatPercent(score: number): string {
  return `${Math.round(score * 100)}%`
}

export function formatPoints(points: number): string {
  return points.toFixed(1)
}

function weightChanged(row: BreakdownRow): boolean {
  return Math.abs(row.effective_weight - row.weight) >= 0.05
}

export function formatWeight(row: BreakdownRow): string {
  return weightChanged(row)
    ? `${row.weight} → ${formatPoints(row.effective_weight)}`
    : String(row.weight)
}

export function weightsRedistributed(rows: BreakdownRow[]): boolean {
  return rows.some(weightChanged)
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

export function sourceSummary(coverage: Coverage): string[] {
  const { github } = coverage
  const githubLine =
    github.status === 'read'
      ? `GitHub: ${github.inspected_repos} of ${github.public_non_fork_repos} public repositories inspected, ${plural(github.readmes_found, 'README')} found`
      : `GitHub: ${SOURCE_STATUS_TEXT[github.status]}`
  return [`CV: ${SOURCE_STATUS_TEXT[coverage.cv]}`, githubLine]
}

export function evidenceShare(coverage: Coverage): string {
  return `${formatPercent(coverage.requirements_with_evidence)} of assessed requirements have cited evidence.`
}
