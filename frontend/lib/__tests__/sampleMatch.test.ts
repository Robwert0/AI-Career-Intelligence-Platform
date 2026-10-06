import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { evidenceById, requirementTextById } from '../matchReport'
import { SAMPLE_CANDIDATE, SAMPLE_JOB, SAMPLE_REPORT, sampleCtas } from '../sampleMatch'
import { parseReport } from './reportShape'

const ROOT = path.resolve(__dirname, '../..')

describe('the public sample report', () => {
  const report = parseReport(SAMPLE_REPORT)

  it('is a scored report with every requirement status a visitor should see', () => {
    expect(report.score).toBe(65)
    const statuses = new Set(report.requirements.map((r) => r.status))
    expect([...statuses].sort()).toEqual([
      'demonstrated',
      'not_assessed',
      'not_demonstrated',
      'partial',
    ])
  })

  it('adds its breakdown points up to the score', () => {
    const total = report.breakdown.reduce((sum, row) => sum + row.points, 0)
    expect(Math.round(total)).toBe(report.score)
  })

  it('names only requirements and evidence the report contains', () => {
    const texts = requirementTextById(report)
    const evidence = evidenceById(report)
    const advice = [...report.recommendations.immediate, ...report.recommendations.longer_term]

    for (const item of advice) expect(texts.has(item.requirement_id)).toBe(true)
    for (const line of [...report.summary.strongest, ...report.summary.gaps]) {
      expect([...texts.values()]).toContain(line)
    }
    for (const rewrite of report.rewrites) {
      expect(evidence.get(rewrite.evidence_id)?.text).toBe(rewrite.before)
      expect(evidence.get(rewrite.evidence_id)?.source).toBe('cv')
    }
  })

  it('links to no real GitHub account', () => {
    const urls = [...evidenceById(report).values()].map((item) => item.url)
    expect(urls.every((url) => url === null)).toBe(true)
  })

  it('is labelled as sample data rather than a model run', () => {
    expect(report.model).toBe('sample data')
    expect(SAMPLE_CANDIDATE).not.toBe('')
    expect(SAMPLE_JOB.title).not.toBe('')
  })
})

describe('sample report actions', () => {
  it('sends a visitor to sign in or register, then back to /match', () => {
    expect(sampleCtas(false)).toEqual([
      { href: '/login?next=%2Fmatch', label: 'Sign in to analyse your own job', primary: true },
      { href: '/register?next=%2Fmatch', label: 'Create an account', primary: false },
    ])
  })

  it('sends a signed-in user straight to the analyzer', () => {
    expect(sampleCtas(true)).toEqual([
      { href: '/match', label: 'Analyse your own job', primary: true },
    ])
  })

  it('never offers an edit or re-run that has nothing to re-run', () => {
    const labels = [...sampleCtas(false), ...sampleCtas(true)].map((cta) => cta.label.toLowerCase())
    expect(labels.some((label) => /edit|re-run|start over/.test(label))).toBe(false)
  })
})

// Viewing the sample must not call the backend: walk the sample route's runtime imports and fail
// if any reaches the authenticated API client or the analysis endpoints.
const FORBIDDEN = ['lib/api.ts', 'lib/match.ts', 'lib/useAnalysis.ts', 'lib/useJobIntake.ts']
const IMPORT = /^import\s+(?!type\b)[^'"]*?from\s+'([^']+)'/gm

function resolveImport(from: string, specifier: string): string | null {
  const base = specifier.startsWith('@/')
    ? path.join(ROOT, specifier.slice(2))
    : specifier.startsWith('.')
      ? path.resolve(path.dirname(from), specifier)
      : null
  if (base === null) return null
  for (const candidate of [base, `${base}.ts`, `${base}.tsx`]) {
    try {
      readFileSync(candidate)
      return candidate
    } catch {}
  }
  return null
}

function runtimeImports(entry: string): Set<string> {
  const seen = new Set<string>()
  const stack = [entry]
  while (stack.length > 0) {
    const file = stack.pop()!
    if (seen.has(file) || file.endsWith('.json')) continue
    seen.add(file)
    for (const match of readFileSync(file, 'utf8').matchAll(IMPORT)) {
      const resolved = resolveImport(file, match[1])
      if (resolved !== null) stack.push(resolved)
    }
  }
  return seen
}

describe('the sample route', () => {
  it('imports nothing that can call the match API', () => {
    const reached = [...runtimeImports(path.join(ROOT, 'app/match/sample/page.tsx'))].map((file) =>
      path.relative(ROOT, file),
    )

    expect(reached).toContain('components/match/MatchReportView.tsx')
    expect(reached.filter((file) => FORBIDDEN.includes(file))).toEqual([])
  })

  it('catches a forbidden import when there is one', () => {
    const reached = [...runtimeImports(path.join(ROOT, 'components/match/MatchAnalyzer.tsx'))]
    expect(reached.map((file) => path.relative(ROOT, file))).toContain('lib/match.ts')
  })
})
