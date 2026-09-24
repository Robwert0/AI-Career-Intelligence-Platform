import { describe, expect, it } from 'vitest'
import { cv } from '../cv'

const PHONE_SHAPED = /(?:\d[\s().-]*){9,}/

function everyString(value: unknown): string[] {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(everyString)
  if (value && typeof value === 'object') return Object.values(value).flatMap(everyString)
  return []
}

const everyHref = [
  ...cv.links.map((link) => link.href),
  ...cv.projects.flatMap((project) => (project.repo ? [project.repo] : [])),
]

describe('cv content', () => {
  it('links only over https or mailto', () => {
    for (const href of everyHref) expect(href).toMatch(/^(https:\/\/|mailto:)/)
  })

  it('never publishes a phone number', () => {
    for (const text of everyString(cv)) {
      expect(text).not.toMatch(/\+\d{2}/)
      expect(text).not.toMatch(PHONE_SHAPED)
    }
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
