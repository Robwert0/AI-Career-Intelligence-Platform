import { describe, expect, it } from 'vitest'
import { ROLE_OPTIONS, roleLabel } from '../roles'

describe('roles', () => {
  it('offers exactly the four backend roles', () => {
    expect(ROLE_OPTIONS.map((option) => option.value)).toEqual([
      'recruiter',
      'hiring_manager',
      'engineer',
      'other',
    ])
  })

  it('labels a known role', () => {
    expect(roleLabel('hiring_manager')).toBe('Hiring manager')
  })

  it('shows a dash when the role was not given', () => {
    expect(roleLabel(null)).toBe('—')
  })
})
