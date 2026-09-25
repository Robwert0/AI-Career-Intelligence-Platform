import { describe, expect, it } from 'vitest'
import { getProject, projects } from '../projects'

const PRIVATE_REPOS = ['Practica', 'FunProjetcs']

describe('projects', () => {
  it('uses unique, URL-safe slugs because each one is a route', () => {
    const slugs = projects.map((project) => project.slug)
    expect(new Set(slugs).size).toBe(slugs.length)
    for (const slug of slugs) expect(slug).toMatch(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
  })

  it('fills every field a project page renders', () => {
    for (const project of projects) {
      for (const field of [
        'name',
        'tagline',
        'context',
        'period',
        'purpose',
        'description',
      ] as const) {
        expect(project[field].trim(), `${project.slug}.${field}`).not.toBe('')
      }
      expect(project.stack.length, project.slug).toBeGreaterThan(0)
      expect(project.highlights.length, project.slug).toBeGreaterThan(0)
    }
  })

  it('never links a private repo, which would 404 for visitors', () => {
    const hrefs = projects.flatMap((project) => project.repos)
    for (const href of hrefs) {
      expect(href).toMatch(/^https:\/\/github\.com\/Robwert0\/[\w.-]+$/)
      expect(PRIVATE_REPOS).not.toContain(href.split('/').pop())
    }
  })

  it('has exactly one flagship so the top tile is unambiguous', () => {
    expect(projects.filter((project) => project.category === 'flagship')).toHaveLength(1)
  })

  it('looks projects up by slug', () => {
    expect(getProject('jarvis')?.name).toBe('Jarvis')
    expect(getProject('no-such-project')).toBeUndefined()
  })
})
