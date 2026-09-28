import { describe, expect, it } from 'vitest'
import type { AssessedRequirement, BreakdownRow, Coverage, Evidence } from '../match'
import {
  citation,
  evidenceById,
  evidenceShare,
  formatPercent,
  formatPoints,
  formatWeight,
  requirementTextById,
  safeRepoUrl,
  sourceSummary,
  statusLabel,
  weightsRedistributed,
} from '../matchReport'

function evidence(patch: Partial<Evidence> = {}): Evidence {
  return {
    id: 'cv:experience:0',
    source: 'cv',
    kind: 'work',
    section_label: 'Experience · Tyrell',
    text: 'Built Go services',
    url: null,
    ...patch,
  }
}

function requirement(patch: Partial<AssessedRequirement> = {}): AssessedRequirement {
  return {
    id: 'req:required:0',
    text: '5 years of Go',
    importance: 'required',
    status: 'demonstrated',
    rationale: 'Clear.',
    hard_gap: false,
    evidence: [evidence()],
    ...patch,
  }
}

function coverage(patch: Partial<Coverage> = {}): Coverage {
  return {
    level: 'medium',
    cv: 'read',
    github: { status: 'read', inspected_repos: 10, public_non_fork_repos: 23, readmes_found: 8 },
    requirements_with_evidence: 0.8,
    limitations: [],
    ...patch,
  }
}

function row(patch: Partial<BreakdownRow> = {}): BreakdownRow {
  return {
    category: 'required',
    weight: 70,
    effective_weight: 70,
    score: 0.75,
    points: 52.5,
    ...patch,
  }
}

describe('statusLabel', () => {
  it.each([
    ['demonstrated', 'Demonstrated'],
    ['partial', 'Partially demonstrated'],
    ['not_demonstrated', 'Not demonstrated'],
    ['unmet', 'Unmet'],
    ['not_assessed', 'Not assessed'],
  ] as const)('%s → %s', (status, label) => {
    expect(statusLabel({ status, hard_gap: false })).toBe(label)
  })

  it('names a hard gap in words', () => {
    expect(statusLabel({ status: 'unmet', hard_gap: true })).toBe('Unmet · hard gap')
  })
})

describe('safeRepoUrl', () => {
  it.each([
    ['https://github.com/octocat/hello-world', 'https://github.com/octocat/hello-world'],
    ['https://github.com/octocat', 'https://github.com/octocat'],
  ])('keeps %s', (url, expected) => {
    expect(safeRepoUrl(url)).toBe(expected)
  })

  it.each([
    null,
    'javascript:alert(1)',
    'http://github.com/octocat',
    'https://github.com.evil.example/octocat',
    'https://evil.example/github.com/octocat',
    'https://user:pass@github.com/octocat',
    'https://github.com:8443/octocat',
    'not a url',
  ])('drops %s', (url) => {
    expect(safeRepoUrl(url)).toBeNull()
  })
})

describe('citation', () => {
  it('cites the CV section without a link', () => {
    expect(citation(evidence())).toEqual({ label: 'CV · Experience · Tyrell', href: null })
  })

  it('links a repo', () => {
    const repo = evidence({
      source: 'github',
      kind: 'repo',
      section_label: 'jarvis',
      url: 'https://github.com/octocat/jarvis',
    })

    expect(citation(repo)).toEqual({
      label: 'GitHub · jarvis',
      href: 'https://github.com/octocat/jarvis',
    })
  })

  it('links a CV project merged with its repo', () => {
    const merged = evidence({ kind: 'project', url: 'https://github.com/octocat/jarvis' })

    expect(citation(merged).href).toBe('https://github.com/octocat/jarvis')
  })

  it('never links an unsafe url', () => {
    expect(citation(evidence({ source: 'github', url: 'javascript:alert(1)' })).href).toBeNull()
  })
})

describe('lookups', () => {
  const report = {
    requirements: [
      requirement(),
      requirement({
        id: 'req:preferred:0',
        text: 'Kubernetes',
        evidence: [evidence(), evidence({ id: 'gh:repo:jarvis', source: 'github' })],
      }),
    ],
  }

  it('indexes evidence by id, once each', () => {
    expect([...evidenceById(report).keys()]).toEqual(['cv:experience:0', 'gh:repo:jarvis'])
  })

  it('names requirements by id', () => {
    expect(requirementTextById(report).get('req:preferred:0')).toBe('Kubernetes')
    expect(requirementTextById(report).get('req:missing')).toBeUndefined()
  })
})

describe('numbers', () => {
  it('formats the category score as a percentage and points to one decimal', () => {
    expect(formatPercent(0.755)).toBe('76%')
    expect(formatPoints(52.5)).toBe('52.5')
    expect(formatPoints(6.6667)).toBe('6.7')
  })

  it('shows a redistributed weight', () => {
    expect(formatWeight(row())).toBe('70')
    expect(formatWeight(row({ weight: 70, effective_weight: 77.78 }))).toBe('70 → 77.8')
    expect(
      weightsRedistributed([
        row(),
        row({ category: 'preferred', weight: 20, effective_weight: 0 }),
      ]),
    ).toBe(true)
    expect(weightsRedistributed([row()])).toBe(false)
  })
})

describe('coverage text', () => {
  it('summarises both sources', () => {
    expect(sourceSummary(coverage())).toEqual([
      'CV: read',
      'GitHub: 10 of 23 public repositories inspected, 8 READMEs found',
    ])
  })

  it('describes a source that was not read', () => {
    expect(sourceSummary(coverage({ cv: 'not_provided' }))[0]).toBe('CV: not provided')
    const github = {
      status: 'failed' as const,
      inspected_repos: 0,
      public_non_fork_repos: 0,
      readmes_found: 0,
    }
    expect(sourceSummary(coverage({ github }))[1]).toBe('GitHub: could not be read')
  })

  it('uses the singular for one README', () => {
    const github = {
      status: 'read' as const,
      inspected_repos: 1,
      public_non_fork_repos: 1,
      readmes_found: 1,
    }
    expect(sourceSummary(coverage({ github }))[1]).toBe(
      'GitHub: 1 of 1 public repositories inspected, 1 README found',
    )
  })

  it('states the evidence share', () => {
    expect(evidenceShare(coverage())).toBe('80% of assessed requirements have cited evidence.')
  })
})
