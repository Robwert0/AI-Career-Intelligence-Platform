import { expect } from 'vitest'
import type { MatchReport } from '../match'
import {
  CATEGORY_LABEL,
  COVERAGE_LABEL,
  EVIDENCE_KIND_LABEL,
  IMPORTANCE_LABEL,
  STATUS_LABEL,
} from '../matchReport'

// JSON imports widen every literal to string, so the fixture cannot be assigned to MatchReport
// directly. This parser checks what the compiler cannot -- exact key sets and enum membership,
// against the very maps the UI renders from -- and only then hands back the typed value.
const SOURCE_STATUSES = ['read', 'not_provided', 'failed', 'skipped']

function keysOf(value: object): string[] {
  return Object.keys(value).sort()
}

function expectKeys(value: object, expected: string[]) {
  expect(keysOf(value)).toEqual([...expected].sort())
}

export function parseReport(raw: unknown): MatchReport {
  const report = raw as MatchReport
  expectKeys(report, [
    'score',
    'refusal',
    'summary',
    'breakdown',
    'coverage',
    'requirements',
    'recommendations',
    'rewrites',
    'disclaimer',
    'model',
  ])
  expect((report.score === null) === (report.refusal !== null)).toBe(true)
  for (const row of report.breakdown) {
    expectKeys(row, ['category', 'weight', 'effective_weight', 'score', 'points'])
    expect(Object.keys(CATEGORY_LABEL)).toContain(row.category)
  }
  expect(Object.keys(COVERAGE_LABEL)).toContain(report.coverage.level)
  expect(SOURCE_STATUSES).toContain(report.coverage.cv)
  expect(SOURCE_STATUSES).toContain(report.coverage.github.status)
  for (const requirement of report.requirements) {
    expectKeys(requirement, [
      'id',
      'text',
      'importance',
      'status',
      'rationale',
      'hard_gap',
      'evidence',
    ])
    expect(Object.keys(IMPORTANCE_LABEL)).toContain(requirement.importance)
    expect(Object.keys(STATUS_LABEL)).toContain(requirement.status)
    for (const item of requirement.evidence) {
      expectKeys(item, ['id', 'source', 'kind', 'section_label', 'text', 'url'])
      expect(['cv', 'github']).toContain(item.source)
      expect(Object.keys(EVIDENCE_KIND_LABEL)).toContain(item.kind)
    }
  }
  return raw as MatchReport
}
