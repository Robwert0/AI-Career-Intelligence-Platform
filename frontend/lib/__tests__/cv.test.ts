import { describe, expect, it } from 'vitest'
import { cv } from '../cv'

const everyHref = [
  ...cv.links.map((link) => link.href),
  ...cv.projects.flatMap((project) => (project.repo ? [project.repo] : [])),
]

describe('cv content', () => {
  it('links only over https or mailto', () => {
    for (const href of everyHref) expect(href).toMatch(/^(https:\/\/|mailto:)/)
  })

  it('never publishes a phone number', () => {
    const content = JSON.stringify(cv)
    expect(content).not.toMatch(/\+\d{2}/)
    expect(content.replace(/\D/g, '')).not.toContain('766308044')
    expect(everyHref.some((href) => href.startsWith('tel:'))).toBe(false)
  })

  it('serves the photo from our own origin so the CSP img-src stays self', () => {
    if (cv.photo) expect(cv.photo.src).toMatch(/^\/[^/]/)
  })

  it('has no empty section a visitor would see as a blank heading', () => {
    for (const list of [cv.experience, cv.projects, cv.skills, cv.education, cv.languages]) {
      expect(list.length).toBeGreaterThan(0)
    }
  })

  it('gives every project and role unique keys for rendering', () => {
    const projectNames = cv.projects.map((project) => project.name)
    const roleKeys = cv.experience.map((role) => `${role.company}|${role.period}`)
    expect(new Set(projectNames).size).toBe(projectNames.length)
    expect(new Set(roleKeys).size).toBe(roleKeys.length)
  })
})
