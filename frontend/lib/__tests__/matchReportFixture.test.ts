import { describe, expect, it } from 'vitest'
import {
  CATEGORY_LABEL,
  COVERAGE_LABEL,
  citation,
  evidenceById,
  evidenceShare,
  filterCounts,
  formatPercent,
  formatPoints,
  formatWeight,
  matchesFilter,
  requirementAnchor,
  requirementTextById,
  sourceStatusLines,
  sourceSummary,
  statusLabel,
  weightsRedistributed,
} from '../matchReport'
import fixture from './fixtures/match-report.full.json'
import { parseReport } from './reportShape'

const report = parseReport(fixture)

describe('the shared golden report (slice 4 output)', () => {
  it('is assignable to MatchReport: valid enums, exact keys, score <=> refusal', () => {
    expect(report.score).toBe(52)
    expect(report.refusal).toBeNull()
  })

  it('narrows as a scored report under the discriminated union', () => {
    if (report.score === null) throw new Error('expected a scored report')
    const scored: number = report.score
    const noRefusal: null = report.refusal
    expect(scored).toBe(52)
    expect(noRefusal).toBeNull()
  })
})

describe('report view-model helpers on the golden report', () => {
  it('renders the breakdown rows in order with their numbers', () => {
    const rows = report.breakdown.map((row) => [
      CATEGORY_LABEL[row.category],
      formatWeight(row),
      formatPercent(row.score),
      formatPoints(row.points),
    ])

    expect(rows).toEqual([
      ['Required requirements', '70', '50%', '35.0'],
      ['Preferred requirements', '20', '50%', '10.0'],
      ['Applied evidence', '10', '67%', '6.7'],
    ])
    expect(weightsRedistributed(report.breakdown)).toBe(false)
  })

  it('sums the breakdown points to the score', () => {
    const total = report.breakdown.reduce((sum, row) => sum + row.points, 0)

    expect(Math.round(total)).toBe(report.score)
  })

  it('summarises coverage and sources', () => {
    expect(COVERAGE_LABEL[report.coverage.level]).toBe('High')
    expect(sourceSummary(report.coverage)).toEqual([
      'CV: read',
      'GitHub: 10 of 14 public repositories inspected, 7 READMEs found',
    ])
    expect(evidenceShare(report.coverage)).toBe('83% of assessed requirements have cited evidence.')
    expect(report.coverage.limitations).toHaveLength(3)
  })

  it('labels each requirement, required first, with the hard gap named', () => {
    const labels = report.requirements.map((r) => `${r.id}: ${statusLabel(r)}`)

    expect(labels).toEqual([
      'req:required:0: Demonstrated',
      'req:required:1: Partially demonstrated',
      'req:required:2: Partially demonstrated',
      'req:required:3: Unmet · hard gap',
      'req:required:4: Not assessed',
      'req:preferred:0: Demonstrated',
      'req:preferred:1: Not demonstrated',
    ])
    expect(report.requirements.filter((r) => r.hard_gap).map((r) => r.id)).toEqual([
      'req:required:3',
    ])
  })

  it('cites evidence per requirement, and none for the not-assessed one', () => {
    const first = report.requirements[0]
    const permit = report.requirements.find((r) => r.status === 'not_assessed')

    expect(first.evidence.map((item) => citation(item))).toEqual([
      { label: 'CV · Experience · Globex', href: null },
      { label: 'CV · Projects · Ledger', href: 'https://github.com/jane-doe/ledger' },
    ])
    expect(permit?.evidence).toEqual([])
  })

  it('indexes evidence once by id and names requirements by id', () => {
    expect([...evidenceById(report).keys()]).toEqual([
      'cv:experience:0',
      'cv:project:0',
      'cv:skills:0',
      'cv:experience:1',
    ])
    expect(requirementTextById(report).get('req:required:3')).toBe('Rust systems programming')
  })

  it('resolves every recommendation and rewrite to something the report contains', () => {
    const texts = requirementTextById(report)
    const evidence = evidenceById(report)
    const recommendations = [
      ...report.recommendations.immediate,
      ...report.recommendations.longer_term,
    ]

    expect(report.recommendations.immediate).toHaveLength(2)
    expect(report.recommendations.longer_term).toHaveLength(2)
    for (const recommendation of recommendations) {
      expect(texts.has(recommendation.requirement_id)).toBe(true)
    }
    expect(report.rewrites).toHaveLength(1)
    for (const rewrite of report.rewrites) {
      expect(evidence.get(rewrite.evidence_id)?.text).toBe(rewrite.before)
      expect(rewrite.questions.length).toBeGreaterThan(0)
    }
  })
})

describe('requirement filters on the golden report', () => {
  it('counts each filter, with needs attention = partial, not demonstrated or unmet', () => {
    expect(filterCounts(report.requirements)).toEqual({
      all: 7,
      attention: 4,
      demonstrated: 2,
      not_assessed: 1,
    })
  })

  it('keeps the hard gap under needs attention and never under demonstrated', () => {
    const gap = report.requirements.find((r) => r.hard_gap)!
    expect(matchesFilter(gap, 'attention')).toBe(true)
    expect(matchesFilter(gap, 'demonstrated')).toBe(false)
  })

  it('files every status under exactly one narrow filter', () => {
    for (const requirement of report.requirements) {
      const narrow = (['attention', 'demonstrated', 'not_assessed'] as const).filter((f) =>
        matchesFilter(requirement, f),
      )
      expect(narrow, requirement.id).toHaveLength(1)
    }
  })

  it('turns requirement ids into selector-safe anchors', () => {
    expect(requirementAnchor('req:required:3')).toBe('req-req-required-3')
    const anchors = report.requirements.map((r) => requirementAnchor(r.id))
    expect(new Set(anchors).size).toBe(anchors.length)
  })

  it('names each source status in a short line', () => {
    expect(sourceStatusLines(report.coverage)).toEqual([
      { source: 'CV', status: 'read' },
      { source: 'GitHub', status: 'read' },
    ])
  })
})
