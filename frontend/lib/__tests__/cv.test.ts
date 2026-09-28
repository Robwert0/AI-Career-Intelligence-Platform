import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { cv } from '../cv'
import { NAV_LINKS } from '../nav'
import { getProject } from '../projects'

const PHONE_SHAPED = /(?:\d[\s().-]*){9,}/

function everyString(value: unknown): string[] {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(everyString)
  if (value && typeof value === 'object') return Object.values(value).flatMap(everyString)
  return []
}

const everyHref = [
  ...cv.links.map((link) => link.href),
  ...cv.projects.flatMap((project) => project.repos),
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

  it('gives every role a unique key for rendering', () => {
    const roleKeys = cv.experience.map((role) => `${role.company}|${role.period}`)
    expect(new Set(roleKeys).size).toBe(roleKeys.length)
  })
})

describe('portfolio wiring', () => {
  it('links selected work only to project pages that exist', () => {
    for (const work of cv.selectedWork) {
      if (work.projectSlug) expect(getProject(work.projectSlug), work.title).toBeDefined()
    }
  })

  it('offers a CV download only when the PDF is actually in public/', () => {
    if (!cv.pdf) return
    expect(cv.pdf.href).toMatch(/^\/[\w.-]+\.pdf$/)
    expect(existsSync(join(__dirname, '..', '..', 'public', cv.pdf.href))).toBe(true)
  })

  it('points every nav link at a section the home page renders', () => {
    const sectionIds = ['work', 'experience', 'skills', 'education', 'contact']
    for (const link of NAV_LINKS) expect(sectionIds).toContain(link.href.replace('/#', ''))
  })
})
